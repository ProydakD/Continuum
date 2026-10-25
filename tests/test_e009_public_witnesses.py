"""Span composition tests; supplied obligation semantics remain explicitly unverified."""
from copy import deepcopy
import unittest

from research.e009_public_witnesses import compose_witnesses, trace_public_statuses


BINDING = {"claim_id": "R7", "field": "status", "as_of": "D"}
TEXT = "R7 is refuted. The old supported entry is not current."


def obligation(text=TEXT, **changes):
    result = {"binding": deepcopy(BINDING), "document": 0, "quote": text,
              "roles": ["identity", "assertion", "scope", "qualification"]}
    result.update(changes)
    return result


def assess(citations, documents=None, obligations=None, binding=None):
    return compose_witnesses(documents if documents is not None else [{"stage": "D", "text": TEXT}],
                             binding if binding is not None else BINDING,
                             obligations if obligations is not None else [obligation()], citations)


class PublicWitnessTests(unittest.TestCase):
    def observation(self, stage, value, scope="current", covered=True):
        binding = {"claim_id": "R7", "field": "status", "as_of": stage}
        proof = compose_witnesses([{"stage": stage, "text": TEXT}], binding,
                                 [obligation(binding=binding)], [{"document": 0, "quote": TEXT}] if covered else [])
        return {"binding": binding, "status": {"state": "known", "value": value}, "scope": scope, "coverage": proof}

    def test_split_sentences_cover_same_obligation_without_joining_values(self):
        citations = [{"document": 0, "quote": "R7 is refuted."},
                     {"document": 0, "quote": "The old supported entry is not current."}]
        before = deepcopy(citations)
        result = assess(citations)
        self.assertTrue(result["covered"])
        self.assertEqual(result["coverage_state"], "covered")
        self.assertEqual(citations, before)
        self.assertFalse(result["obligation_semantics_verified"])
        self.assertFalse(result["causal_truth_verified"])
        self.assertFalse(result["registered_bri_rescored"])

    def test_quote_order_overlap_and_redundancy_do_not_change_coverage(self):
        citations = [{"document": 0, "quote": "R7 is refuted. The old supported"},
                     {"document": 0, "quote": "supported entry is not current."}]
        self.assertTrue(assess(citations)["covered"])
        self.assertTrue(assess(citations[::-1] + citations)["covered"])

    def test_missing_qualification_and_negation_stay_uncovered(self):
        self.assertFalse(assess([{"document": 0, "quote": "R7 is refuted."}])["covered"])
        result = assess([{"document": 0, "quote": "R7 is refuted. The old supported entry is "},
                         {"document": 0, "quote": "current."}])
        self.assertFalse(result["covered"])
        missing = result["obligations"][0]["missing_ranges"]
        self.assertEqual("".join(TEXT[a:b] for a, b in missing), "not")

    def test_unrelated_same_words_cannot_fill_missing_source_positions(self):
        text = TEXT + " Another entry is not current."
        result = assess([{"document": 0, "quote": "R7 is refuted. The old supported entry is "},
                         {"document": 0, "quote": "Another entry is not current."}],
                        documents=[{"stage": "D", "text": text}])
        self.assertFalse(result["covered"])

    def test_old_document_quote_cannot_cover_current_document(self):
        docs = [{"stage": "D", "text": TEXT}, {"stage": "C", "text": TEXT}]
        self.assertFalse(assess([{"document": 1, "quote": TEXT}], docs)["covered"])

    def test_scope_obligation_from_wrong_stage_rejected(self):
        with self.assertRaises(ValueError):
            assess([{"document": 0, "quote": TEXT}], documents=[{"stage": "C", "text": TEXT}])

    def test_identity_field_and_as_of_bindings_cannot_be_borrowed(self):
        for name, value in [("claim_id", "R8"), ("field", "origin"), ("as_of", "C")]:
            different = deepcopy(BINDING);different[name] = value
            with self.assertRaises(ValueError):
                assess([{"document": 0, "quote": TEXT}], binding=different)

    def test_missing_required_roles_is_unknown_not_vacuous_success(self):
        result = assess([], obligations=[])
        self.assertEqual(result["coverage_state"], "unknown")
        self.assertEqual(set(result["missing_roles"]), {"identity", "assertion", "scope"})
        result = assess([{"document": 0, "quote": TEXT}], obligations=[obligation(roles=["assertion"])])
        self.assertFalse(result["covered"])
        self.assertEqual(result["coverage_state"], "unknown")

    def test_no_citations_does_not_cover_available_obligations(self):
        self.assertEqual(assess([])["coverage_state"], "uncovered")

    def test_duplicate_and_overlapping_occurrences_require_explicit_offset(self):
        docs = [{"stage": "D", "text": "aaaa"}]
        with self.assertRaises(ValueError):
            assess([{"document": 0, "quote": "aaa"}], docs, [obligation("aaa", start=1)])
        with self.assertRaises(ValueError):
            assess([{"document": 0, "quote": "aaaa"}], docs, [obligation("aaa")])
        self.assertTrue(assess([{"document": 0, "quote": "aaa", "start": 1}], docs,
                               [obligation("aaa", start=1)])["covered"])
        self.assertFalse(assess([{"document": 0, "quote": "aaa", "start": 0}], docs,
                                [obligation("aaa", start=1)])["covered"])

    def test_unicode_codepoint_offsets_not_bytes_or_normalized_text(self):
        text = "🌍 R7: cafe\u0301 — не подтверждено."
        quote = "R7: cafe\u0301 — не подтверждено."
        docs = [{"stage": "D", "text": text}]
        result = assess([{"document": 0, "quote": quote, "start": 2}], docs,
                        [obligation(quote, start=2)])
        self.assertTrue(result["covered"])
        self.assertEqual(result["citation_spans"][0]["start"], 2)
        for wrong in [{"document": 0, "quote": quote, "start": len("🌍 ".encode("utf-8"))},
                      {"document": 0, "quote": quote.replace("e\u0301", "é")}]:
            with self.assertRaises(ValueError):
                assess([wrong], docs, [obligation(quote)])

    def test_only_declared_ascii_whitespace_gaps_are_ignored(self):
        for gap, expected in [(" \n\t", True), (";", False), ("\u00a0", False)]:
            text = "R7" + gap + "refuted"
            result = assess([{"document": 0, "quote": "R7"}, {"document": 0, "quote": "refuted"}],
                            [{"stage": "D", "text": text}], [obligation(text)])
            self.assertEqual(result["covered"], expected)

    def test_empty_fabricated_offsets_and_private_fields_rejected(self):
        for citation in [{"document": 0, "quote": ""}, {"document": 0, "quote": "fabricated"},
                         {"document": True, "quote": TEXT}, {"document": 0, "quote": TEXT, "start": -1},
                         {"document": 0, "quote": TEXT, "private_truth": True}]:
            with self.assertRaises(ValueError):
                assess([citation])
        with self.assertRaises(ValueError):
            assess([], [{"stage": "D", "text": " "}], [obligation(" ")])

    def test_multidocument_lineage_is_not_current_scope(self):
        docs = [{"stage": "C", "text": "R7 was supported."}, {"stage": "D", "text": TEXT}]
        obligations = [obligation("R7 was supported.", roles=["lineage"]), obligation(document=1)]
        citations = [{"document": 0, "quote": "R7 was supported."}, {"document": 1, "quote": TEXT}]
        self.assertTrue(assess(citations, docs, obligations)["covered"])
        self.assertFalse(assess(citations[1:], docs, obligations)["covered"])

    def test_status_change_is_not_automatically_correct_root_revision(self):
        result = trace_public_statuses([self.observation("C", "undetermined"), self.observation("D", "refuted")])
        self.assertTrue(result["transitions"][0]["changed"])
        self.assertIsNone(result["transitions"][0]["root_revision"])
        self.assertEqual((result["bri_bounds"]["lower"], result["bri_bounds"]["upper"]), (0, 1))
        self.assertFalse(result["annotation_semantics_verified"])

    def test_historical_supported_is_not_agent_endorsement(self):
        result = trace_public_statuses([self.observation("seed", "supported", "historical"),
                                        self.observation("A", "undetermined")])
        self.assertEqual(result["transitions"][0]["kind"], "historical_to_current")
        self.assertIsNone(result["transitions"][0]["root_revision"])

    def test_missing_before_unknown_and_uncovered_keep_uncertainty(self):
        self.assertTrue(trace_public_statuses([self.observation("D", "supported")])["missing_before"])
        self.assertTrue(trace_public_statuses([])["missing_before"])
        before = self.observation("C", "undetermined", covered=False)
        self.assertIsNone(trace_public_statuses([before, self.observation("D", "refuted")])["transitions"][0]["changed"])
        before = self.observation("C", "undetermined");before["status"] = {"state": "unknown", "value": None}
        self.assertIsNone(trace_public_statuses([before, self.observation("D", "refuted")])["transitions"][0]["changed"])

    def test_unordered_stages_and_foreign_coverage_are_rejected(self):
        with self.assertRaises(ValueError):
            trace_public_statuses([self.observation("D", "supported"), self.observation("C", "refuted")])
        after = self.observation("D", "refuted");after["coverage"]["binding"]["claim_id"] = "R8"
        with self.assertRaises(ValueError):
            trace_public_statuses([after])

    def test_inconsistent_proof_and_seed_scope_are_rejected(self):
        current = self.observation("D", "refuted");current["coverage"]["covered"] = "yes"
        with self.assertRaises(ValueError):
            trace_public_statuses([current])
        with self.assertRaises(ValueError):
            trace_public_statuses([self.observation("seed", "supported")])


if __name__ == "__main__":
    unittest.main()
