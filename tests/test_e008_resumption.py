import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from research.e008_locks import read, write_once
from research.e008_live import recover, save_network_result
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy
from research.e008_resumption import (CUTOVER, FAILURE, NEXT, MODEL_AMENDMENT_SHA, PLAN, STOP_SHA,
    audit_resumption, execution_binding, recovery_gate, require_recovered, root, verify_scope)


class ResumptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.guard = SeriesLedger(self.study, resource_policy([{"id": "j1"}, {"id": "j2"}]))
        self.guard.start()
        self.provider = Mock(model="fixed-primary", ledger=self.guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.provider.models.side_effect = self.available
        self.value = {"models": {"primary": "fixed-primary", "secondary": "fixed-secondary"},
                      "recovery_plan": copy.deepcopy(PLAN)}
        self.wait = patch("research.e008_live.wait_until").start()
        self.addCleanup(patch.stopall)

    def transport(self, status=200, sent=True):
        with self.provider.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "transport_bytes", "worker": None, "method": "GET",
                "http_status": status, "request_sent": sent, "response_complete": status == 200,
                "request_body_bytes": 0, "response_body_bytes": 12}) + "\n")

    def available(self):
        self.transport()
        return ["fixed-primary"]

    def gate(self):
        return recovery_gate(self.study, self.value, self.provider)

    def test_original_still_stops_new_route_uses_slot_two_without_replay(self):
        stopped = self.study / "recovery" / FAILURE / "1-result.json"
        self.transport(None, False)
        save_network_result(stopped, self.provider, 0,
                            {"available": False, "failure_type": "OSError", "http_status": None, "action": "stop"})
        before = stopped.read_bytes()
        with self.assertRaisesRegex(SeriesStopped, "non-transient"):
            recover(self.study, FAILURE, self.provider)
        self.provider.models.assert_not_called()
        self.assertEqual(self.gate(), {"pass": True, "slot": 2, "model": "fixed-primary"})
        self.assertEqual(self.gate()["slot"], 2)
        self.assertEqual(self.provider.models.call_count, 1)
        self.provider.respond.assert_not_called()
        self.assertEqual(stopped.read_bytes(), before)
        self.assertEqual(read(root(self.study) / "recovery/2-started.json")["delay"], 120)
        self.assertFalse((self.study / "recovery" / FAILURE / "complete.json").exists())

    def test_absence_uses_only_remaining_two_slots_then_cached_stop(self):
        self.provider.models.side_effect = lambda: (self.transport(), [])[1]
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "exhausted"):
                self.gate()
        self.assertEqual(self.provider.models.call_count, 2)
        self.assertEqual(read(root(self.study) / "recovery/3-started.json")["delay"], 300)
        self.provider.respond.assert_not_called()

    def test_second_remaining_slot_can_succeed(self):
        calls = iter([[], ["fixed-primary"]])
        self.provider.models.side_effect = lambda: (self.transport(), next(calls))[1]
        self.assertEqual(self.gate()["slot"], 3)
        self.assertEqual(self.gate()["slot"], 3)
        self.assertEqual(self.provider.models.call_count, 2)

    def test_new_unsent_oserror_is_not_exempted(self):
        def fail():
            self.transport(None, False)
            raise OSError("synthetic unsent failure")
        self.provider.models.side_effect = fail
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "stopped"):
                self.gate()
        self.assertEqual(self.provider.models.call_count, 1)

    def test_auth_error_stops_without_second_get(self):
        def fail():
            self.transport(401)
            raise RuntimeError("HTTP401")
        self.provider.models.side_effect = fail
        with self.assertRaises(SeriesStopped):
            self.gate()
        self.assertEqual(self.provider.models.call_count, 1)

    def test_stop_file_blocks_any_request(self):
        (self.study / "STOP").touch()
        with self.assertRaisesRegex(SeriesStopped, "STOP"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_original_deadline_not_reset(self):
        with patch.object(self.guard, "remaining", side_effect=SeriesStopped("deadline")):
            with self.assertRaisesRegex(SeriesStopped, "deadline"):
                self.gate()
        self.provider.models.assert_not_called()

    def test_orphan_sending_is_not_replayed(self):
        base = root(self.study) / "recovery"
        write_once(base / "2-started.json", {"at": 0, "delay": 120, "model": "fixed-primary"})
        write_once(base / "2-sending.json", {"at": 120})
        with self.assertRaisesRegex(SeriesStopped, "orphan"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_started_but_unsent_resumes_same_slot(self):
        write_once(root(self.study) / "recovery/2-started.json", {"at": 5, "delay": 120, "model": "fixed-primary"})
        self.assertEqual(self.gate()["slot"], 2)
        self.wait.assert_called_once_with(125, self.guard)

    def test_result_and_trace_tampering_denied(self):
        self.gate()
        self.provider.log.write_bytes(b"modified")
        with self.assertRaises(PermissionError):
            self.gate()
        self.assertEqual(self.provider.models.call_count, 1)

    def test_complete_file_alone_does_not_authorize(self):
        write_once(root(self.study) / "recovery/complete.json", {"pass": True, "slot": 2, "model": "fixed-primary"})
        with patch("research.e008_resumption.require_prepared", return_value={}):
            with self.assertRaises(SeriesStopped):
                require_recovered(self.study, self.value)
        self.provider.models.assert_not_called()

    def test_changed_model_or_plan_denied(self):
        self.value["models"]["primary"] = "substitute"
        with self.assertRaises(PermissionError):
            self.gate()
        self.value["models"]["primary"] = self.provider.model
        self.value["recovery_plan"]["remaining_catalogue_slots"].append(4)
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_other_ledger_denied(self):
        self.provider.ledger = SimpleNamespace(study=self.study / "new-clock")
        with self.assertRaises(PermissionError):
            self.gate()

    def test_bindings_preserve_old_revision_and_attribute_new_revision(self):
        a001 = {"commit": "old", "amendment_sha256": "model-sha"}
        a002 = {"commit": "new", "resumption_sha256": "resume-sha"}
        amendment = {"proposed_models": self.value["models"]}
        with patch("research.e008_transition.require_prepared", return_value=a001), \
             patch("research.e008_resumption.require_prepared", return_value=a002):
            before = execution_binding(self.study, {"id": FAILURE, "model_role": "primary"}, amendment, self.value)
            after = execution_binding(self.study, {"id": NEXT, "model_role": "primary"}, amendment, self.value)
        self.assertEqual(before["commit"], "old")
        self.assertNotIn("resumption_sha256", before)
        self.assertEqual(after["commit"], "new")
        self.assertEqual(after["amendment_sha256"], "model-sha")
        self.assertEqual(after["resumption_sha256"], "resume-sha")

    def test_final_audit_reconstructs_get_and_rejects_bad_chronology(self):
        # Simulated times only; transport remains an offline fixture.
        with patch("research.e008_resumption.time.time", side_effect=[10, 130]), \
             patch.object(self.guard, "check_context", return_value=100):
            self.gate()
        timeline = {FAILURE: {"finished": 1}, NEXT: {"started": 150}}
        admission = {"prepared_at": 5, "commit": "new", "resumption_sha256": "sha"}
        with patch("research.e008_resumption.require_prepared", return_value=admission), \
             patch("research.e008_resumption.verify_preserved"):
            report = audit_resumption(self.study, self.value, timeline)
            self.assertTrue(report["pass"])
            self.assertEqual(report["overhead_already_in_main_ledger"]["metadata_requests"], 1)
            timeline[NEXT]["started"] = 100
            with self.assertRaisesRegex(PermissionError, "chronology"):
                audit_resumption(self.study, self.value, timeline)


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.registration = {"schedule": [{"id": f"j{n:05d}"} for n in range(1, 3427)]}
        self.amendment = {"implementation_hashes": {"research/e008_live.py": "old", "prompts/A.txt": "fixed"},
                          "proposed_models": {"primary": "p", "secondary": "s"}, "invariants": {"clock": 123}}
        self.current = {**self.amendment["implementation_hashes"], "research/e008_live.py": "new",
                        "research/e008_resumption.py": "new"}
        self.value = {"amendment_id": "E008-A002", "status": "approved_for_execution", "preregistered": True,
            "human_authorization": "Да, оформить отдельное возобновление без повторов",
            "cutover_after_ordinal": CUTOVER, "first_pending_id": NEXT, "models": self.amendment["proposed_models"],
            "invariants": self.amendment["invariants"], "recovery_plan": PLAN,
            "model_amendment_sha256": MODEL_AMENDMENT_SHA, "stop_sha256": STOP_SHA,
            "base_implementation_hashes": self.amendment["implementation_hashes"], "implementation_hashes": self.current}

    def test_narrow_source_overlay_allowed(self):
        verify_scope(self.registration, self.amendment, self.value, self.current)

    def test_scientific_source_change_and_deletion_denied(self):
        for current in ({**self.current, "prompts/A.txt": "changed"},
                        {k: v for k, v in self.current.items() if k != "prompts/A.txt"}):
            with self.subTest(current=current):
                value = {**self.value, "implementation_hashes": current}
                with self.assertRaises(PermissionError):
                    verify_scope(self.registration, self.amendment, value, current)

    def test_unauthorized_models_clocks_boundary_or_failure_denied(self):
        for field, changed in (("models", {"primary": "other", "secondary": "s"}),
                               ("invariants", {"clock": 456}), ("cutover_after_ordinal", 1280),
                               ("first_pending_id", "j01281"), ("status", "draft"),
                               ("stop_sha256", "another-error"), ("human_authorization", "")):
            with self.subTest(field=field), self.assertRaises(PermissionError):
                verify_scope(self.registration, self.amendment, {**self.value, field: changed}, self.current)


if __name__ == "__main__":
    unittest.main()
