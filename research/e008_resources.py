"""E008-only durable admission limits; no resets, refunds or automatic retries."""
from contextlib import closing
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import time

from .e007_provider import MeasuredProvider
from .responses_provider import SpendLedger


class SeriesStopped(PermissionError):
    """A registered stop condition, not a request to retry the same position."""


def resource_policy(jobs):
    ids = [j["id"] for j in jobs]
    if (not ids or len(ids) != len(set(ids)) or any(not isinstance(x, str) for x in ids)
            or set(ids) & {"smoke-primary", "smoke-secondary"}):
        raise ValueError("unique assigned context IDs required")
    return {
        "workers": {**{identity: 10 for identity in ids}, "smoke-primary": 1, "smoke-secondary": 1},
        "maximum_response_attempts": 10 * len(ids) + 2,
        "maximum_metadata_attempts": 3 * len(ids) + 2,
        "series_seconds": 259200, "artifact_bytes": 40 * 1024 ** 3,
        "reserve_bytes": 128 * 1024 ** 2, "request_seconds": 120,
        "output_tokens": 8192, "request_bytes": 262144, "response_bytes": 4194304,
    }


def directory_bytes(path):
    """Fail closed on a symlink/reparse point rather than traversing outside study."""
    total = 0
    for directory, folders, files in os.walk(path, followlinks=False):
        for name in folders + files:
            item = Path(directory) / name
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise SeriesStopped("study contains a redirected filesystem entry")
        total += sum((Path(directory) / name).stat().st_size for name in files)
    return total


class SeriesLedger(SpendLedger):
    """Reuse the spend/event ledger with a shared durable technical policy.

    Space is admission-controlled before every context/request, not an OS quota.
    Response/message envelopes bound the admitted operation; existing output is
    retained if a gate closes. A pending request blocks all further network use.
    """

    def __init__(self, study, policy):
        self.study = Path(study).resolve(strict=True)
        if (not isinstance(policy.get("workers"), dict) or not policy["workers"]
                or any(not isinstance(k, str) or type(v) is not int or v <= 0 for k, v in policy["workers"].items())):
            raise ValueError("positive per-context request ceilings required")
        if any(type(v) is not int or v <= 0 for k, v in policy.items() if k != "workers"):
            raise ValueError("positive integer resource ceilings required")
        if policy["request_bytes"] != 262144 or policy["response_bytes"] != 4194304 or policy["output_tokens"] > 8192:
            raise ValueError("transport ceilings differ from the frozen implementation")
        self.limits = json.loads(json.dumps(policy))
        self.encoded_limits = json.dumps(self.limits, sort_keys=True)
        super().__init__(self.study / "provider-ledger.sqlite3", unbounded=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS runtime_policy(value TEXT NOT NULL, started REAL, last_wall REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS metadata_attempts(id INTEGER PRIMARY KEY, started REAL, outcome TEXT)")
            prior = db.execute("SELECT value FROM runtime_policy").fetchone()
            if prior and prior[0] != self.encoded_limits:
                raise PermissionError("cannot change registered technical limits on resume")
            if not prior:
                db.execute("INSERT INTO runtime_policy(value) VALUES(?)", (self.encoded_limits,))
            db.commit()
        self.monotonic_anchor = time.monotonic()
        self.wall_anchor = time.time()

    def start(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT started FROM runtime_policy").fetchone()
            if row[0] is None:
                now = time.time()
                db.execute("UPDATE runtime_policy SET started=?, last_wall=?", (now, now))
            db.commit()
        return self.remaining()

    def remaining(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            encoded, started, last_wall = db.execute("SELECT value,started,last_wall FROM runtime_policy").fetchone()
            if encoded != self.encoded_limits or json.dumps(self.limits, sort_keys=True) != self.encoded_limits:
                raise SeriesStopped("technical policy changed")
            if started is None:
                raise SeriesStopped("series clock not started")
            now = time.time()
            if not math.isfinite(now) or now < last_wall:
                raise SeriesStopped("wall clock moved backwards")
            elapsed = max(now, self.wall_anchor + time.monotonic() - self.monotonic_anchor) - started
            db.execute("UPDATE runtime_policy SET last_wall=?", (now,))
            db.commit()
        if (self.study / "STOP").exists():
            raise SeriesStopped("operator STOP")
        remaining = self.limits["series_seconds"] - elapsed
        if remaining <= 0:
            raise SeriesStopped("registered series deadline")
        return remaining

    def check_space(self):
        used = directory_bytes(self.study)
        reserve = self.limits["reserve_bytes"]
        if used + reserve > self.limits["artifact_bytes"]:
            raise SeriesStopped("artifact ceiling including next-operation reserve")
        if shutil.disk_usage(self.study).free < reserve:
            raise SeriesStopped("insufficient free space for next-operation reserve")
        return used

    @staticmethod
    def require_no_pending(db):
        if (db.execute("SELECT 1 FROM attempts WHERE outcome='pending'").fetchone()
                or db.execute("SELECT 1 FROM metadata_attempts WHERE outcome='pending'").fetchone()):
            raise SeriesStopped("pending or orphan network outcome; never retry automatically")

    def check_context(self):
        remaining = self.remaining()
        self.check_space()
        with closing(sqlite3.connect(self.path)) as db:
            self.require_no_pending(db)
        return remaining

    def reserve(self, worker):
        self.remaining()
        self.check_space()
        if worker not in self.limits["workers"]:
            raise SeriesStopped("network request from an unregistered context")
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_no_pending(db)
            total = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            local = db.execute("SELECT COUNT(*) FROM attempts WHERE worker=?", (worker,)).fetchone()[0]
            if total >= self.limits["maximum_response_attempts"] or local >= self.limits["workers"][worker]:
                raise SeriesStopped("registered response attempt ceiling")
            cursor = db.execute("INSERT INTO attempts(worker,started,reserved,outcome) VALUES(?,?,?,?)",
                                (worker, time.time(), "0", "pending"))
            db.commit()
            return cursor.lastrowid

    def reserve_metadata(self):
        self.check_context()
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_no_pending(db)
            total = db.execute("SELECT COUNT(*) FROM metadata_attempts").fetchone()[0]
            if total >= self.limits["maximum_metadata_attempts"]:
                raise SeriesStopped("registered metadata attempt ceiling")
            cursor = db.execute("INSERT INTO metadata_attempts(started,outcome) VALUES(?,?)", (time.time(), "pending"))
            db.commit()
            return cursor.lastrowid

    def finish(self, attempt, outcome, usage=None):
        self._finish("attempts", attempt, outcome, usage)

    def finish_metadata(self, attempt, outcome):
        self._finish("metadata_attempts", attempt, outcome)

    def _finish(self, table, attempt, outcome, usage=None):
        if outcome not in ("completed", "failed_or_unknown"):
            raise ValueError("invalid terminal network outcome")
        with closing(sqlite3.connect(self.path)) as db:
            if table == "attempts":
                changed = db.execute("UPDATE attempts SET outcome=?,usage=? WHERE id=? AND outcome='pending'",
                                     (outcome, json.dumps(usage), attempt)).rowcount
            else:
                changed = db.execute("UPDATE metadata_attempts SET outcome=? WHERE id=? AND outcome='pending'",
                                     (outcome, attempt)).rowcount
            if changed != 1:
                raise SeriesStopped("cannot rewrite terminal or nonexistent network outcome")
            db.commit()


class BoundedProvider(MeasuredProvider):
    """Existing measured HTTPS transport plus E008-only durable admission."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(self.ledger, SeriesLedger):
            raise TypeError("E008 durable series ledger required")

    def respond(self, worker, history, tools, timeout=120, *, max_output_tokens=8192):
        if type(max_output_tokens) is not int or max_output_tokens > self.ledger.limits["output_tokens"]:
            raise SeriesStopped("unregistered output-token ceiling")
        return super().respond(worker, history, tools, timeout=timeout, max_output_tokens=max_output_tokens)

    def request(self, method, endpoint, payload=None, timeout=120):
        metadata = (method, endpoint) == ("GET", "/v1/models")
        if not metadata and (method, endpoint) != ("POST", "/v1/responses"):
            raise PermissionError("unregistered endpoint")
        if payload is not None and len(json.dumps(payload, ensure_ascii=False).encode()) > self.ledger.limits["request_bytes"]:
            raise SeriesStopped("actual request bytes exceed ceiling")
        remaining = self.ledger.remaining()
        timeout = min(timeout, self.ledger.limits["request_seconds"], remaining)
        if timeout <= 0:
            raise SeriesStopped("nonpositive request deadline")
        if not metadata:
            with closing(sqlite3.connect(self.ledger.path)) as db:
                pending = db.execute("SELECT worker FROM attempts WHERE outcome='pending'").fetchall()
            if pending != [(getattr(self, "current_worker", None),)]:
                raise SeriesStopped("HTTP response request lacks its durable reservation")
        attempt = self.ledger.reserve_metadata() if metadata else None
        outcome = "failed_or_unknown"
        try:
            result = super().request(method, endpoint, payload, timeout)
            outcome = "completed"
            return result
        finally:
            if attempt is not None:
                self.ledger.finish_metadata(attempt, outcome)


def provider_failure_action(failure_type, http_status):
    """Use observed transport status/type, never model text or exception substrings."""
    if failure_type in ("SSLError", "SSLCertVerificationError", "PermissionError", "SeriesStopped"):
        return "stop"
    if http_status is not None:
        return "recover_next_position" if http_status in (429, 502, 503, 504) else "stop"
    if failure_type in ("TimeoutError", "ConnectionError", "ConnectionResetError", "ConnectionRefusedError",
                        "BrokenPipeError", "RemoteDisconnected", "gaierror"):
        return "recover_next_position"
    return "stop"
