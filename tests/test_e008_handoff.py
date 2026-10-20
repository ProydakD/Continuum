import base64
from fractions import Fraction
import hashlib
import json
import unittest

from research.e008_assessment import assess, build_gold, exact_value, hypothesis_index, hypothesis_key, inherited_claims
from research.e008_protocol import canonical, prompt, public_input, read_bytes, read_result, snapshot_value, source_ids, tools_for
from research.e008_scm import VARIABLES, evidence, model


def sample_world():
    scm = model("confounded", VARIABLES, "and", [0, 0, 0])
    return {"id": "unit", "truth": scm, "private_canary": "NEVER_SEND_THIS",
            "evidence": [evidence(scm, "EA"), evidence(scm, "EB", [["V0", 1]]), evidence(scm, "EC", [["V1", 1]])],
            "panel": [{"id": "P01", "kind": "edge", "source": "V0", "target": "V1"}],
            "successor": [{"id": "Q01", "kind": "probability", "target": "V1", "do": [["V0", 1]]}],
            "design_audit": {"integrative_question_ids": [], "unidentifiable_question_ids": []}}


def response(value, evidence_ids, *, confidence=1, revisions=None):
    return {"answers": [{"id": "P01", "value": value, "confidence": confidence, "evidence": evidence_ids,
                         "depends_on": [], "explanation": "The cited intervention constrains this edge.",
                         "witnesses": []}],
            "hypotheses": [], "revisions": revisions or [], "save_status": "saved"}


class PublicBoundaryTests(unittest.TestCase):
    def test_projection_excludes_oracle_future_questions_and_future_evidence(self):
        world = sample_world()
        a = {"stage": "A", "condition": "C1", "budget": 2048}
        text = prompt(a, world)
        self.assertNotIn("NEVER_SEND_THIS", text)
        data = json.loads(text.split("PUBLIC_INPUT: ", 1)[1])
        self.assertEqual(data["evidence"], world["evidence"][:1])
        self.assertEqual(data["questions"], world["panel"])
        self.assertEqual(data["source_ids_authorized_for_authentication"], ["EA"])

    def test_equal_primary_information_tools_and_budget_for_representations(self):
        world = sample_world()
        for stage in "ABCD":
            projected = [public_input({"stage": stage, "condition": c, "budget": 2048}, world) for c in ("C1", "T1", "T2")]
            self.assertEqual(projected[0], projected[1])
            self.assertEqual(projected[1], projected[2])
        self.assertNotIn("save_memory", [t["name"] for t in tools_for("D")])

    def test_full_journal_and_single_source_controls_are_explicit(self):
        world = sample_world()
        for condition, ids in (("C0", ["EC"]), ("SINGLE-A", ["EA"]), ("SINGLE-B", ["EB"]), ("FULL-JOURNAL", ["EA", "EB", "EC"])):
            job = {"stage": "D", "condition": condition, "budget": 2048}
            self.assertEqual(source_ids(job), ids)
            self.assertEqual([r["id"] for r in public_input(job, world)["evidence"]], ids)

    def test_complete_read_result_counts_metadata_unicode_and_encoding(self):
        value = snapshot_value("Сведения", "utf8", "B", "j0002:B", "0" * 64)
        raw = read_bytes(value)
        self.assertEqual(raw, json.dumps(read_result(value)).encode())
        self.assertGreater(len(raw), len(value["content"].encode()))
        self.assertEqual(json.loads(raw)["sha256"], hashlib.sha256(canonical(value)).hexdigest())
        arbitrary = base64.b64encode(bytes(range(256))).decode()
        self.assertEqual(snapshot_value(arbitrary, "base64", "A", "j0001:A", None)["content"], arbitrary)

    def test_bad_binary_encoding_and_empty_memory_are_rejected_without_execution(self):
        for content, encoding in (("", "utf8"), ("!", "base64"), ("", "base64"), ("x", "code")):
            with self.assertRaises(ValueError):
                snapshot_value(content, encoding, "A", "j1:A", None)
        text = "powershell.exe Remove-Item X; not an executable tool"
        self.assertEqual(snapshot_value(text, "utf8", "A", "j1:A", None)["content"], text)


class AssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = sample_world()
        cls.gold = build_gold(cls.world)

    def score(self, answer, permitted=("EA", "EB", "EC"), inherited=None):
        return assess(answer, self.world["panel"], self.gold, list(permitted), inherited_answers=inherited)

    def test_exact_probability_includes_thirds_and_rejects_type_coercion(self):
        self.assertEqual(exact_value("2/6", "probability"), "1/3")
        for value in (True, 0.5, "2", "1/0"):
            with self.assertRaises(ValueError):
                exact_value(value, "probability")
        with self.assertRaises(ValueError):
            exact_value(1, "edge")

    def test_null_is_correct_for_nonidentifiable_not_hidden_truth_match(self):
        unknown = self.score(response(None, ["EA"]), permitted=("EA",))
        confident = self.score(response(False, ["EA"]), permitted=("EA",))
        self.assertTrue(unknown["questions"][0]["correct"])
        self.assertFalse(confident["questions"][0]["correct"])
        self.assertTrue(confident["questions"][0]["high_confidence_unidentified_point"])

    def test_new_evidence_identifies_false_edge(self):
        result = self.score(response(False, ["EA", "EB", "EC"]))
        self.assertTrue(result["questions"][0]["correct"])
        self.assertTrue(result["questions"][0]["supported_explanation"])
        self.assertEqual(result["questions"][0]["brier"], 0)

    def test_forged_source_does_not_receive_provenance_credit(self):
        result = self.score(response(False, ["ORACLE"]))
        self.assertTrue(result["questions"][0]["correct"])
        self.assertFalse(result["questions"][0]["source_ids_valid"])
        self.assertFalse(result["questions"][0]["supported_explanation"])

    def test_invalid_or_missing_answer_is_not_dropped(self):
        for invalid in (None, {}, {"answers": []}):
            result = self.score(invalid)
            self.assertEqual(len(result["questions"]), 1)
            self.assertFalse(result["questions"][0]["correct"])
            self.assertFalse(result["schema_valid"])

    def test_revision_of_honest_uncertainty_is_not_called_original_error(self):
        prior = {"A:P01": {"question_id": "P01", "value": None, "expected_at_origin": None,
                           "identified_at_origin": False, "origin_kind": "natural"}}
        change = {"claim_id": "A:P01", "previous_value": None, "new_value": False,
                  "evidence": ["EA", "EB", "EC"], "reason": "New intervention distinguishes a shared cause from the asserted edge."}
        result = self.score(response(False, ["EA", "EB", "EC"], revisions=[change]), inherited=prior)["revisions"][0]
        self.assertTrue(result["uncertainty_resolution"])
        self.assertFalse(result["error_correction"])

    def test_invented_prior_value_does_not_count_as_correction(self):
        prior = {"A:P01": {"question_id": "P01", "value": None, "expected_at_origin": None}}
        change = {"claim_id": "A:P01", "previous_value": True, "new_value": False,
                  "evidence": ["EA", "EB", "EC"], "reason": "Alleged old error."}
        result = self.score(response(False, ["EA", "EB", "EC"], revisions=[change]), inherited=prior)["revisions"][0]
        self.assertFalse(result["matches_observed_prior"])
        self.assertFalse(result["error_correction"])

    def test_malformed_ancestor_dependencies_do_not_abort_or_create_lineage(self):
        for dependencies in (None, 42, "A:H0", {"claim": "A:H0"}, [{}]):
            prior = response(True, ["EA"])
            prior["answers"][0]["depends_on"] = dependencies
            inherited = inherited_claims([{"job": {"stage": "A"}, "result": {"answer": prior}}], self.gold)
            self.assertEqual(inherited["A:P01"]["depends_on"], [])
            self.assertEqual(inherited["A:P01"]["dependency_hypothesis_indices"], {})
            self.assertTrue(inherited["A:P01"]["value"])

    def test_deliberate_and_natural_errors_keep_distinct_origin(self):
        change = {"claim_id": "probe:P01", "previous_value": True, "new_value": False,
                  "evidence": ["EA", "EB", "EC"], "reason": "The inherited claim is contradicted."}
        prior = {"probe:P01": {"question_id": "P01", "value": True, "expected_at_origin": None,
                               "origin_kind": "deliberate_injection"}}
        result = self.score(response(False, ["EA", "EB", "EC"], revisions=[change]), inherited=prior)["revisions"][0]
        self.assertTrue(result["error_correction"])
        self.assertEqual(result["origin_kind"], "deliberate_injection")

    def test_invalid_confidence_is_not_silently_clamped(self):
        for confidence in (True, -1, 2, float("nan")):
            self.assertFalse(self.score(response(False, ["EA", "EB", "EC"], confidence=confidence))["questions"][0]["valid"])

    def test_single_source_abstention_is_epistemic_success_not_new_knowledge(self):
        q = self.world["successor"][0]
        expected = self.gold["subsets"]["EC"]["questions"][q["id"]]["expected"]
        self.assertIsNone(expected)
        self.assertIsNotNone(self.gold["subsets"]["EA+EB+EC"]["questions"][q["id"]]["expected"])
        answer = response(None, ["EC"])
        answer["answers"][0]["id"] = q["id"]
        score = assess(answer, [q], self.gold, ["EC"])
        self.assertEqual(score["new_epistemic_correct"], 1)
        self.assertEqual(score["new_correct"], 0)

    def test_single_source_lucky_point_is_prediction_success_not_verified_knowledge(self):
        q = self.world["successor"][0]
        expected = self.gold["subsets"]["EA+EB+EC"]["questions"][q["id"]]["expected"]
        answer = response(expected, ["EC"])
        answer["answers"][0]["id"] = q["id"]
        score = assess(answer, [q], self.gold, ["EC"])
        self.assertEqual(score["new_target_correct"], 1)
        self.assertEqual(score["new_correct"], 0)
        self.assertEqual(score["new_epistemic_correct"], 0)

    def test_rejected_dependency_must_keep_original_assignment_not_just_id(self):
        base = {"id": "probe:H0", "family": "relay", "order": list(VARIABLES), "gate": "and",
                "flips": [0, 0, 0], "status": "rejected", "confidence": 1, "evidence": ["EA", "EB", "EC"]}
        original = hypothesis_index()[hypothesis_key(base)]
        prior = {"probe:P01": {"question_id": "P01", "value": True, "expected_at_origin": None,
            "origin_kind": "deliberate_injection", "depends_on": ["probe:H0"],
            "dependency_hypothesis_indices": {"probe:H0": original}}}
        change = {"claim_id": "probe:P01", "previous_value": True, "new_value": False,
                  "evidence": ["EA", "EB", "EC"], "reason": "Refuted predecessor premise."}
        answer = response(False, ["EA", "EB", "EC"], revisions=[change])
        answer["hypotheses"] = [base]
        checked = self.score(answer, inherited=prior)
        self.assertEqual(checked["revisions"][0]["rejected_dependencies"], ["probe:H0"])
        answer["hypotheses"] = [dict(base, flips=[1, 0, 0])]
        checked = self.score(answer, inherited=prior)
        self.assertEqual(checked["revisions"][0]["rejected_dependencies"], [])


if __name__ == "__main__":
    unittest.main()
