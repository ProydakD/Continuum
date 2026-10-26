"""Negative native-context controls, not independent semantic calibration."""
from copy import deepcopy
import unittest

from research.e009_measurement.identity_context import inspect_native_identity_context


def view(payload, representation="S", stage="B"):
    return {"memory": {"format": representation, "payload": payload},
            "stage": stage, "origin": {"actor": "identity-fixture"},
            "sha256": None, "trust": "unverified_author_assertion"}


def inspect(payload, pointer="", claim_id="A"):
    return inspect_native_identity_context(view(payload), {"document": 0, "pointer": pointer}, claim_id)


class NativeIdentityContextTests(unittest.TestCase):
    def test_same_field_value_in_other_record_does_not_bind_identity(self):
        records = [{"id": "A", "status": "supported"}, {"id": "B", "status": "supported"}]
        result = inspect(records, "/1/status")
        self.assertEqual(result["category"], "native_context_other_id")
        self.assertEqual(result["nearest_native_record"]["id"], "B")
        self.assertEqual(result["source"]["pointer"], "/1/status")

    def test_native_record_and_field_ancestry(self):
        for pointer in ("/0", "/0/id", "/0/status", "/0/nested/value"):
            with self.subTest(pointer=pointer):
                result = inspect([{"id": "A", "status": None, "nested": {"value": []}}], pointer)
                self.assertEqual(result["category"], "native_context_same_id")
                self.assertEqual(result["nearest_native_record"]["pointer"], "/0")

    def test_escaped_and_empty_key_ancestors(self):
        for payload, pointer in (({"a/b~": {"id": "A"}}, "/a~1b~0/id"), ({"": {"id": "A"}}, "//id")):
            with self.subTest(pointer=pointer):
                self.assertEqual(inspect(payload, pointer)["category"], "native_context_same_id")

    def test_broad_container_is_not_unique_identity(self):
        result = inspect([{"id": "A"}, {"id": "B"}, {"id": "A", "historical": True}])
        self.assertEqual(result["category"], "selected_container_includes_id")
        self.assertEqual(result["descendant_ids"], ["A", "B", "A"])
        self.assertFalse(result["semantic_identity_verified"])

    def test_nested_record_has_nearest_identity_not_wrapper_identity(self):
        payload = {"id": "wrapper", "claims": [{"id": "A", "status": "supported"}]}
        self.assertEqual(inspect(payload)["category"], "selected_container_includes_id")
        result = inspect(payload, "/claims/0/status")
        self.assertEqual(result["nearest_native_record"]["id"], "A")

    def test_prose_and_alternative_key_remain_unassessed(self):
        for payload in ({"note": "A is the current claim"}, {"claim_id": "A"}, ["A"], {"value": None}):
            with self.subTest(payload=payload):
                self.assertEqual(inspect(payload)["category"], "no_native_identity_binding")

    def test_case_and_type_are_not_normalized(self):
        self.assertEqual(inspect({"id": "a"})["category"], "native_context_other_id")
        self.assertEqual(inspect({"id": 1}, claim_id="1")["category"], "no_native_identity_binding")
        for claim_id in (None, True, 1, ""):
            with self.subTest(claim_id=claim_id), self.assertRaises(ValueError):
                inspect({"id": "A"}, claim_id=claim_id)

    def test_evidence_record_id_does_not_prove_claim_type(self):
        result = inspect({"id": "A", "type": "evidence"})
        self.assertEqual(result["category"], "native_context_same_id")
        self.assertEqual(result["nearest_native_record"]["type"], "evidence")
        self.assertFalse(result["semantic_identity_verified"])

    def test_historical_and_negated_same_id_not_promoted(self):
        for payload in ({"id": "A", "historical": True}, {"id": "A", "quote": "rejected", "current": False}):
            result = inspect(payload)
            self.assertEqual(result["category"], "native_context_same_id")
            self.assertFalse(result["currentness_verified"])
            self.assertFalse(result["semantic_identity_verified"])

    def test_journal_selection_is_explicit_and_not_changed(self):
        memory = {"memory": None, "trust": "unverified_author_assertion",
                  "journal": [view({"id": "A"}, stage="A"), view({"id": "B"}, stage="B")]}
        result = inspect_native_identity_context(memory, {"document": 0, "pointer": ""}, "A")
        self.assertEqual(result["source"]["stage"], "A")
        self.assertFalse(result["currentness_verified"])

    def test_invalid_or_non_native_selection_not_repaired(self):
        with self.assertRaisesRegex(ValueError, "S payload must be structured"):
            inspect(None)
        for pointer in ("/01", "/1", "/bad~2"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                inspect([{"id": "A"}], pointer)
        with self.assertRaisesRegex(ValueError, "S document"):
            inspect_native_identity_context(view("A", "F"), {"document": 0, "start": 0, "end": 1, "decode": "text"}, "A")
        with self.assertRaises(ValueError):
            inspect_native_identity_context(view({"id": "A"}), {"document": 0, "pointer": "", "value": "A"}, "A")

    def test_detached_return_and_no_input_mutation(self):
        payload = {"id": "A", "type": {"nested": []}}
        before = deepcopy(payload)
        result = inspect(payload)
        result["nearest_native_record"]["type"]["nested"].append("change")
        result["descendant_ids"].append("B")
        self.assertEqual(payload, before)


if __name__ == "__main__":
    unittest.main()
