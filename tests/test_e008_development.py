import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from research.e003 import Jobs
from research.e008_development import DevelopmentBridge, development_input, development_prompt, training_projection
from research.e008_execute import ledger_key, ledger_record


def job(role="designer", version=1, lineage="L1"):
    return {"id": "unit", "role": role, "version": version, "lineage": lineage, "condition": "T2",
            "stage": "A" if role == "designer" else "B", "world": None}


class DevelopmentTests(unittest.TestCase):
    def bridge(self, assigned=None):
        assigned = assigned or job()
        bridge = DevelopmentBridge.__new__(DevelopmentBridge)
        bridge.actor = "unit:" + assigned["stage"]
        bridge.index = Mock(return_value=(None, {}))
        bridge.configure(assigned)
        bridge.get = Mock(return_value=development_input(assigned, [], 2048))
        bridge.put = Mock(return_value="saved-sha")
        bridge.tool = Mock(return_value={"id": "claim", "revision": 1})
        return bridge

    def test_training_projection_never_serializes_truth_or_canary(self):
        world = {"split": "training", "truth": "hidden", "private_canary": "hidden", "id": "training-relay-01",
                 "evidence": [], "panel": [], "successor": []}
        gold = {"subsets": {k: {"questions": {}} for k in ("EA", "EA+EB", "EA+EB+EC")}}
        visible = training_projection(world, gold, "example-01")
        self.assertNotIn("truth", visible)
        self.assertNotIn("private_canary", visible)
        self.assertNotIn("id", visible)
        with self.assertRaises(PermissionError):
            training_projection(dict(world, split="test"), gold, "example-01")

    def test_foreign_or_future_protocol_cannot_enter_development_input(self):
        assigned = job(version=2)
        for version in ("L2-v1", "L1-v2", "L1-v3"):
            with self.assertRaises(PermissionError):
                development_input(assigned, [], 2048, protocol={"version": version})
        self.assertEqual(development_input(assigned, [], 2048, protocol={"version": "L1-v1"})["prior_protocol"]["version"], "L1-v1")

    def test_arbitrary_binary_protocol_is_stored_not_executed(self):
        bridge = self.bridge()
        bridge.call("read_development", {})
        body = base64.b64encode(b"\x00\xffmachine-native-not-a-JSON-schema").decode()
        result = bridge.call("publish_protocol", {"body": body, "encoding": "base64", "reason": "fixture"})
        self.assertTrue(result["saved"])
        self.assertEqual(bridge.put.call_args.args[1]["body"], body)
        bridge.finish({"save_status": "saved", "summary": "fixture"})
        with self.assertRaises(PermissionError):
            bridge.call("run_shell", {"command": "not executed"})

    def test_rejection_and_single_repair_keep_transition_bound(self):
        bridge = self.bridge()
        with self.assertRaises(ValueError):
            bridge.call("publish_protocol", {"body": "small", "encoding": "utf8", "reason": "fixture"})
        bridge.call("read_development", {})
        self.assertFalse(bridge.call("publish_protocol", {"body": "x" * 8193, "encoding": "utf8", "reason": "fixture"})["saved"])
        self.assertTrue(bridge.call("publish_protocol", {"body": "small", "encoding": "utf8", "reason": "fixture"})["saved"])
        with self.assertRaises(ValueError):
            bridge.call("publish_protocol", {"body": "third", "encoding": "utf8", "reason": "fixture"})
        bridge.put.assert_called_once()

    def test_critic_cannot_modify_protocol_or_hide_extra_input(self):
        bridge = self.bridge(job("critic"))
        supplied = bridge.get.return_value
        bridge.get.return_value = dict(supplied, hidden_oracle="not allowed")
        with self.assertRaises(PermissionError):
            bridge.call("read_development", {})
        bridge = self.bridge(job("critic"))
        bridge.call("read_development", {})
        with self.assertRaises(PermissionError):
            bridge.call("publish_protocol", {"body": "overwrite", "encoding": "utf8", "reason": "fixture"})
        self.assertTrue(bridge.call("publish_review", {"content": "Retain alternatives."})["saved"])

    def test_prompt_does_not_force_internal_schema_or_include_world(self):
        text = development_prompt(job())
        self.assertIn("NOT required to use JSON", text)
        self.assertNotIn("PUBLIC_INPUT:", text)
        self.assertNotIn('"truth"', text)

    def test_existing_job_ledger_accepts_development_and_keeps_terminal_immutable(self):
        assigned = [job(), dict(job("critic"), id="unit2")]
        with tempfile.TemporaryDirectory() as directory:
            ledger = Jobs(Path(directory) / "jobs.sqlite3", [ledger_record(j) for j in assigned])
            self.assertEqual(len(ledger.state()), 2)
            ledger.claim(ledger_key(assigned[0]))
            ledger.finish(ledger_key(assigned[0]), {"status": "completed"})
            with self.assertRaises(RuntimeError):
                ledger.claim(ledger_key(assigned[0]))
            ledger.claim(ledger_key(assigned[1]))
            ledger.finish(ledger_key(assigned[1]), {"status": "failed"})


if __name__ == "__main__":
    unittest.main()
