"""Controller protocol and assignment regressions before live provider use."""
import json
import unittest

from research.e009_broker import read_size
from research.e009_protocol import assigned_seed, fresh_history, output_items, public_input, request_body
from research.e009_revision import sha
import test_e009_broker


class ControllerTests(unittest.TestCase):
    def test_new_context_contains_only_registered_public_input(self):
        public = {"stage": "B", "world_id": "fixture", "memory": None}
        history = fresh_history(public)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(json.loads(history[0]["content"]), public)
        public["leak"] = "later mutation"
        self.assertNotIn("leak", history[0]["content"])

    def test_request_never_carries_server_side_conversation_id(self):
        request = request_body("assigned-model", fresh_history({"stage": "A"}), "A", "F1", 16000)
        self.assertFalse(request["store"])
        self.assertFalse(request["parallel_tool_calls"])
        self.assertNotIn("previous_response_id", request)
        self.assertNotIn("conversation", request)
        self.assertEqual(request["model"], "assigned-model")

    def test_preserve_all_reasoning_and_phase_items_in_same_context(self):
        response = {"status": "completed", "output": [
            {"type": "reasoning", "encrypted_content": "opaque"},
            {"type": "message", "phase": "final_answer", "role": "assistant", "content": []}]}
        self.assertEqual(output_items(response), response["output"])
        copy = output_items(response)
        copy[0]["encrypted_content"] = "changed"
        self.assertEqual(response["output"][0]["encrypted_content"], "opaque")

    def test_incomplete_or_unregistered_output_is_not_completion(self):
        for response in ({"status": "incomplete", "output": []},
                         {"status": "completed", "output": [{"type": "shell_call"}]},
                         {"status": "completed", "output": []}):
            with self.subTest(response=response), self.assertRaises(ValueError):
                output_items(response)

    def test_multiple_tool_calls_rejected_under_serial_contract(self):
        call = {"type": "function_call", "name": "read_memory", "call_id": "1", "arguments": "{}"}
        with self.assertRaises(ValueError):
            output_items({"status": "completed", "output": [call, call]})

    def test_verifier_available_only_in_registered_factor(self):
        for condition in ("F0", "S0", "C0", "FULL-JOURNAL", "F1", "S1"):
            request = request_body("fixture", [], "E", condition, 16000)
            names = {t["name"] for t in request["tools"]}
            self.assertEqual("verify_references" in names, condition in {"F1", "S1"})
            self.assertNotIn("publish", names)
            self.assertIn("hash_claims", names)


class AssignedBrokerTests(unittest.TestCase):
    setUp = test_e009_broker.BrokerTests.setUp
    broker = test_e009_broker.BrokerTests.broker
    def test_episode_track_and_catalog_binding_cannot_change(self):
        assignment = {"episode": "one", "track": "controlled", "catalog_sha256": "a" * 64}
        first = self.broker(assignment=assignment)
        first.call("read_memory", {})
        first.publish({"format": "F", "payload": "x"}, {})
        assignment["episode"] = "mutated caller"
        for key in ("episode", "track", "catalog_sha256"):
            changed = dict(first.assignment); changed[key] = "changed"
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.broker("B", task_id=first.task["id"], assignment=changed)

    def test_full_journal_contains_publications_not_private_measurements(self):
        task_id = None
        for stage in "ABCD":
            broker = self.broker(stage, condition="FULL-JOURNAL", task_id=task_id)
            broker.call("read_memory", {})
            broker.publish({"format": "F", "payload": stage + "x" * 3000}, {"private": "NEVER-PUBLIC"})
            task_id = broker.task["id"]
        last = self.broker("E", condition="FULL-JOURNAL", task_id=task_id)
        value = last.call("read_memory", {})
        self.assertEqual([item["stage"] for item in value["journal"]], list("ABCD"))
        self.assertGreater(read_size(value), 8192)
        self.assertNotIn("NEVER-PUBLIC", json.dumps(value))

    def test_hash_tool_uses_supplied_values_only_and_counts_calls(self):
        broker = self.broker()
        claims = [{"id": "H", "value": 1}, {"id": "H", "value": True}]
        result = broker.call("hash_claims", {"claims": claims})
        self.assertEqual(result["sha256"], [sha(c) for c in claims])
        self.assertNotEqual(*result["sha256"])
        broker.call("hash_claims", {"claims": []})
        broker.call("hash_claims", {"claims": []})
        with self.assertRaises(PermissionError):
            broker.call("hash_claims", {"claims": []})

    def test_public_projection_and_seed_never_include_private_truth(self):
        from research.e009_episode import make_episode
        episode = make_episode(43, "projection")
        for stage in "ABCDE":
            public = public_input(episode, self.registry, stage, "F1", "controlled")
            self.assertIsNone(public["memory"])
            self.assertNotIn("hidden_model", public)
            self.assertNotIn("design_audit", public)
            self.assertEqual("question" in public, stage == "E")
            self.assertEqual(assigned_seed(episode, "F1", "controlled", stage) is None, stage != "A")
        self.assertIsNone(assigned_seed(episode, "F1", "natural", "A"))


if __name__ == "__main__":
    unittest.main()
