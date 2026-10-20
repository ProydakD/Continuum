import json
from pathlib import Path
import tempfile
import unittest

from research.e008_network import NetworkIndex


class NetworkIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "provider.jsonl"
        self.events = [{"event": "request_started", "attempt": 1, "worker": "one"},
                       {"event": "request_failed", "attempt": 1},
                       {"event": "request_started", "attempt": 2, "worker": "two"},
                       {"event": "response", "attempt": 2, "worker": "two"}]
        self.path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in self.events))

    def test_workerless_failures_are_routed_without_foreign_context(self):
        index = NetworkIndex(self.path)
        self.assertEqual(list(index.worker("one")), self.events[:2])
        self.assertEqual(list(index.worker("two")), self.events[2:])
        self.assertEqual(list(index.all()), self.events)
        index.verify()

    def test_same_length_tampering_invalidates_selected_bytes(self):
        index = NetworkIndex(self.path)
        self.path.write_bytes(self.path.read_bytes().replace(b"one", b"bad"))
        with self.assertRaises(PermissionError):
            list(index.worker("one"))
        with self.assertRaises(PermissionError):
            index.verify()

    def test_append_cannot_disappear_from_frozen_report(self):
        index = NetworkIndex(self.path)
        with self.path.open("ab") as f:
            f.write(b'{"event":"extra"}\n')
        with self.assertRaises(PermissionError):
            list(index.all())

    def test_partial_line_is_not_a_completed_record(self):
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaises(ValueError):
            NetworkIndex(self.path)


if __name__ == "__main__":
    unittest.main()
