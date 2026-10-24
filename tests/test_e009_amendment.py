import unittest

from research.e009_protocol import MAX_BATCH_CALLS, instructions_for, output_items, request_body
from research.e009_oracle import Oracle
from research.e009_scm import models


def call(identity):
    return {"type": "function_call", "call_id": str(identity), "name": "hash_claims", "arguments": '{"claims":[]}'}


class AmendmentTests(unittest.TestCase):
    def test_v2_accepts_ordered_batch_but_v1_remains_strict(self):
        response = {"status": "completed", "output": [call(i) for i in range(3)]}
        self.assertEqual(output_items(response, 2), response["output"])
        with self.assertRaisesRegex(ValueError, "invalid function call batch"):
            output_items(response, 1)

    def test_invalid_batch_is_rejected_before_any_dispatch(self):
        batches = [[call(1), call(1)], [call(i) for i in range(MAX_BATCH_CALLS + 1)],
                   [call(1), {**call(2), "arguments": "[]"}],
                   [call(1), {**call(2), "arguments": '{"x":NaN}'}]]
        for batch in batches:
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                output_items({"status": "completed", "output": batch}, 2)

    def test_all_query_kinds_have_literal_public_shapes_and_work_in_oracle(self):
        text = instructions_for(2)
        oracle = Oracle(models())
        queries = [{"kind": "model", "index": 0}, {"kind": "edge", "source": "Z", "target": "V"},
                   {"kind": "path", "source": "Z", "target": "Q"},
                   {"kind": "probability", "target": "V", "do": []}]
        for query in queries:
            self.assertIn('"kind":"' + query["kind"] + '"', text)
            self.assertIs(type(oracle.quantity(0, query)), int)
        self.assertIn('"kind":"census_match"', text)
        self.assertNotIn('"source"', instructions_for(1))
        with self.assertRaises(KeyError):
            oracle.quantity(0, {"kind": "edge", "from": "Z", "to": "V"})

    def test_request_binds_version_without_extra_hidden_state(self):
        first = request_body("fixture", [], "A", "F1", 16000, 1)
        second = request_body("fixture", [], "A", "F1", 16000, 2)
        self.assertNotEqual(first["instructions"], second["instructions"])
        first.pop("instructions"); second.pop("instructions")
        self.assertEqual(first, second)
        self.assertFalse(second["parallel_tool_calls"])


if __name__ == "__main__":
    unittest.main()
