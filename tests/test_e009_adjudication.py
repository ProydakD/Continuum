"""Mechanical grounding must neither invent semantics nor leak private labels."""
from copy import deepcopy
import json
import unittest

from research.e009_adjudication import FIELDS, SCHEMA, known_claims, public_request, validate_reconstruction


def envelope(payload, representation="F", stage="A"):
    return {"memory": {"format": representation, "payload": payload}, "stage": stage,
            "origin": {"actor": "fixture"}, "sha256": None, "trust": "unverified"}


class AdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.claim = {"id": "H", "version": 2, "origin": "fixture",
                      "proposition": {"query": {"kind": "edge", "source": "X", "target": "Y"}, "value": 1},
                      "status": "supported", "bases": [["e:EA"]], "reasons": ["EA"],
                      "previous_sha256": "a" * 64}
        self.text = "Публичная память: " + json.dumps(self.claim)
        self.view = envelope(self.text)
        self.output = {"schema": SCHEMA, "evidence": {"e0": {"document": 0, "quote": json.dumps(self.claim)}},
                       "claims": [{"id": "H", "identity_evidence": ["e0"], "fields": {
                           k: {"state": "known", "value": self.claim[k], "alternatives": [], "evidence": ["e0"]}
                           for k in FIELDS}}], "coverage": "complete", "unresolved": []}

    def test_public_request_retains_history_and_metadata_but_rejects_sidecar(self):
        view = {"journal": [envelope("old", stage=None), self.view], "memory": None, "trust": "unverified"}
        request = public_request(view)
        self.assertEqual([d["stage"] for d in request["documents"]], [None, "A"])
        self.assertEqual(request["documents"][1]["origin"], self.view["origin"])
        request["documents"][1]["origin"]["actor"] = "changed"
        self.assertEqual(self.view["origin"]["actor"], "fixture")
        with self.assertRaises(ValueError):
            public_request({**self.view, "private_claims": [self.claim]})

    def test_exact_text_citation_resolves_utf8_without_claiming_truth(self):
        result = validate_reconstruction(self.view, self.output)
        witness = result["resolved_evidence"]["e0"]
        self.assertEqual(self.text.encode()[witness["start_utf8"]:witness["end_utf8"]].decode(), json.dumps(self.claim))
        self.assertEqual(result["known_fields"], 7)
        self.assertTrue(result["structurally_valid"])
        self.assertFalse(result["semantic_verified"])
        self.assertEqual(known_claims(self.output)["claims"], [self.claim])

    def test_real_but_irrelevant_quote_is_not_semantic_verification(self):
        output = deepcopy(self.output)
        output["claims"][0]["fields"]["status"]["value"] = "refuted"
        result = validate_reconstruction(self.view, output)
        self.assertTrue(result["structurally_valid"])
        self.assertFalse(result["semantic_verified"])

    def test_missing_changed_or_ambiguous_quote_is_rejected(self):
        for quote in ("", "fabricated quote", "Public memory"):
            output = deepcopy(self.output); output["evidence"]["e0"]["quote"] = quote
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                validate_reconstruction(self.view, output)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            validate_reconstruction(envelope(self.text + self.text), self.output)

    def test_structured_pointer_is_exact_and_escape_aware(self):
        view = envelope({"a/b~c": [self.claim]}, "S")
        output = deepcopy(self.output); output["evidence"]["e0"] = {"document": 0, "pointer": "/a~1b~0c/0"}
        self.assertTrue(validate_reconstruction(view, output)["structurally_valid"])
        for pointer in ("/a~1b~0c/01", "/a~1b~0c/-1", "/a~1b~0c/1", "/a~2b", "missing"):
            output["evidence"]["e0"]["pointer"] = pointer
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                validate_reconstruction(view, output)

    def test_unknown_is_retained_not_filled_or_counted_complete(self):
        output = deepcopy(self.output)
        output["claims"][0]["fields"]["origin"] = {"state": "unknown", "value": None, "alternatives": [], "evidence": []}
        with self.assertRaisesRegex(ValueError, "hide unknowns"):
            validate_reconstruction(self.view, output)
        output.update(coverage="partial", unresolved=["Origin not stated."])
        result = validate_reconstruction(self.view, output)
        self.assertEqual(result["unknown_fields"], 1)
        self.assertEqual(known_claims(output)["unresolved_claim_ids"], ["H"])
        self.assertEqual(known_claims(output)["claims"], [])

    def test_conflict_preserves_competing_values(self):
        output = deepcopy(self.output)
        field = output["claims"][0]["fields"]["status"]
        field.update(state="conflicting", value=None, alternatives=["supported", "refuted"])
        result = validate_reconstruction(self.view, output)
        self.assertEqual(result["conflicting_fields"], 1)
        self.assertEqual(known_claims(output)["unresolved_claim_ids"], ["H"])
        field["alternatives"] = ["supported", "supported"]
        with self.assertRaisesRegex(ValueError, "distinct alternatives"):
            validate_reconstruction(self.view, output)

    def test_no_claims_unknown_and_explicit_empty_are_different(self):
        output = {"schema": SCHEMA, "claims": [], "evidence": {}, "coverage": "unreadable", "unresolved": ["No identifiable claims."]}
        self.assertEqual(validate_reconstruction(envelope("Only a heading."), output)["coverage"], "unreadable")
        output.update(coverage="complete", unresolved=[], evidence={"e0": {"document": 0, "quote": "No current claims remain."}})
        self.assertEqual(validate_reconstruction(envelope("No current claims remain."), output)["coverage"], "complete")

    def test_invalid_fields_references_documents_and_nonfinite_values_fail(self):
        changes = [lambda o: o.update(extra=True),
                   lambda o: o["claims"].append(deepcopy(o["claims"][0])),
                   lambda o: o["evidence"]["e0"].update(document=True),
                   lambda o: o["evidence"]["e0"].update(document=-1),
                   lambda o: o["claims"][0].update(identity_evidence=["missing"]),
                   lambda o: o["claims"][0]["fields"].pop("version"),
                   lambda o: o["claims"][0]["fields"]["version"].update(value=float("nan"))]
        for change in changes:
            output = deepcopy(self.output); change(output)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_reconstruction(self.view, output)


if __name__ == "__main__":
    unittest.main()
