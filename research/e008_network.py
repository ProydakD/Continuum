"""Read-only, hash-bound offsets into one serial provider journal.

Index once; load only a selected context's lines for its independent raw audit.
The index is not trusted persistent state and cannot authorize a model request.
"""
from collections import defaultdict
import hashlib
import json

from .common import digest


def context_span(path, offset, worker):
    """Seal only the just-finished serial context, never re-read its prefix."""
    size = path.stat().st_size if path.exists() else 0
    if type(offset) is not int or not 0 <= offset <= size:
        raise PermissionError("provider journal shrank or invalid start offset")
    raw = b""
    if path.exists():
        with path.open("rb") as stream:
            stream.seek(offset)
            raw = stream.read(size - offset)
    proof = {"offset": offset, "length": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "worker": worker}
    _context_events(raw, worker)
    return proof


def _context_events(raw, worker):
    if raw and not raw.endswith(b"\n"):
        raise PermissionError("partial context network event")
    events, attempts = [], set()
    for line in raw.splitlines():
        event = json.loads(line)
        if event.get("event") == "request_failed":
            if event["attempt"] not in attempts:
                raise PermissionError("foreign failed attempt in context span")
        elif event.get("worker") != worker:
            raise PermissionError("foreign network event in context span")
        if event.get("event") == "request_started":
            attempts.add(event["attempt"])
        events.append(event)
    return events


def span_events(path, proof, worker):
    if (proof["worker"] != worker or type(proof["offset"]) is not int or proof["offset"] < 0
            or type(proof["length"]) is not int or proof["length"] < 0):
        raise PermissionError("invalid context network binding")
    if not path.exists():
        raw = b""
        if proof["offset"] or proof["length"]:
            raise PermissionError("context provider trace disappeared")
    else:
        with path.open("rb") as stream:
            stream.seek(proof["offset"])
            raw = stream.read(proof["length"])
    if len(raw) != proof["length"] or hashlib.sha256(raw).hexdigest() != proof["sha256"]:
        raise PermissionError("original context provider bytes changed")
    return _context_events(raw, worker)


class NetworkIndex:
    def __init__(self, path):
        self.path = path
        self.entries = defaultdict(list)
        attempts = {}
        whole = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                offset = stream.tell()
                raw = stream.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    raise ValueError("partial provider journal line")
                event = json.loads(raw)
                whole.update(raw)
                worker = event.get("worker")
                if event.get("event") == "request_started":
                    if event["attempt"] in attempts:
                        raise ValueError("duplicate provider attempt")
                    attempts[event["attempt"]] = worker
                elif event.get("event") == "request_failed":
                    if event["attempt"] not in attempts:
                        raise ValueError("unbound failed attempt")
                    worker = attempts[event["attempt"]]
                self.entries[worker].append((offset, len(raw), hashlib.sha256(raw).hexdigest()))
            self.size = stream.tell()
        self.sha256 = whole.hexdigest()

    def worker(self, identity):
        """Byte changes, even same-sized edits, invalidate the selected audit."""
        with self.path.open("rb") as stream:
            for offset, length, sha in self.entries.get(identity, []):
                stream.seek(offset)
                raw = stream.read(length)
                if hashlib.sha256(raw).hexdigest() != sha:
                    raise PermissionError("indexed provider bytes changed")
                yield json.loads(raw)

    def all(self):
        """Verify the complete stream while reading; caller must exhaust it."""
        whole = hashlib.sha256()
        count = 0
        with self.path.open("rb") as stream:
            for raw in stream:
                whole.update(raw)
                count += len(raw)
                yield json.loads(raw)
        if count != self.size or whole.hexdigest() != self.sha256:
            raise PermissionError("provider journal changed during evaluation")

    def verify(self):
        if self.path.stat().st_size != self.size or digest(self.path) != self.sha256:
            raise PermissionError("provider journal changed after indexing")
