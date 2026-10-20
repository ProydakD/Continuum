import copy
import unittest

from research.e008_amendment import model_for, require_execution_record, validate_scope
from research.e008_design import signature


class AmendmentScopeTests(unittest.TestCase):
    def setUp(self):
        self.registration = {
            "schedule": [
                {"id": "j00001", "phase": "calibration", "model_role": "primary"},
                {"id": "j00002", "phase": "validation", "model_role": "primary"},
                {"id": "j00003", "phase": "validation", "model_role": "primary"},
                {"id": "j00004", "phase": "test", "model_role": "primary"},
                {"id": "j00005", "phase": "robustness", "model_role": "secondary"},
            ],
            "models": {"primary": "old-primary", "secondary": "old-secondary"},
            "oracle_sha256": "oracle", "gold_manifest_sha256": "gold",
            "analysis": {"threshold": 0.1}, "limits": {"responses_per_context": 10},
            "resources": {"maximum_response_attempts": 52},
        }
        self.amendment = {
            "status": "draft_not_authorized_for_model_execution", "preregistered": False,
            "cutover_after_ordinal": 2, "first_pending_id": "j00003",
            "old_models": copy.deepcopy(self.registration["models"]),
            "proposed_models": {"primary": "new-primary", "secondary": "new-secondary"},
            "preserved_outcome_hashes": {"j00001": "one", "j00002": "two"},
            "reconciled_failure": {"id": "j00002", "sha256": "two",
                "failure_and_exhausted_recovery_remain_unchanged": True},
            "invariants": {
                "schedule_sha256": signature(self.registration["schedule"]),
                "oracle_sha256": "oracle", "gold_manifest_sha256": "gold",
                "analysis_sha256": signature(self.registration["analysis"]),
                "limits": copy.deepcopy(self.registration["limits"]),
                "original_resources": copy.deepcopy(self.registration["resources"]),
                "no_test_or_robustness_started": True, "no_completed_context_replays": True,
                "no_model_protocol_content_edits": True,
                "old_registration_and_admission_files_unchanged": True,
            },
        }

    def test_old_and_new_positions_have_distinct_expected_models(self):
        self.assertEqual([model_for(self.registration, job, self.amendment)
                          for job in self.registration["schedule"]],
                         ["old-primary", "old-primary", "new-primary", "new-primary", "new-secondary"])

    def test_without_amendment_original_identity_is_preserved(self):
        self.assertEqual(model_for(self.registration, self.registration["schedule"][3]), "old-primary")

    def test_draft_is_not_execution_authority(self):
        with self.assertRaisesRegex(PermissionError, "draft amendment"):
            require_execution_record(self.amendment)

    def test_status_label_alone_cannot_authorize_execution(self):
        self.amendment.update(status="approved_for_execution", preregistered=True)
        with self.assertRaises(PermissionError):
            require_execution_record(self.amendment)

    def test_missing_preserved_outcome_is_rejected(self):
        self.amendment["preserved_outcome_hashes"].pop("j00001")
        with self.assertRaises(PermissionError):
            validate_scope(self.registration, self.amendment)

    def test_other_failed_position_cannot_be_silently_reconciled(self):
        self.amendment["reconciled_failure"].update(id="j00001", sha256="one")
        with self.assertRaises(PermissionError):
            validate_scope(self.registration, self.amendment)

    def test_scientific_threshold_change_is_rejected(self):
        self.amendment["invariants"]["analysis_sha256"] = signature({"threshold": 0.01})
        with self.assertRaises(PermissionError):
            validate_scope(self.registration, self.amendment)

    def test_resource_reset_is_rejected(self):
        self.amendment["invariants"]["original_resources"]["maximum_response_attempts"] += 100
        with self.assertRaises(PermissionError):
            validate_scope(self.registration, self.amendment)

    def test_same_primary_and_secondary_are_rejected(self):
        self.amendment["proposed_models"]["secondary"] = "new-primary"
        with self.assertRaises(PermissionError):
            validate_scope(self.registration, self.amendment)

    def test_boundary_after_heldout_is_rejected(self):
        self.registration["schedule"][1]["phase"] = "test"
        self.amendment["invariants"]["schedule_sha256"] = signature(self.registration["schedule"])
        with self.assertRaisesRegex(PermissionError, "held-out"):
            validate_scope(self.registration, self.amendment)

    def test_role_substitution_and_unknown_job_are_rejected(self):
        for job in ({"id": "j00003", "model_role": "secondary"},
                    {"id": "foreign", "model_role": "primary"}):
            with self.subTest(job=job), self.assertRaises(PermissionError):
                model_for(self.registration, job, self.amendment)

    def test_boundary_cannot_skip_the_first_pending_job(self):
        self.amendment["first_pending_id"] = "j00004"
        with self.assertRaises(PermissionError):
            validate_scope(self.registration, self.amendment)


if __name__ == "__main__":
    unittest.main()
