import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.e008_design import schedule
from research.e008_locks import DecisionStore, load_outcome, seal_outcome, write_once


def synthetic_world(split):
    return {"id": split + "-world", "split": split, "truth": {"family": "relay", "PRIVATE": "NOT_FOR_MODELS"},
            "evidence": [{"id": "EA"}, {"id": "EB"}, {"id": "EC"}], "panel": [],
            "successor": [{"id": "Q" + str(i), "kind": "edge"} for i in range(10)],
            "design_audit": {"unidentifiable_question_ids": ["Q8", "Q9"]}}


class LockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.worlds = [synthetic_world(s) for s in ("training", "calibration", "validation", "test")]
        self.jobs = schedule(self.worlds)
        write_once(self.study / "registration.json", {"schedule": self.jobs})
        write_once(self.study / "oracle.json", {"worlds": self.worlds})
        self.store = DecisionStore(self.study, self.worlds, self.jobs)

    def outcome(self, job, correct=5, status="completed"):
        run = self.study / "units" / job["id"]
        result = {"job": job, "status": status, "saved": status == "completed"}
        write_once(run / "result.json", result)
        write_once(run / "raw-receipt.json", {"fixture": True, "not_model_evidence": True})
        score = {"new_target_correct": correct, "new_total": 10,
                 "questions": [{"id": "Q" + str(i), "target_expected": None if i >= 8 else True,
                                "target_correct": i < correct} for i in range(10)]}
        return seal_outcome(self.study, job, {"pass": status == "completed"}, score)

    def calibration(self, *, failed_budget=None):
        for job in self.jobs:
            if job["phase"] == "calibration":
                correct = {1024: 1, 2048: 4, 4096: 8}[job["budget"]]
                self.outcome(job, correct, "failed" if job["budget"] == failed_budget else "completed")

    def development(self):
        for job in self.jobs:
            if job["phase"] in ("development", "validation"):
                self.outcome(job, {1: 4, 2: 8, 3: 8}[job["version"]])

    def test_outcomes_are_immutable_and_raw_file_changes_detected(self):
        job = self.jobs[0]
        first = self.outcome(job)
        self.assertEqual(load_outcome(self.study, job["id"]), first)
        self.assertEqual(seal_outcome(self.study, job, first["audit"], first["score"]), first)
        with self.assertRaises(PermissionError):
            seal_outcome(self.study, job, first["audit"], {})
        (self.study / "units" / job["id"] / "raw-receipt.json").write_text("{}")
        with self.assertRaises(PermissionError):
            load_outcome(self.study, job["id"])

    def test_successful_unverified_context_is_not_sealed(self):
        job = self.jobs[0]
        write_once(self.study / "units" / job["id"] / "result.json", {"job": job, "status": "completed"})
        with self.assertRaises(PermissionError):
            seal_outcome(self.study, job, {"pass": False})

    def test_pending_cannot_enter_decision(self):
        self.calibration()
        job = next(j for j in self.jobs if j["phase"] == "calibration")
        (self.study / "units" / job["id"] / "outcome.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.store.calibration_lock()

    def test_calibration_uses_only_identified_predictions_and_freezes_sources(self):
        self.calibration()
        first = self.store.calibration_lock()
        self.assertEqual(first["decision"]["budget"], 2048)
        self.assertEqual(self.store.calibration_lock(), first)
        self.assertTrue(all(next(j for j in self.jobs if j["id"] == identity)["phase"] == "calibration"
                            for identity in first["sources"]))
        self.assertEqual(first["decision"]["candidates"][1]["rates"], {"C1": .5, "T1": .5})

    def test_failures_are_zero_not_removed_for_calibration(self):
        self.calibration(failed_budget=2048)
        lock = self.store.calibration_lock()
        row = next(r for r in lock["decision"]["candidates"] if r["budget"] == 2048)
        self.assertEqual(row["rates"], {"C1": 0, "T1": 0})
        self.assertFalse(row["both_in_target"])

    def test_registration_corpus_and_in_memory_assignments_cannot_change(self):
        self.calibration()
        self.jobs[0]["lineage"] = "foreign"
        with self.assertRaises(PermissionError):
            self.store.calibration_lock()
        self.jobs[0]["lineage"] = None
        self.worlds[0]["truth"]["PRIVATE"] = "changed"
        with self.assertRaises(PermissionError):
            self.store.calibration_lock()

    def test_calibration_cannot_be_replaced_with_a_different_decision(self):
        self.calibration()
        self.store.calibration_lock()
        path = self.study / "locks/calibration.json"
        value = json.loads(path.read_text())
        value["decision"]["budget"] = 4096
        path.write_text(json.dumps(value))
        with self.assertRaises(PermissionError):
            self.store.calibration_lock()

    def test_feedback_only_own_completed_validation_and_no_truth(self):
        self.calibration()
        self.development()
        feedback = self.store.validation_feedback("L1", 1)
        self.assertEqual(feedback["version"], "L1-v1")
        self.assertEqual(feedback["cases"][0]["new_target_correct"], 4)
        text = json.dumps(feedback)
        for forbidden in ("PRIVATE", "NOT_FOR_MODELS", "test-world", "training-world", "truth"):
            self.assertNotIn(forbidden, text)
        sources = json.loads((self.study / "locks/feedback-L1-v1.json").read_text())["sources"]
        self.assertTrue(all(j["phase"] == "validation" and j["lineage"] == "L1" and j["version"] == 1
                            for j in self.jobs if j["id"] in sources))

    def test_protocol_choice_uses_validation_only_and_all_versions(self):
        self.calibration()
        self.development()
        def publication(lineage, version, role="designer"):
            return {"version": f"{lineage}-v{version}", "body": "unit test, not a model proposal"}
        with patch.object(self.store, "publication", side_effect=publication):
            first = self.store.protocol_lock()
            self.assertEqual(first["decision"]["lineages"]["L1"]["version"], 2)
            self.assertEqual(first["decision"]["lineages"]["L2"]["version"], 2)
            self.assertEqual(self.store.protocol_lock(), first)
            # No held-out outcome exists; creating one later cannot affect selection.
            job = next(j for j in self.jobs if j["phase"] == "test" and j["stage"] == "D")
            self.outcome(job, 10)
            self.assertEqual(self.store.protocol_lock(), first)
        self.assertFalse(any(j["phase"] == "test" and j["id"] in first["sources"] for j in self.jobs))

    def test_unfinished_development_prevents_test_protocol_lock(self):
        self.calibration()
        with self.assertRaises(FileNotFoundError):
            self.store.protocol_lock()

    def test_training_projection_and_first_designer_need_no_prior_history(self):
        self.calibration()
        job = next(j for j in self.jobs if j["role"] == "designer" and j["lineage"] == "L1")
        gold = {"training-world": {"subsets": {s: {"questions": {"Q0": {"expected": None}}}
                                               for s in ("EA", "EA+EB", "EA+EB+EC")}}}
        supplied = self.store.development_bundle(job, gold)
        self.assertIsNone(supplied["prior_protocol"])
        self.assertIsNone(supplied["prior_review"])
        self.assertIsNone(supplied["validation_feedback"])
        self.assertEqual(supplied["memory_budget_bytes"], 2048)
        self.assertNotIn("PRIVATE", json.dumps(supplied))
        foreign = copy.deepcopy(gold)
        foreign["test-world"] = foreign["training-world"]
        with self.assertRaises(PermissionError):
            self.store.development_bundle(job, foreign)

    def test_second_designer_cannot_see_other_line_or_future_version(self):
        self.calibration()
        self.development()
        job = next(j for j in self.jobs if j["role"] == "designer" and j["lineage"] == "L2" and j["version"] == 2)
        gold = {"training-world": {"subsets": {s: {"questions": {}} for s in ("EA", "EA+EB", "EA+EB+EC")}}}
        seen = []
        def publication(lineage, version, role="designer"):
            seen.append((lineage, version, role))
            return {"version": f"{lineage}-v{version}", "content": role}
        with patch.object(self.store, "publication", side_effect=publication):
            supplied = self.store.development_bundle(job, gold)
        self.assertEqual(seen, [("L2", 1, "designer"), ("L2", 1, "critic")])
        self.assertEqual(supplied["validation_feedback"]["version"], "L2-v1")


if __name__ == "__main__":
    unittest.main()
