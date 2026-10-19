"""Trusted broker only. No retries, redirects, worker credentials or arbitrary URLs."""
from contextlib import closing
from decimal import Decimal
import http.client
import json
import os
from pathlib import Path
import sqlite3
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit


class SpendLedger:
    """One study-wide ledger, including smoke, errors and unknown outcomes.

    Finite budgets require an operator-confirmed upper cost per request (not a
    guessed token price). Reservations are never refunded from estimated usage.
    Unbounded spending is possible only by an explicit operator choice.
    """
    def __init__(self, path, budget_usd=None, upper_request_usd=None, unbounded=False):
        if not unbounded and (budget_usd is None or upper_request_usd is None):
            raise PermissionError('finite authorization and trusted request-cost bound required')
        self.path = Path(path)
        self.policy = {'unbounded': unbounded, 'budget': str(budget_usd), 'upper': str(upper_request_usd)}
        if not unbounded:
            if Decimal(str(budget_usd)) <= 0 or Decimal(str(upper_request_usd)) <= 0:
                raise ValueError('positive monetary limits required')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS policy(value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, worker TEXT, started REAL, reserved TEXT, outcome TEXT, usage TEXT)')
            existing = db.execute('SELECT value FROM policy').fetchone()
            encoded = json.dumps(self.policy, sort_keys=True)
            if existing and existing[0] != encoded:
                raise PermissionError('cannot reset or expand existing study authorization')
            if not existing:
                db.execute('INSERT INTO policy VALUES(?)', (encoded,))
            db.commit()

    def reserve(self, worker):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT reserved,outcome FROM attempts').fetchall()
            if any(r[1] == 'pending' for r in rows):
                raise RuntimeError('pending or orphan request; no automatic retry')
            upper = Decimal('0') if self.policy['unbounded'] else Decimal(self.policy['upper'])
            if not self.policy['unbounded'] and sum((Decimal(r[0]) for r in rows), Decimal(0))+upper > Decimal(self.policy['budget']):
                raise PermissionError('aggregate monetary reservation exhausted')
            cursor = db.execute('INSERT INTO attempts(worker,started,reserved,outcome) VALUES(?,?,?,?)',
                                (worker, time.time(), str(upper), 'pending'))
            db.commit()
            return cursor.lastrowid

    def finish(self, attempt, outcome, usage=None):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE attempts SET outcome=?,usage=? WHERE id=?', (outcome, json.dumps(usage), attempt))
            db.commit()


class ResponsesProvider:
    def __init__(self, base_url, model, ledger, log, *, authorize=False, key=None):
        if not authorize:
            raise PermissionError('Responses backend is default-deny')
        url = urlsplit(base_url)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment
                or url.path.rstrip('/') != '/v1'):
            raise ValueError('fixed HTTPS /v1 origin required')
        self.host, self.port = url.hostname, url.port or 443
        self.model, self.ledger, self.log = model, ledger, Path(log)
        self.key = key if key is not None else os.environ.get('API_KEY', '')
        if not self.key or '\r' in self.key or '\n' in self.key:
            raise PermissionError('API_KEY missing or invalid; never read global auth files')

    def record(self, record):
        text = json.dumps(record, ensure_ascii=False).replace(self.key, '[REDACTED]')
        with self.log.open('a', encoding='utf-8') as f:
            f.write(text+'\n')

    def request(self, method, endpoint, payload=None, timeout=30):
        if (method, endpoint) not in {('GET', '/v1/models'), ('POST', '/v1/responses')}:
            raise PermissionError('unregistered endpoint')
        # HTTPSConnection does not follow 3xx redirects or use environment proxies.
        conn = http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=ssl.create_default_context())
        expired = threading.Event()
        deadline = time.monotonic()+timeout

        def expire():
            expired.set()
            if conn.sock is not None:
                try:
                    conn.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # Connection may already have closed; deadline still expires.
            conn.close()

        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            conn.connect()
            if expired.is_set():
                raise TimeoutError('provider total deadline expired')
            conn.sock.settimeout(max(0.001, deadline-time.monotonic()))
            body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
            conn.request(method, endpoint, body=body, headers={'Authorization': 'Bearer '+self.key, 'Content-Type': 'application/json'})
            response = conn.getresponse()
            raw = response.read(4*1024*1024+1)
            if expired.is_set() or time.monotonic() >= deadline:
                raise TimeoutError('provider total deadline expired')
            if len(raw) > 4*1024*1024:
                raise ValueError('provider response exceeds byte envelope')
            if response.status != 200:
                raise RuntimeError('provider HTTP status '+str(response.status)+'; no retry or redirect')
            return json.loads(raw)
        finally:
            timer.cancel()
            conn.close()

    def models(self):
        response = self.request('GET', '/v1/models')
        ids = [x['id'] for x in response.get('data', []) if isinstance(x, dict) and isinstance(x.get('id'), str)]
        self.record({'event': 'provider_metadata', 'models': ids, 'provenance': 'gateway-declared, not verified OpenAI backend'})
        return ids

    def respond(self, worker, history, tools, timeout=30, *, max_output_tokens=2048):
        if not isinstance(history, list) or not isinstance(tools, list):
            raise ValueError('invalid Responses input')
        if type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 8192:
            raise ValueError('invalid registered output ceiling')
        payload = {'model': self.model, 'input': history, 'tools': tools, 'store': False,
                   'max_output_tokens': max_output_tokens, 'parallel_tool_calls': False}
        if len(json.dumps(payload).encode()) > 262144:
            raise ValueError('request byte envelope exceeded')
        attempt = self.ledger.reserve(worker)
        start = time.monotonic()
        self.record({'event': 'request_started', 'attempt': attempt, 'worker': worker, 'payload': payload})
        try:
            response = self.request('POST', '/v1/responses', payload, timeout)
            self.record({'event': 'response', 'attempt': attempt, 'worker': worker, 'response': response,
                         'seconds': time.monotonic()-start})
            if response.get('status') != 'completed' or response.get('model') != self.model:
                raise ValueError('incomplete response or returned model differs from frozen model')
            if not isinstance(response.get('output'), list):
                raise ValueError('missing Responses output')
            self.ledger.finish(attempt, 'completed', response.get('usage'))
            return response
        except Exception as exc:
            self.ledger.finish(attempt, 'failed_or_unknown')
            # Do not log arbitrary provider exception strings, headers or credentials.
            self.record({'event': 'request_failed', 'attempt': attempt, 'type': type(exc).__name__,
                         'seconds': time.monotonic()-start})
            raise
