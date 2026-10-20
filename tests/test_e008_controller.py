import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from research.e008_controller import resolve_job


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.selected = {"memory_budget": 2048, "lineages": {
            "L1": {"protocol": {"version": "L1-v2", "body": "unit fixture", "encoding": "utf8"}},
            "L2": {"protocol": None}}}
        self.store = SimpleNamespace(
            protocol_lock=Mock(return_value={"decision": self.selected}),
            calibration_lock=Mock(return_value={"decision": {"budget": 1024}}),
            publication=Mock(return_value={"version": "L1-v1", "body": "unit fixture"}),
            worlds={})
        self.job = {"id": "j1", "phase": "test", "stage": "A", "condition": "T2", "role": "investigator",
                    "lineage": "L1", "version": None, "budget": None, "protocol_version": None, "control": None}

    def test_held_out_uses_locked_version_not_latest_or_best_test_result(self):
        before = copy.deepcopy(self.job)
        resolved, protocol = resolve_job(self.store, self.job)
        self.assertEqual(resolved["protocol_version"], "L1-v2")
        self.assertEqual(resolved["budget"], 2048)
        self.assertEqual(protocol, self.selected["lineages"]["L1"]["protocol"])
        self.assertEqual(self.job, before)
        self.store.publication.assert_not_called()

    def test_missing_protocol_never_replaced_by_typed_baseline(self):
        self.job["lineage"] = "L2"
        resolved, protocol = resolve_job(self.store, self.job)
        self.assertIsNone(protocol)
        self.assertIsNone(resolved["protocol_version"])

    def test_single_context_controls_also_wait_for_lock(self):
        self.job.update(condition="C0", stage="D", lineage=None)
        _, protocol = resolve_job(self.store, self.job)
        self.store.protocol_lock.assert_called_once_with()
        self.assertIsNone(protocol)

    def test_validation_uses_assigned_version_and_calibration_only(self):
        self.job.update(phase="validation", version=1)
        resolved, protocol = resolve_job(self.store, self.job)
        self.assertEqual(resolved["budget"], 1024)
        self.assertEqual(protocol["version"], "L1-v1")
        self.store.publication.assert_called_once_with("L1", 1)
        self.store.protocol_lock.assert_not_called()

    def test_crash_only_on_assigned_c_and_authentication_ablation_persists(self):
        self.job.update(stage="C", condition="C1", phase="robustness", control="crash")
        resolved, _ = resolve_job(self.store, self.job)
        self.assertTrue(resolved["crash_after_commit"])
        self.job["stage"] = "D"
        resolved, _ = resolve_job(self.store, self.job)
        self.assertNotIn("crash_after_commit", resolved)
        self.job["control"] = "authentication_ablation"
        resolved, _ = resolve_job(self.store, self.job)
        self.assertTrue(resolved["verification_disabled"])


if __name__ == "__main__":
    unittest.main()
