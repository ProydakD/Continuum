"""Constructed truth/quote controls; passing these is not natural-prose validation."""
from copy import deepcopy
import json
import unittest

from research.e009_adjudication_v2 import SCHEMA as OUTPUT_SCHEMA, validate_reconstruction
from research.e009_observer_validation import compare_control, render_control, same_field, serialize_spans
from research.e009_episode import make_episode
from research.e009_episode_eval import reference_chain
from research.e009_oracle import Oracle
from research.e009_scm import models


def answer(case):
    memory = case["public"]["memory"]
    evidence = {"all": {"document": 0, "quote": memory["payload"]} if memory["format"] == "F"
                else {"document": 0, "pointer": ""}}
    claims = [{"id": cid, "identity_evidence": ["all"], "fields": {
        f: {**deepcopy(value), "evidence": ["all"]} for f, value in fields.items()}}
        for cid, fields in case["gold"]["expected"].items()]
    partial = any(v["state"] == "unknown" for c in claims for v in c["fields"].values())
    return {"schema": OUTPUT_SCHEMA, "evidence": evidence, "claims": claims,
            "coverage": "partial" if partial else "complete", "coverage_gaps": ["unrecorded hash"] if partial else []}


class ObserverValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = reference_chain(make_episode(455, "observer-control"), Oracle(models()))[1]["claims"]

    def test_spans_roundtrip_unicode_escaping_and_empty_values(self):
        value = {"a/b~": ["🌍", {"empty": [], "quote": '"x"'}], "none": None}
        text, spans = serialize_spans(value)
        self.assertEqual(json.loads(text), value)
        self.assertEqual(json.loads(text[slice(*spans["/a~1b~0/0"])]), "🌍")
        self.assertEqual(json.loads(text[slice(*spans["/a~1b~0/1/empty"])]), [])

    def test_gold_constructed_answers_cover_both_representations_and_shared_fields(self):
        for representation in ("F", "S"):
            for mode in ("complete", "shared_fields", "quoted_opposite", "partial_and_conflict"):
                with self.subTest(representation=representation, mode=mode):
                    case = render_control(self.records, mode, representation, "B")
                    result = compare_control(case, answer(case))
                    self.assertTrue(result["meaning_exact"])
                    self.assertTrue(result["witness_exact"])
                    self.assertFalse(result["general_natural_validity_established"])

    def test_wrong_value_with_real_citation_fails_meaning_not_existence(self):
        case = render_control(self.records, "complete", "F", "B"); output = answer(case)
        output["claims"][0]["fields"]["status"]["value"] = "supported"
        validate_reconstruction(case["public"], output)
        result = compare_control(case, output)
        self.assertFalse(result["meaning_exact"]); self.assertTrue(result["witness_exact"])

    def test_right_values_with_only_discarded_quote_fail_carrier_check(self):
        for representation in ("F", "S"):
            case = render_control(self.records, "quoted_opposite", representation, "B"); output = answer(case)
            if representation == "S": output["evidence"]["all"] = {"document": 0, "pointer": "/discarded_historical_quote"}
            else:
                start, end = case["gold"]["value_spans"]["/discarded_historical_quote"]
                output["evidence"]["all"] = {"document": 0, "quote": case["public"]["memory"]["payload"][start:end]}
            validate_reconstruction(case["public"], output)
            result = compare_control(case, output)
            self.assertTrue(result["meaning_exact"]); self.assertFalse(result["witness_exact"])

    def test_split_exact_source_quotes_are_composed(self):
        case = render_control(self.records, "complete", "F", "B"); output = answer(case)
        text = case["public"]["memory"]["payload"]; cut = len(text) // 2
        output["evidence"] = {"left": {"document": 0, "quote": text[:cut]}, "right": {"document": 0, "quote": text[cut:]}}
        for claim in output["claims"]:
            claim["identity_evidence"] = ["left", "right"]
            for field in claim["fields"].values(): field["evidence"] = ["left", "right"]
        self.assertTrue(compare_control(case, output)["witness_exact"])

    def test_conflict_cannot_be_silently_repaired_to_valid_array(self):
        case = render_control(self.records, "partial_and_conflict", "S", "B"); output = answer(case)
        field = next(c for c in output["claims"] if c["id"] == "J")["fields"]["proposition"]
        field.update(state="known", value=field["alternatives"][0], alternatives=[])
        self.assertFalse(compare_control(case, output)["meaning_exact"])

    def test_unknown_is_not_absent_and_flat_basis_is_not_and(self):
        case = render_control(self.records, "partial_and_conflict", "F", "B"); output = answer(case)
        h = next(c for c in output["claims"] if c["id"] == "H")
        h["fields"]["previous_sha256"]["state"] = "absent"
        output["coverage"] = "complete"; output["coverage_gaps"] = []
        self.assertFalse(compare_control(case, output)["meaning_exact"])
        output = answer(case); k = next(c for c in output["claims"] if c["id"] == "K")
        k["fields"]["bases"]["value"] = [["e:EA", "c:J"]]
        self.assertFalse(compare_control(case, output)["meaning_exact"])

    def test_semantic_normalization_not_arbitrary_malformed_equivalence(self):
        field = lambda v: {"state": "known", "value": v, "alternatives": []}
        self.assertTrue(same_field("bases", field([["e:EA", "e:EB"], ["c:J"]]), field([["c:J"], ["e:EB", "e:EA"]])))
        self.assertFalse(same_field("bases", field(["e:EA", "c:J"]), field(["e:EA", "c:H"])))
        self.assertFalse(same_field("proposition", field("unparsed A"), field("unparsed B")))

    def test_source_inputs_and_records_are_not_mutated(self):
        records = deepcopy(self.records); render_control(records, "partial_and_conflict", "F", "B")
        self.assertEqual(records, self.records)

    def test_wrong_document_citation_is_not_accepted(self):
        case = render_control(self.records, "complete", "F", "B"); output = answer(case)
        output["evidence"]["all"]["document"] = 1
        with self.assertRaises(ValueError): compare_control(case, output)


if __name__ == "__main__":
    unittest.main()
