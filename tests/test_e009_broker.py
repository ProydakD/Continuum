"""Budget, capability, private-channel and byte-parser regression tests."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from continuum.store import Store
from research.e009_broker import MemoryBroker, frame, parse_frame, read_envelope, read_size
from research.e009_episode import make_episode
from research.e009_revision import sha
from research.e009_sources import EvidenceRegistry, evidence_catalog


class LocalTransport:
    def __init__(self, path, actor):
        self.store = Store(path, actor=actor, scope="lab",
                           origin={"model_declared": "fixture", "run_id": "unit", "role": "worker"})

    def tool(self, name, **args):
        return getattr(self.store, name)(**args)


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "state.sqlite3"
        catalog = evidence_catalog(make_episode(43, "unit"))
        self.registry = EvidenceRegistry(catalog, sha(catalog))

    def broker(self, stage="A", condition="F1", **kwargs):
        actor = "unit:" + stage
        return MemoryBroker(LocalTransport(self.db, actor), stage, condition, actor, self.registry, **kwargs)

    def test_read_limit_includes_origin_and_transport_wrapper(self):
        value = read_envelope({"format": "F", "payload": "knowledge"}, "A", "a" * 64,
                              {"actor": "previous-instance", "model_declared": "fixture"})
        self.assertGreater(read_size(value), len(b"knowledge"))

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b"{}",
                    b"[" * 262145, b'{"x":"\xff"}\n'):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                parse_frame(raw)
        with self.assertRaises(ValueError):
            frame({"x": float("nan")})

    def test_unicode_count_is_actual_utf8_not_characters(self):
        value = {"result": {"memory": "я" * 100}}
        self.assertEqual(frame(value).decode().count("я"), 100)
        self.assertEqual(len(frame(value)) - len(frame(value).decode()), 100)

    def test_unknown_or_hash_selected_read_is_denied(self):
        broker = self.broker()
        for name, arguments in (("get_object", {}), ("read_memory", {"sha256": "a" * 64}),
                                ("shell", {"command": "do not execute"})):
            with self.assertRaises(PermissionError):
                broker.call(name, arguments)
        self.assertEqual(broker.reads, 0)

    def test_publication_requires_explicit_memory_and_prior_read(self):
        broker = self.broker()
        with self.assertRaises(PermissionError):
            broker.call("publish", {"measurement": {}})
        with self.assertRaises(PermissionError):
            broker.publish({"format": "F", "payload": "x"}, {})
        broker.call("read_memory", {})
        with self.assertRaises(ValueError):
            broker.publish({"format": "S", "payload": []}, {})

    def test_metadata_overflow_does_not_commit_pointer(self):
        broker = self.broker(budget=600)
        broker.call("read_memory", {})
        result = broker.publish({"format": "F", "payload": "x" * 500}, {"private": "secret"})
        self.assertFalse(result["saved"])
        self.assertGreater(result["read_bytes"], 600)
        self.assertFalse(broker.committed)
        self.assertEqual(broker.transport.tool("get_task", task_id=broker.task["id"])["result"], "")
        # Retry fits; the orphan object does not consume a checkpoint or overwrite it.
        self.assertTrue(broker.publish({"format": "F", "payload": "x"}, {})["saved"])

    def test_private_measurement_not_in_successor_read_or_receipt(self):
        first = self.broker()
        first.call("read_memory", {})
        receipt = first.publish({"format": "F", "payload": "only-public"},
                                {"private_canary": "PRIVATE-DO-NOT-FORWARD"})
        self.assertNotIn("measurement", json.dumps(receipt))
        second = self.broker("B", task_id=first.task["id"])
        result = second.call("read_memory", {})
        self.assertEqual(result["memory"]["payload"], "only-public")
        self.assertEqual(result["origin"]["actor"], "unit:A")
        self.assertNotIn("PRIVATE", json.dumps(result))
        with self.assertRaises(PermissionError):
            second.call("read_memory", {})

    def test_c0_withholds_previous_publication(self):
        first = self.broker(condition="C0")
        first.call("read_memory", {})
        first.publish({"format": "F", "payload": "not inherited"}, {})
        second = self.broker("B", condition="C0", task_id=first.task["id"])
        result = second.call("read_memory", {})
        self.assertIsNone(result["memory"])
        self.assertIsNone(result["sha256"])

    def test_stage_order_and_duplicate_commit_rejected(self):
        first = self.broker()
        first.call("read_memory", {})
        first.publish({"format": "F", "payload": "x"}, {})
        with self.assertRaises(PermissionError):
            first.publish({"format": "F", "payload": "y"}, {})
        with self.assertRaises(ValueError):
            self.broker("C", task_id=first.task["id"])
        with self.assertRaises(ValueError):
            self.broker("A", task_id=first.task["id"])

    def test_verifier_condition_and_quota(self):
        off = self.broker(condition="F0")
        with self.assertRaises(PermissionError):
            off.call("verify_references", {"claims": []})
        for _ in range(3):
            self.assertFalse(off.call("verify_source", {"record": {"id": "future"}})["valid"])
        with self.assertRaises(PermissionError):
            off.call("verify_source", {"record": {"id": "future"}})

    def test_storage_size_preflight_keeps_no_commit(self):
        broker = self.broker()
        broker.call("read_memory", {})
        with self.assertRaises(ValueError):
            broker.publish({"format": "F", "payload": "x"}, {"oversize": "x" * 65536})
        self.assertFalse(broker.committed)

    def test_atomic_index_references_both_objects(self):
        broker = self.broker()
        broker.call("read_memory", {})
        broker.publish({"format": "F", "payload": "public"}, {"claims": []})
        index = json.loads(broker.task["result"])
        for name in ("memory_sha256", "measurement_sha256"):
            value = broker.transport.tool("get_object", sha256=index[name])
            self.assertTrue(base64.b64decode(value["content_base64"], validate=True))

    def test_exponent_overflow_is_not_a_json_number(self):
        with self.assertRaises(ValueError):
            parse_frame(b'{"x":1e999}\n')

    def test_condition_cannot_change_on_existing_task(self):
        first = self.broker(condition="F1")
        first.call("read_memory", {})
        first.publish({"format": "F", "payload": "x"}, {})
        with self.assertRaises(ValueError):
            self.broker("B", condition="F0", task_id=first.task["id"])

    def test_e_is_readonly_after_complete_chain(self):
        task_id = None
        for stage in "ABCD":
            broker = self.broker(stage, task_id=task_id)
            broker.call("read_memory", {})
            broker.publish({"format": "F", "payload": stage}, {})
            task_id = broker.task["id"]
        last = self.broker("E", task_id=task_id)
        self.assertEqual(last.call("read_memory", {})["memory"]["payload"], "D")
        with self.assertRaises(PermissionError):
            last.publish({"format": "F", "payload": "E"}, {})

    def test_seed_metadata_counts_against_read_limit(self):
        with self.assertRaises(ValueError):
            self.broker(seed={"format": "F", "payload": "x" * 500}, budget=600)


if __name__ == "__main__":
    unittest.main()
