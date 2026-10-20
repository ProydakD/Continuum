"""Read-only, hash-bound offsets into one serial provider journal.

Index once; load only a selected context's lines for its independent raw audit.
The index is not trusted persistent state and cannot authorize a model request.
"""
from collections import defaultdict
import hashlib
import json

from .common import digest


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
