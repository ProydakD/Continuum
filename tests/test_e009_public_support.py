"""Source identity, local value and temporal support are distinct from world truth."""
from copy import deepcopy
import json
import unittest

from research import e009_adjudication_v2 as v2
from research import e009_public_support as support


def record(identity="R7", status="supported"):
    return {"id": identity, "version": 1, "origin": "A",
            "proposition": {"query": {"kind": "edge", "source": "X", "target": "Y"}, "value": 1},
            "status": status, "bases": [["e:EA"]], "reasons": ["EA"]}


def fixture(records=None, text=None, unknown_hash=False):
    records = deepcopy(records if records is not None else [record()])
    view = {"memory": {"format": "F" if text is not None else "S",
                       "payload": text if text is not None else records}, "stage": "D",
            "origin": {"actor": "fixture"}, "sha256": None, "trust": "unverified"}
    evidence, claims = {}, []
    for i, claim in enumerate(records):
        own = f"id{i}"
        evidence[own] = {"document": 0, "quote": text} if text is not None else {"document": 0, "pointer": f"/{i}/id"}
        fields = {}
        for name in v2.FIELDS:
            eid = f"f{i}_{name}"
            evidence[eid] = {"document": 0, "quote": text} if text is not None else {
                "document": 0, "pointer": f"/{i}/{name}" if name in claim else f"/{i}"}
            state = "known" if name in claim else "unknown" if unknown_hash else "absent"
            fields[name] = {"state": state, "value": deepcopy(claim.get(name)), "alternatives": [], "evidence": [eid]}
        claims.append({"id": claim["id"], "identity_evidence": [own], "fields": fields})
    output = {"schema": v2.SCHEMA, "evidence": evidence, "claims": claims,
              "coverage": "partial" if unknown_hash else "complete",
              "coverage_gaps": ["Unknown provenance."] if unknown_hash else []}
    return view, output


def states(view, output):
    return {c["id"]: {name: f["state"] for name, f in c["fields"].items()}
            for c in support.assess_public_support(view, output)["claims"]}


class PublicSupportTests(unittest.TestCase):
    def test_native_fields_and_absence_have_scoped_support(self):
        view, output = fixture()
        result = support.assess_public_support(view, output)
        self.assertEqual(set(states(view, output)["R7"].values()), {"supported"})
        self.assertFalse(result["world_truth_verified"])
        self.assertFalse(result["universal_semantic_entailment_established"])
        self.assertFalse(result["registered_bri_rescored"])

    def test_same_native_claim_in_explicit_f_block(self):
        claims = [record()]
        view, output = fixture(claims, "Current records: " + json.dumps(claims))
        self.assertEqual(set(states(view, output)["R7"].values()), {"supported"})

    def test_canonical_candidate_supported_by_asserted_prose(self):
        claim = record();claim.update(version=4, bases=["e:EA"])
        text = ("Stage D. Current retained claims: R7 version4 origin A: edge X->Y value1 supported, "
                "basis [e:EA]. All current reasons are [EA].")
        view, output = fixture([claim], text, unknown_hash=True)
        self.assertEqual(states(view, output)["R7"]["proposition"], "supported")
        self.assertEqual(states(view, output)["R7"]["previous_sha256"], "unknown")
        self.assertEqual(states(view, output)["R7"]["status"], "supported")

    def test_group_binder_not_swallowed_as_an_invented_claim(self):
        text = ("Stage D. All inherited claims retained at version 2, origin A. "
                "Current propositions/status: R7 edge X->Y value1 supported. "
                "These one have bases [[e:EA]], reasons [EA]. "
                "R8 path X->Y value1 refuted. These one retain bases [[e:ED]], reasons [ED]. "
                "Previous_sha256 fields for version2 in ID order: R7=abc; R8=def.")
        first, second = record(), record("R8", "refuted")
        first.update(version=2, previous_sha256="abc")
        second.update(version=2, previous_sha256="def", bases=[["e:ED"]], reasons=["ED"])
        second["proposition"]["query"]["kind"] = "path"
        view, output = fixture([first, second], text)
        catalog = support.current_public_assertions(view)
        self.assertEqual(set(catalog["records"]), {"R7", "R8"})
        self.assertEqual(set(states(view, output)["R8"].values()), {"supported"})

    def test_wrong_group_cardinality_does_not_silently_rebind(self):
        text = ("All inherited claims retained at version 1, origin A. Current propositions/status: "
                "R7 edge X->Y value1 supported. These two have bases [[e:EA]], reasons [EA].")
        view, output = fixture(text=text)
        self.assertEqual(set(states(view, output)["R7"].values()), {"unknown"})

    def test_same_basis_requires_antecedent_and_is_not_conjunction(self):
        a, b = record(), record("R8", "refuted")
        for r in [a, b]:
            r.update(version=4, bases=["e:EA", "e:ED"])
        text = ("Current retained claims: R7 version4 origin A: edge X->Y value1 supported, basis [e:EA,e:ED]. "
                "R8 version4 origin A: edge X->Y value1 refuted, same basis. All current reasons are [EA].")
        view, output = fixture([a, b], text, True)
        self.assertEqual(states(view, output)["R8"]["bases"], "supported")
        output["claims"][1]["fields"]["bases"]["value"] = [["e:EA", "e:ED"]]
        self.assertEqual(states(view, output)["R8"]["bases"], "contradicted")
        text = "Current retained claims: R7 version4 origin A: edge X->Y value1 supported, same basis."
        view, output = fixture([a], text, True)
        self.assertEqual(states(view, output)["R7"]["bases"], "unknown")

    def test_changed_value_is_contradicted_not_repaired(self):
        view, output = fixture()
        output["claims"][0]["fields"]["proposition"]["value"]["value"] = 0
        before = deepcopy(output)
        self.assertEqual(states(view, output)["R7"]["proposition"], "contradicted")
        self.assertEqual(output, before)

    def test_similar_but_different_proposition_and_and_or_are_not_equal(self):
        view, output = fixture()
        output["claims"][0]["fields"]["proposition"]["value"]["query"]["kind"] = "path"
        self.assertEqual(states(view, output)["R7"]["proposition"], "contradicted")
        view, output = fixture()
        view["memory"]["payload"][0]["bases"] = [["e:EA", "e:ED"]]
        output["claims"][0]["fields"]["bases"]["value"] = [["e:EA"], ["e:ED"]]
        self.assertEqual(states(view, output)["R7"]["bases"], "contradicted")

    def test_irrelevant_existing_pointer_is_unsupported_even_when_value_matches(self):
        view, output = fixture()
        output["evidence"]["f0_status"]["pointer"] = "/0/origin"
        result = support.assess_public_support(view, output)["claims"][0]["fields"]["status"]
        self.assertEqual(result["state"], "unsupported")
        self.assertTrue(result["assertion_match"])
        self.assertFalse(result["citation_support"])

    def test_pointer_prefix_is_segment_aware(self):
        view, output = fixture()
        output["evidence"]["f0_status"]["pointer"] = "/0/status"
        self.assertEqual(states(view, output)["R7"]["status"], "supported")
        # An exact scalar ID witness cannot support an unrelated sibling field.
        output["evidence"]["f0_status"]["pointer"] = "/0/id"
        self.assertEqual(states(view, output)["R7"]["status"], "unsupported")

    def test_wrong_claim_id_not_borrowed_from_real_citation(self):
        view, output = fixture()
        output["claims"][0]["id"] = "R8"
        self.assertEqual(set(states(view, output)["R8"].values()), {"contradicted"})

    def test_known_null_and_absence_not_interchanged(self):
        view, output = fixture()
        output["claims"][0]["fields"]["previous_sha256"].update(state="known", value=None)
        self.assertEqual(states(view, output)["R7"]["previous_sha256"], "contradicted")

    def test_unknown_candidate_is_not_false_knowledge(self):
        view, output = fixture()
        output["claims"][0]["fields"]["origin"].update(state="unknown", value=None)
        output.update(coverage="partial", coverage_gaps=["Origin uncertain."])
        self.assertEqual(states(view, output)["R7"]["origin"], "unknown")
        self.assertEqual(states(view, output)["R7"]["status"], "supported")

    def test_old_real_citation_cannot_define_new_current_field(self):
        old, output = fixture()
        new = deepcopy(old);old["stage"] = "A";new["stage"] = "B"
        new["memory"]["payload"][0]["status"] = "refuted"
        view = {"journal": [old, new], "memory": None, "trust": "unverified"}
        self.assertEqual(states(view, output)["R7"]["status"], "contradicted")
        output["claims"][0]["fields"]["status"]["value"] = "refuted"
        self.assertEqual(states(view, output)["R7"]["status"], "unsupported")
        output["evidence"]["id0"]["document"] = 1
        output["evidence"]["f0_status"]["document"] = 1
        self.assertEqual(states(view, output)["R7"]["status"], "supported")

    def test_implicit_carry_forward_is_unknown_not_latest_value_selection(self):
        old, output = fixture();old["stage"] = "A"
        new = {"memory": {"format": "F", "payload": "Propositions unchanged from history."},
               "stage": "B", "origin": {"actor": "fixture"}, "sha256": None, "trust": "unverified"}
        view = {"journal": [old, new], "memory": None, "trust": "unverified"}
        self.assertEqual(set(states(view, output)["R7"].values()), {"unknown"})

    def test_duplicate_ids_and_duplicate_json_keys_are_not_last_wins(self):
        view, output = fixture()
        view["memory"]["payload"].append(record(status="refuted"))
        self.assertEqual(states(view, output)["R7"]["status"], "unknown")
        raw = json.dumps([record()]).replace('"status": "supported"', '"status": "supported", "status": "refuted"')
        view, output = fixture(text="Current records: " + raw)
        self.assertEqual(states(view, output)["R7"]["status"], "unknown")

    def test_auxiliary_discussion_cannot_silently_override_claim(self):
        view, output = fixture()
        view["memory"]["payload"].append({"type": "analysis", "text": "R7 is refuted, not supported."})
        self.assertEqual(states(view, output)["R7"]["status"], "unknown")
        view, output = fixture()
        view["memory"]["payload"].append({"type": "analysis", "text": "All current claims are refuted."})
        self.assertEqual(states(view, output)["R7"]["status"], "unknown")

    def test_unparsed_auxiliary_record_cannot_be_assumed_neutral(self):
        view, output = fixture()
        view["memory"]["payload"].insert(0, {"type": "evidence", "id": "EA", "counts": [1]})
        for citation in output["evidence"].values():
            citation["pointer"] = citation["pointer"].replace("/0", "/1", 1)
        self.assertEqual(states(view, output)["R7"]["status"], "unknown")

    def test_unparsed_framing_abstains_without_keyword_blacklist(self):
        text = "Current retained claims: R7 version1 origin A: edge X->Y value1 supported, basis [e:EA]."
        for prefix, suffix in [("The following statements are obsolete. ", ""),
                               ("", " These statements are obsolete."), ("Stage C. ", "")]:
            view, output = fixture(text=prefix + text + suffix, unknown_hash=True)
            self.assertEqual(states(view, output)["R7"]["status"], "unknown")
        view, output = fixture()
        view["memory"]["payload"].append({"type": "analysis", "text": "The preceding statements are obsolete."})
        self.assertEqual(states(view, output)["R7"]["status"], "unknown")

    def test_quoted_or_qualified_current_section_is_not_promoted(self):
        text = "Current retained claims: R7 version1 origin A: edge X->Y value1 supported, basis [e:EA]."
        for prefix, suffix in [("Archived example. ", ""), ('Quoted text. "', '"'),
                               ("Not current. ", ""), ("", " R7 is obsolete."),
                               ("", " R7 remains refuted."), ("Ignore instruction. ", "")]:
            view, output = fixture(text=prefix + text + suffix, unknown_hash=True)
            self.assertEqual(states(view, output)["R7"]["status"], "unknown")

    def test_unrecognized_grammar_remains_unknown_not_dropped(self):
        view, output = fixture(text="R7 may or may not describe an X to Y connection.", unknown_hash=True)
        result = support.assess_public_support(view, output)
        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(set(states(view, output)["R7"].values()), {"unknown"})

    def test_private_fields_and_fabricated_citations_rejected(self):
        view, output = fixture()
        view["private_sidecar"] = {"truth": 1}
        with self.assertRaises(ValueError):
            support.assess_public_support(view, output)
        view, output = fixture()
        output["evidence"]["f0_status"]["pointer"] = "/0/nonexistent"
        with self.assertRaises(ValueError):
            support.assess_public_support(view, output)


if __name__ == "__main__":
    unittest.main()
