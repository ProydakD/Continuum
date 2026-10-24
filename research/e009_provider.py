"""E009-only authorized HTTPS transport, bounded retries and durable attempt accounting."""
import asyncio
from contextlib import closing
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import random
import re
import sqlite3
import ssl
import time
from urllib.parse import urlsplit

import httpx2 as httpx

from .e009_broker import frame
from .e009_protocol import output_items

RETRYABLE = {408, 429, 500, 502, 503, 504}
QUOTA_ERRORS = {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active",
                "usage_limit_reached", "quota_exceeded", "spend_limit_exceeded"}


class ProviderFailure(RuntimeError):
    """Only fixed, credential-free reason codes cross the adapter boundary."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def retry_delay(header, backoff, now):
    delay = None
    if isinstance(header, str):
        try:
            delay = float(header)
        except ValueError:
            try:
                delay = parsedate_to_datetime(header).timestamp() - now
            except (ValueError, TypeError, OverflowError):
                pass
    if delay is None or not math.isfinite(delay) or delay < 0:
        delay = 0
    return max(backoff, delay)


class AttemptLedger:
    """CAS terminal transitions. Pending/orphan calls and duplicate requests never disappear."""
    def __init__(self, path, policy):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS policy(value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(
                    id INTEGER PRIMARY KEY, context TEXT NOT NULL, body_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL, UNIQUE(context,body_sha256));
                CREATE TABLE IF NOT EXISTS attempts(
                    id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL, ordinal INTEGER NOT NULL,
                    status TEXT NOT NULL, record TEXT NOT NULL, UNIQUE(request_id,ordinal));
            """)
            encoded = frame(policy).decode()
            row = db.execute("SELECT value FROM policy").fetchone()
            if row and row[0] != encoded:
                raise ProviderFailure("ledger_policy_mismatch")
            if not row:
                db.execute("INSERT INTO policy VALUES(?)", (encoded,))
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA synchronous=FULL")
        return closing(db)

    def begin(self, context, body_sha256):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM requests WHERE status='pending'").fetchone():
                raise ProviderFailure("pending_or_orphan_request")
            if db.execute("SELECT 1 FROM requests WHERE context=? AND body_sha256=?", (context, body_sha256)).fetchone():
                raise ProviderFailure("duplicate_request")
            row = db.execute("INSERT INTO requests(context,body_sha256,status) VALUES(?,?,'pending')",
                             (context, body_sha256))
            db.commit()
            return row.lastrowid

    def start_attempt(self, request_id, ordinal, record):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone() != ("pending",):
                raise ProviderFailure("request_not_pending")
            row = db.execute("INSERT INTO attempts(request_id,ordinal,status,record) VALUES(?,?,'pending',?)",
                             (request_id, ordinal, frame(record).decode()))
            db.commit()
            return row.lastrowid

    def finish_attempt(self, attempt, record):
        with self.connect() as db:
            changed = db.execute("UPDATE attempts SET status='terminal',record=? WHERE id=? AND status='pending'",
                                 (frame(record).decode(), attempt)).rowcount
            if changed != 1:
                raise ProviderFailure("attempt_already_terminal")
            db.commit()

    def finish_request(self, request_id, status):
        if status not in {"completed", "failed"}:
            raise ValueError("invalid request status")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM attempts WHERE request_id=? AND status='pending'", (request_id,)).fetchone():
                raise ProviderFailure("attempt_still_pending")
            changed = db.execute("UPDATE requests SET status=? WHERE id=? AND status='pending'",
                                 (status, request_id)).rowcount
            if changed != 1:
                raise ProviderFailure("request_already_terminal")
            db.commit()

    def records(self, context=None):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            query = "SELECT a.id,a.request_id,a.ordinal,a.status,a.record FROM attempts a"
            values = ()
            if context is not None:
                query += " JOIN requests r ON r.id=a.request_id WHERE r.context=?"
                values = (context,)
            query += " ORDER BY a.id"
            return [{"id": row[0], "request_id": row[1], "ordinal": row[2], "status": row[3],
                     **json.loads(row[4])} for row in db.execute(query, values)]

    def cooldown(self):
        return max((r.get("retry_at", 0) for r in self.records()), default=0)


class HTTPSProvider:
    fixture = False

    def __init__(self, base_url, model, directory, *, authorize=False, stop_path=None):
        if not authorize:
            raise ProviderFailure("authorization_required")
        if not isinstance(base_url, str) or any(c.isspace() or ord(c) < 32 for c in base_url):
            raise ProviderFailure("invalid_fixed_endpoint_or_model")
        url = urlsplit(base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment
                or url.path.rstrip("/") != "/v1" or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", model)):
            raise ProviderFailure("invalid_fixed_endpoint_or_model")
        key = os.environ.get("API_KEY", "")
        if not key or any(c in key for c in "\r\n") or not key.isascii():
            raise ProviderFailure("credential_unavailable")
        if key in base_url or key in model:
            raise ProviderFailure("unsafe_configuration")
        self._key = key
        self.host, self.port, self.model = url.hostname, url.port or 443, model
        self.directory = Path(directory).resolve()
        self.stop_path = Path(stop_path) if stop_path is not None else self.directory / "STOP"
        self.policy = {"endpoint": base_url.rstrip("/") + "/responses", "model": model,
                       "attempts": 4, "backoff_seconds": [2, 4, 8], "jitter_seconds": 0.25,
                       "attempt_seconds": 40, "request_bytes": 262144, "response_bytes": 4194304,
                       "fixture": self.fixture, "cost_usd": None, "concurrency": 1}
        self.ledger = AttemptLedger(self.directory / "attempts.sqlite3", self.policy)

    def stopped(self):
        return self.stop_path.exists()

    def accounting(self, context):
        rows = self.ledger.records(context)
        return {"fixture": self.fixture, "transport_attempts": len(rows),
                "submitted_or_uncertain": sum(r["status"] == "pending" or r.get("request_may_have_been_sent", False)
                                             for r in rows),
                "unknown_usage_attempts": sum(r.get("usage_state") == "unknown" for r in rows),
                "reported_input_tokens": sum((r.get("usage") or {}).get("input_tokens", 0) for r in rows),
                "reported_output_tokens": sum((r.get("usage") or {}).get("output_tokens", 0) for r in rows),
                "cost_usd": None}

    def wait(self, delay, deadline):
        end = time.monotonic() + delay
        if end >= deadline:
            raise ProviderFailure("retry_wait_exceeds_deadline")
        while time.monotonic() < end:
            if self.stopped():
                raise ProviderFailure("operator_stop")
            time.sleep(min(0.1, end - time.monotonic()))

    def _attempt(self, body, timeout, observation):
        async def exchange():
            transport = httpx.AsyncHTTPTransport(verify=ssl.create_default_context(),
                                                trust_env=False, retries=0)
            try:
                async with httpx.AsyncClient(transport=transport, trust_env=False,
                                             follow_redirects=False, timeout=timeout) as client:
                    # Conservative until a connect-only failure proves no request was sent.
                    observation["request_may_have_been_sent"] = True
                    async with client.stream("POST", self.policy["endpoint"], content=body,
                            headers={"Authorization": "Bearer " + self._key,
                                     "Content-Type": "application/json", "Accept-Encoding": "identity"}) as response:
                        observation["http_status"] = response.status_code
                        chunks, total = [], 0
                        async for chunk in response.aiter_raw():
                            total += len(chunk)
                            observation["response_body_bytes_observed"] = total
                            if total > self.policy["response_bytes"]:
                                raise ProviderFailure("response_byte_limit")
                            chunks.append(chunk)
                        observation["response_complete"] = True
                        return response.status_code, response.headers.get("Retry-After"), b"".join(chunks)
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                observation["request_may_have_been_sent"] = False
                pending, seen = [error], set()
                while pending:
                    cause = pending.pop()
                    if cause is None or id(cause) in seen:
                        continue
                    seen.add(id(cause))
                    if isinstance(cause, ssl.SSLError):
                        raise ProviderFailure("tls_failure") from None
                    pending.extend((cause.__cause__, cause.__context__))
                raise ProviderFailure("network_failure") from None
            except httpx.TransportError:
                raise ProviderFailure("network_failure") from None

        async def interruptible():
            deadline = time.monotonic() + timeout
            task = asyncio.create_task(exchange())
            try:
                while True:
                    await asyncio.wait({task}, timeout=0.05)
                    if self.stopped():
                        raise ProviderFailure("operator_stop")
                    if time.monotonic() >= deadline:
                        raise ProviderFailure("attempt_deadline")
                    if task.done():
                        return await task
            finally:
                if not task.done():
                    task.cancel()
                    # Join cancellation/connection cleanup before any retry can start.
                    await asyncio.gather(task, return_exceptions=True)

        return asyncio.run(interruptible())

    def respond(self, context_id, request, *, timeout=180):
        if not isinstance(context_id, str) or not context_id or len(context_id) > 256 or self._key in context_id:
            raise ProviderFailure("unsafe_context")
        if (request.get("model") != self.model or request.get("store") is not False
                or "previous_response_id" in request or "conversation" in request):
            raise ProviderFailure("request_binding_mismatch")
        body = frame(request)
        if self._key.encode() in body or len(body) > self.policy["request_bytes"]:
            raise ProviderFailure("unsafe_request_body")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ProviderFailure("invalid_deadline")
        if self.stopped():
            raise ProviderFailure("operator_stop")
        request_id = self.ledger.begin(context_id, hashlib.sha256(body).hexdigest())
        deadline = time.monotonic() + timeout
        try:
            cooldown = self.ledger.cooldown() - time.time()
            if cooldown > 0:
                self.wait(cooldown, deadline)
            for ordinal in range(1, self.policy["attempts"] + 1):
                if self.stopped():
                    raise ProviderFailure("operator_stop")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderFailure("total_deadline")
                observation = {"started": time.time(), "request_body_bytes": len(body),
                    "request_sha256": hashlib.sha256(body).hexdigest(),
                    "request_may_have_been_sent": False, "response_body_bytes_observed": 0,
                    "response_complete": False, "http_status": None, "usage": None,
                    "usage_state": "unknown", "cost_usd": None}
                attempt = self.ledger.start_attempt(request_id, ordinal, observation)
                retryable = False
                retry_after = None
                response = None
                try:
                    status, retry_after, raw = self._attempt(
                        body, min(remaining, self.policy["attempt_seconds"]), observation)
                    if self._key.encode() in raw:
                        raise ProviderFailure("credential_echo")
                    # Standard JSON decoder plus strict re-serialization rejects nonfinite values.
                    try:
                        response = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        if status == 200:
                            raise
                        response = {}
                    if self._key.encode() in frame(response):
                        raise ProviderFailure("credential_echo")
                    observation["response_sha256"] = hashlib.sha256(raw).hexdigest()
                    observation["response_json_sha256"] = hashlib.sha256(frame(response)).hexdigest()
                    usage = response.get("usage") if isinstance(response, dict) else None
                    if (isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0
                                                     for k in ("input_tokens", "output_tokens"))):
                        observation["usage"] = usage
                        observation["usage_state"] = "reported"
                    if status != 200:
                        error = response.get("error", {}) if isinstance(response, dict) else {}
                        quota = isinstance(error, dict) and any(error.get(k) in QUOTA_ERRORS for k in ("code", "type"))
                        retryable = status in RETRYABLE and not quota
                        observation["reason"] = "quota_action_required" if quota else "http_status"
                    else:
                        reported = response.get("model") if isinstance(response, dict) else None
                        if isinstance(reported, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", reported):
                            observation["reported_model"] = reported
                        if not isinstance(response, dict) or response.get("model") != self.model:
                            raise ProviderFailure("reported_model_mismatch")
                        output_items(response)
                        observation["reason"] = "completed"
                except ssl.SSLError:
                    observation["reason"] = "tls_failure"
                except ProviderFailure as error:
                    observation["reason"] = error.reason
                    retryable = error.reason in {"attempt_deadline", "network_failure"}
                except (OSError, http.client.HTTPException):
                    observation["reason"] = "network_failure"
                    retryable = True
                except (ValueError, TypeError):
                    observation["reason"] = "invalid_response"
                if self.stopped():
                    observation["reason"], retryable = "operator_stop", False
                if not observation["request_may_have_been_sent"]:
                    observation["usage_state"] = "not_sent"
                if retryable:
                    backoff = self.policy["backoff_seconds"][min(ordinal - 1, 2)]
                    delay = retry_delay(retry_after, backoff, time.time()) + random.uniform(0, self.policy["jitter_seconds"])
                    observation["retry_delay"] = delay
                    observation["retry_at"] = time.time() + delay
                observation["finished"] = time.time()
                self.ledger.finish_attempt(attempt, observation)
                if observation["reason"] == "completed":
                    self.ledger.finish_request(request_id, "completed")
                    return response
                if not retryable or ordinal == self.policy["attempts"]:
                    raise ProviderFailure(observation["reason"])
                self.wait(observation["retry_delay"], deadline)
            raise AssertionError("attempt loop exhausted without terminal result")
        except Exception:
            self.ledger.finish_request(request_id, "failed")
            raise
