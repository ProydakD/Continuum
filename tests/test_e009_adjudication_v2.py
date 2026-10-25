"""Absence, null, unknown, conflict, and historical v1 must remain distinct."""
from copy import deepcopy
import json
import unittest

from research import e009_adjudication as v1
from research import e009_adjudication_v2 as v2


class AdjudicationV2Tests(unittest.TestCase):
    def setUp(self):
        self.claim = {"id": "R7", "version": 1, "origin": "A", "proposition": {"value": 1},
                      "status": "supported", "bases": [["e:EA"]], "reasons": ["EA"]}
        self.text = "Exact complete current record: " + json.dumps(self.claim)
        self.view = {"memory": {"format": "F", "payload": self.text}, "stage": "A",
                     "origin": {"actor": "fixture"}, "sha256": None, "trust": "unverified"}
        self.output = {"schema": v2.SCHEMA, "evidence": {"e0": {"document": 0, "quote": self.text}},
                       "claims": [{"id": "R7", "identity_evidence": ["e0"], "fields": {
                           k: {"state": "known" if k in self.claim else "absent", "value": self.claim.get(k),
                               "alternatives": [], "evidence": ["e0"]} for k in v2.FIELDS}}],
                       "coverage": "complete", "coverage_gaps": []}

    def test_explicit_absence_keeps_exact_record_without_default_hash(self):
        check = v2.validate_reconstruction(self.view, self.output)
        self.assertEqual(check["absent_fields"], 1)
        self.assertEqual(check["known_fields"], 6)
        result = v2.reconstructible_claims(self.view, self.output)
        self.assertEqual(result["claims"], [self.claim])
        self.assertNotIn("previous_sha256", result["claims"][0])
        self.assertFalse(result["semantic_verified"])

    def test_unknown_is_not_absent_or_silently_projected(self):
        output = deepcopy(self.output)
        output["claims"][0]["fields"]["previous_sha256"]["state"] = "unknown"
        with self.assertRaises(ValueError):
            v2.validate_reconstruction(self.view, output)
        output.update(coverage="partial", coverage_gaps=["Only an incomplete summary is available."])
        result = v2.reconstructible_claims(self.view, output)
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["unresolved_claim_ids"], ["R7"])

    def test_known_null_is_not_removed(self):
        output = deepcopy(self.output)
        output["claims"][0]["fields"]["previous_sha256"]["state"] = "known"
        result = v2.reconstructible_claims(self.view, output)
        self.assertIn("previous_sha256", result["claims"][0])
        self.assertIsNone(result["claims"][0]["previous_sha256"])
        # A mechanically valid citation still does not entail this counterfactual value.
        self.assertFalse(result["semantic_verified"])

    def test_absence_of_required_field_is_not_repaired_into_valid_record(self):
        output = deepcopy(self.output)
        output["claims"][0]["fields"]["origin"].update(state="absent", value=None)
        result = v2.reconstructible_claims(self.view, output)
        self.assertNotIn("origin", result["claims"][0])

    def test_captured_conflict_has_no_coverage_gap_but_remains_unprojected(self):
        output = deepcopy(self.output)
        output["claims"][0]["fields"]["status"].update(state="conflicting", value=None,
                                                       alternatives=["supported", "refuted"])
        check = v2.validate_reconstruction(self.view, output)
        self.assertEqual(check["conflicting_fields"], 1)
        self.assertEqual(v2.reconstructible_claims(self.view, output)["claims"], [])
        output["coverage_gaps"] = ["Conflict copied here as a gap."]
        with self.assertRaises(ValueError):
            v2.validate_reconstruction(self.view, output)

    def test_absence_requires_citation_null_and_no_alternatives(self):
        for update in ({"value": "invented"}, {"alternatives": [None]}, {"evidence": []}):
            output = deepcopy(self.output)
            output["claims"][0]["fields"]["previous_sha256"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                v2.validate_reconstruction(self.view, output)

    def test_v1_records_are_not_silently_converted_or_rescored(self):
        output = deepcopy(self.output); output["schema"] = v1.SCHEMA
        output["unresolved"] = output.pop("coverage_gaps")
        with self.assertRaisesRegex(ValueError, "not converted"):
            v2.validate_reconstruction(self.view, output)
        with self.assertRaisesRegex(ValueError, "invalid field state"):
            v1.validate_reconstruction(self.view, output)
        self.assertEqual(v1.public_request(self.view)["schema"], v1.SCHEMA)
        self.assertEqual(v2.public_request(self.view)["schema"], v2.SCHEMA)

    def test_projection_rejects_fabricated_evidence_before_using_values(self):
        output = deepcopy(self.output); output["evidence"]["e0"]["quote"] = "not in memory"
        with self.assertRaises(ValueError):
            v2.reconstructible_claims(self.view, output)


if __name__ == "__main__":
    unittest.main()
