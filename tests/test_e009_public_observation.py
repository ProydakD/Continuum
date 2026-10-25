"""Public-only extraction and counterfactual sidecar/ambiguity controls."""
from copy import deepcopy
import hashlib
import json
import unittest

from research.e009_guardrails import publication_valid
from research.e009_public_observation import compare_public_measurement, observe_public_memory


def envelope(payload, representation="F", stage="A"):
    return {"memory": {"format": representation, "payload": payload}, "stage": stage,
            "origin": {"actor": "test-fixture"}, "sha256": None, "trust": "unverified"}


class PublicObservationTests(unittest.TestCase):
    def setUp(self):
        self.claim = {"id": "H", "proposition": {"kind": "edge", "from": "X", "to": "Y"},
                      "status": "supported", "bases": [["e:EA"]], "version": 2,
                      "origin": "fixture", "previous_sha256": "a" * 64, "reasons": ["EA"]}

    def test_exact_objects_in_both_formats_still_need_semantic_adjudication(self):
        for representation in ("F", "S"):
            payload = {"claims": [self.claim]}
            if representation == "F":
                payload = json.dumps(payload)
            result = compare_public_measurement(envelope(payload, representation), [self.claim])
            self.assertEqual(result["comparison"], "equal_explicit_objects")
            self.assertEqual(result["semantic_status"], "unadjudicated")
            self.assertFalse(result["public_state_verified"])

    def test_utf8_witness_and_escaped_pointer_recover_exact_public_object(self):
        payload = "Память: " + json.dumps({"a/b~c": [self.claim]}, ensure_ascii=False) + " конец"
        result = observe_public_memory(envelope(payload))
        occurrence = result["occurrences"][0]
        witness = occurrence["witness"]
        root = json.loads(payload.encode()[witness["start_utf8"]:witness["end_utf8"]])
        self.assertEqual(witness["json_pointer"], "/a~1b~0c/0")
        self.assertEqual(root["a/b~c"][0], occurrence["claim"])
        canonical = json.dumps(root, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), witness["json_value_sha256"])

    def test_private_counterfactual_cannot_change_public_observation(self):
        view = envelope(json.dumps(self.claim))
        changed = {**self.claim, "status": "refuted"}
        first = compare_public_measurement(view, [self.claim])
        second = compare_public_measurement(view, [changed])
        self.assertEqual(first["observation"], second["observation"])
        self.assertEqual(second["claim_differences"], [{"id": "H", "paths": ["/status"]}])

    def test_field_corruption_is_visible_despite_legacy_publication_guard(self):
        replacements = {"proposition": {"kind": "edge", "from": "Y", "to": "X"},
                        "bases": [], "previous_sha256": "b" * 64, "status": "refuted",
                        "origin": "changed", "version": 3, "reasons": []}
        for field, value in replacements.items():
            for representation, condition in (("F", "F0"), ("S", "S0")):
                with self.subTest(field=field, representation=representation):
                    public = {**self.claim, field: value}
                    payload = [public] if representation == "S" else json.dumps(public)
                    view = envelope(payload, representation)
                    self.assertTrue(publication_valid({"published_memory": view["memory"]}, condition))
                    result = compare_public_measurement(view, [self.claim])
                    self.assertEqual(result["comparison"], "different_explicit_objects")
                    self.assertTrue(any(p.startswith("/" + field) for p in result["claim_differences"][0]["paths"]))

    def test_missing_extraction_is_not_proof_of_omission(self):
        second = {**self.claim, "id": "J"}
        result = compare_public_measurement(envelope(json.dumps(self.claim)), [self.claim, second])
        self.assertEqual(result["not_extracted_private_ids"], ["J"])
        self.assertEqual(result["comparison"], "different_explicit_objects")
        prose = compare_public_measurement(envelope("H is supported; all earlier fields remain unchanged."), [self.claim])
        self.assertEqual(prose["comparison"], "no_explicit_claim_objects")
        self.assertFalse(prose["public_state_verified"])

    def test_full_journal_preserves_history_without_imputing_current_claims(self):
        seed = envelope(json.dumps(self.claim), stage=None)
        current = envelope("Reuse the seed proposition, but H is now refuted.")
        view = {"journal": [seed, current], "memory": None, "trust": "unverified"}
        result = observe_public_memory(view)
        self.assertEqual([h["stage"] for h in result["history"]], [None, "A"])
        self.assertEqual(result["occurrences"], [])
        changed = deepcopy(view)
        changed["journal"][0]["memory"]["payload"] = "different historical context"
        self.assertNotEqual(observe_public_memory(changed)["memory_view_sha256"], result["memory_view_sha256"])

    def test_matching_old_objects_and_contradictory_prose_never_pass_semantics(self):
        view = envelope("Old snapshot: " + json.dumps(self.claim) + ". Correction: H is now refuted.")
        result = compare_public_measurement(view, [self.claim])
        self.assertEqual(result["comparison"], "equal_explicit_objects")
        self.assertFalse(result["public_state_verified"])

    def test_duplicate_ids_are_ambiguous_not_last_wins(self):
        view = envelope(json.dumps([self.claim, {**self.claim, "status": "refuted"}]))
        result = compare_public_measurement(view, [self.claim])
        self.assertEqual(result["comparison"], "ambiguous_explicit_objects")
        self.assertEqual(result["observation"]["duplicate_ids"], ["H"])
        self.assertEqual(len(result["observation"]["occurrences"]), 2)

    def test_duplicate_keys_nonfinite_and_malformed_roots_are_not_salvaged(self):
        for prefix, suffix in [("{\"a\":1,\"a\":2,\"claims\":", "}"),
                               ("{\"a\":NaN,\"claims\":", "}"),
                               ("{\"a\":1e999,\"claims\":", "}"),
                               ("{\"a\":1,\"a\":2,\"claims\":", ", broken")]:
            with self.subTest(prefix=prefix, suffix=suffix):
                result = compare_public_measurement(envelope(prefix + json.dumps([self.claim]) + suffix), [self.claim])
                self.assertEqual(result["comparison"], "ambiguous_explicit_objects")
                self.assertEqual(result["observation"]["occurrences"], [])
                self.assertEqual(len(result["observation"]["rejected_json_values"]), 1)

    def test_unexpected_private_fields_and_invalid_stages_are_rejected(self):
        for stage in (1, [], {}, "AA", "E"):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                observe_public_memory(envelope("text", stage=stage))
        view = envelope("text")
        view["measurement"] = [self.claim]
        with self.assertRaisesRegex(ValueError, "unexpected public"):
            observe_public_memory(view)
        with self.assertRaisesRegex(ValueError, "consecutive"):
            observe_public_memory({"journal": [envelope("text", stage="B")], "memory": None, "trust": "unverified"})
        with self.assertRaisesRegex(ValueError, "duplicate measurement"):
            compare_public_measurement(envelope("text"), [self.claim, self.claim])

    def test_observation_is_detached_and_does_not_mutate_input(self):
        view = envelope([self.claim], "S")
        before = deepcopy(view)
        result = observe_public_memory(view)
        self.assertEqual(view, before)
        result["occurrences"][0]["claim"]["status"] = "refuted"
        self.assertEqual(view, before)


if __name__ == "__main__":
    unittest.main()
