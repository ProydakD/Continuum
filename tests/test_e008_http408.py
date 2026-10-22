import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from research.common import digest
from research.e008_locks import read, write_once
from research.e008_live import resume_failure
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy, provider_failure_action
from research import e008_http408 as h, e008_resumption as prior


class Http408Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        guard = SeriesLedger(self.study, resource_policy([{"id": "j1"}, {"id": "j2"}]))
        guard.start()
        self.provider = Mock(model="p", ledger=guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.provider.models.side_effect = self.available
        self.value = {"amendment_id": h.IDENTITY, "models": {"primary": "p", "secondary": "s"},
                      "recovery_plan": copy.deepcopy(h.PLAN)}
        self.wait = patch("research.e008_live.wait_until").start()
        self.admitted = patch.object(h, "require_prepared", return_value={
            "prepared_at": 5, "commit": "a003", "resumption_sha256": "new-sha"}).start()
        self.addCleanup(patch.stopall)

    def transport(self, status=200, method="GET", worker=None, sent=True):
        with self.provider.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "transport_bytes", "method": method, "worker": worker,
                "http_status": status, "request_sent": sent, "response_complete": status is not None,
                "request_body_bytes": 0, "response_body_bytes": 12}) + "\n")

    def available(self):
        self.transport()
        return ["p"]

    def gate(self):
        return prior.recovery_gate(self.study, self.value, self.provider)

    def test_classifier_and_future_408_remain_stop(self):
        self.transport(408, "POST", "j01909")
        self.assertEqual(provider_failure_action("RuntimeError", 408), "stop")
        for identity in ("j01909", "j01910"):
            self.transport(408, "POST", identity)
            with self.assertRaisesRegex(SeriesStopped, "non-transient"):
                resume_failure(self.study, {"id": identity},
                    {"failure_origin": "provider", "failure_type": "RuntimeError"}, self.provider)
        self.provider.models.assert_not_called()

    def test_sealed_failure_ignores_later_partial_journal_tail(self):
        for status in (200, 200, 408):
            self.transport(status, "POST", h.FAILURE)
        raw = self.provider.log.read_bytes()
        write_once(self.study / "units" / h.FAILURE / "provider-span.json",
                   {"offset": 0, "length": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "worker": h.FAILURE})
        with self.provider.log.open("ab") as f:
            f.write(b'{"partial_future_request":')
        h.verify_failed_transport(self.study)
        self.provider.models.assert_not_called()
        self.provider.log.write_bytes(raw.replace(b'408', b'429') + b'{"partial_future_request":')
        with self.assertRaises(PermissionError):
            h.verify_failed_transport(self.study)

    def test_sealed_other_status_or_unsent_transport_denied(self):
        span_path = self.study / "units" / h.FAILURE / "provider-span.json"
        for status, sent in ((429, True), (408, False)):
            self.provider.log.write_bytes(b"")
            for value in (200, 200):
                self.transport(value, "POST", h.FAILURE)
            self.transport(status, "POST", h.FAILURE, sent=sent)
            raw = self.provider.log.read_bytes()
            span_path.parent.mkdir(parents=True, exist_ok=True)
            span_path.write_text(json.dumps({"offset": 0, "length": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(), "worker": h.FAILURE}), encoding="utf-8")
            with self.assertRaises(PermissionError):
                h.verify_failed_transport(self.study)

    def test_single_get_cached_no_responses_or_original_recovery(self):
        result = self.gate()
        self.assertEqual(result, {"pass": True, "attempts": 1, "model": "p"})
        self.assertEqual(self.gate(), result)
        self.assertEqual(prior.require_recovered(self.study, self.value), result)
        self.assertEqual(self.provider.models.call_count, 1)
        self.provider.respond.assert_not_called()
        self.assertFalse((self.study / "recovery" / h.FAILURE).exists())
        self.assertEqual(read(h.recovery_root(self.study) / "1-started.json")["delay"], 30)

    def test_missing_model_three_slots_only(self):
        self.provider.models.side_effect = lambda: (self.transport(), [])[1]
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "exhausted"):
                self.gate()
        self.assertEqual(self.provider.models.call_count, 3)
        self.assertEqual([read(h.recovery_root(self.study) / f"{n}-started.json")["delay"] for n in (1, 2, 3)], [30, 120, 300])
        self.provider.respond.assert_not_called()

    def test_second_slot_success(self):
        calls = iter([[], ["p"]])
        self.provider.models.side_effect = lambda: (self.transport(), next(calls))[1]
        self.assertEqual(self.gate()["attempts"], 2)
        self.assertEqual(self.gate()["attempts"], 2)
        self.assertEqual(self.provider.models.call_count, 2)

    def test_new_auth_or_408_or_unsent_error_is_fatal(self):
        for status, error in ((401, RuntimeError), (408, RuntimeError), (None, OSError)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                self.study = Path(folder)
                self.provider.log = self.study / "provider.jsonl"
                self.provider.log.write_bytes(b"")
                self.provider.ledger = SeriesLedger(self.study, resource_policy([{"id": "j1"}]))
                self.provider.ledger.start()
                def fail():
                    self.transport(status, sent=status is not None)
                    raise error("synthetic")
                self.provider.models.reset_mock()
                self.provider.models.side_effect = fail
                for _ in range(2):
                    with self.assertRaises(SeriesStopped):
                        self.gate()
                self.assertEqual(self.provider.models.call_count, 1)

    def test_stop_and_original_deadline_prevent_requests(self):
        (self.study / "STOP").touch()
        with self.assertRaises(SeriesStopped):
            self.gate()
        (self.study / "STOP").unlink()
        with patch.object(self.provider.ledger, "remaining", side_effect=SeriesStopped("deadline")):
            with self.assertRaisesRegex(SeriesStopped, "deadline"):
                self.gate()
        self.provider.models.assert_not_called()

    def test_orphan_send_is_not_replayed(self):
        base = h.recovery_root(self.study)
        write_once(base / "1-started.json", {"at": 5, "delay": 30, "model": "p"})
        write_once(base / "1-sending.json", {"at": 35})
        with self.assertRaisesRegex(SeriesStopped, "orphan"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_unsent_started_slot_retains_clock(self):
        write_once(h.recovery_root(self.study) / "1-started.json", {"at": 5, "delay": 30, "model": "p"})
        self.gate()
        self.wait.assert_called_once_with(35, self.provider.ledger)

    def test_trace_tamper_and_complete_only_denied(self):
        write_once(h.recovery_root(self.study) / "complete.json", {"pass": True, "attempts": 1, "model": "p"})
        with self.assertRaises(SeriesStopped):
            h.require_recovered(self.study, self.value)
        self.gate()
        self.provider.log.write_bytes(b"tamper")
        with self.assertRaises(PermissionError):
            self.gate()
        self.assertEqual(self.provider.models.call_count, 1)

    def test_changed_model_plan_and_ledger_denied(self):
        for changes in ({"models": {"primary": "other"}}, {"recovery_plan": {}}):
            with self.assertRaises(PermissionError):
                h.recovery_gate(self.study, {**self.value, **changes}, self.provider)
        self.provider.ledger = SimpleNamespace(study=self.study / "reset-clock")
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_exact_failure_only_and_parent_reconciliation_preserved(self):
        outcome = self.study / "units" / h.FAILURE / "outcome.json"
        result = {"failure": "retained"}
        write_once(outcome, {"result": result})
        stop = self.study / "stop.json"
        write_once(stop, {"failed_outcome_sha256": digest(outcome)})
        value = {**self.value, "stop_path": str(stop)}
        with patch.object(h, "require_recovered"), patch.object(h, "parent", return_value={}), \
             patch.object(prior, "reconciles", return_value=False) as old:
            self.assertTrue(h.reconciles(self.study, {"id": h.FAILURE}, result, value))
            with self.assertRaises(PermissionError):
                h.reconciles(self.study, {"id": h.FAILURE}, {}, value)
            self.assertFalse(h.reconciles(self.study, {"id": h.NEXT}, result, value))
            old.assert_called_once()

    def test_old_bindings_unchanged_new_binding_attributes_a003(self):
        previous = {"commit": "r1", "resumption_sha256": "r1-sha", "amendment_sha256": "a001"}
        with patch.object(h, "parent", return_value={}), patch.object(prior, "execution_binding", return_value=previous.copy()):
            self.assertEqual(h.execution_binding(self.study, {"id": h.FAILURE}, {}, self.value), previous)
        with patch.object(h, "parent", return_value={}), patch.object(prior, "execution_binding", return_value=previous.copy()):
            after = h.execution_binding(self.study, {"id": h.NEXT}, {}, self.value)
        self.assertEqual(after["commit"], "a003")
        self.assertEqual(after["prior_resumption_sha256"], h.PRIOR_SHA)
        self.assertEqual(after["amendment_sha256"], "a001")

    def test_final_audit_chronology_and_exact_get_accounting(self):
        with patch("research.e008_live.time.time", side_effect=[10, 40]), \
             patch.object(self.provider.ledger, "check_context", return_value=100):
            self.gate()
        timeline = {h.FAILURE: {"finished": 1}, h.NEXT: {"started": 50}}
        with patch.object(h, "parent", return_value={}), patch.object(prior, "audit_resumption", return_value={"pass": True}), \
             patch.object(h, "verify_preserved"):
            result = h.audit_resumption(self.study, self.value, timeline)
            self.assertEqual(result["overhead_already_in_main_ledger"]["metadata_requests"], 1)
            self.assertTrue(result["prior_operational_resumption"]["pass"])
            timeline[h.NEXT]["started"] = 35
            with self.assertRaises(PermissionError):
                h.audit_resumption(self.study, self.value, timeline)


class Http408ScopeTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"implementation_hashes": {"science.py": "fixed", "research/e008_resumption.py": "old"},
                         "models": {"primary": "p", "secondary": "s"}, "invariants": {"deadline": 123}}
        self.current = {**self.previous["implementation_hashes"], "research/e008_resumption.py": "new",
                        "research/e008_http408.py": "new", "tests/test_e008_http408.py": "new"}
        self.registration = {"schedule": [{"id": f"j{n:05d}"} for n in range(1, 3427)]}
        self.value = {"amendment_id": h.IDENTITY, "status": "approved_for_execution", "preregistered": True,
            "human_authorization": "Продолжай", "authorization_scope": "exact j01909 HTTP408; preserve1909; firstj01910; no repeats",
            "prior_resumption_sha256": h.PRIOR_SHA, "stop_sha256": h.STOP_SHA,
            "model_amendment_sha256": prior.MODEL_AMENDMENT_SHA, "cutover_after_ordinal": h.CUTOVER,
            "first_pending_id": h.NEXT, "models": self.previous["models"], "invariants": self.previous["invariants"],
            "recovery_plan": h.PLAN, "base_implementation_hashes": self.previous["implementation_hashes"],
            "implementation_hashes": self.current}
        patch.object(h, "parent", return_value=self.previous).start()
        self.old_scope = patch.object(prior, "verify_scope").start()
        self.addCleanup(patch.stopall)

    def test_narrow_overlay_verifies_immutable_parent_scope(self):
        h.verify_scope(self.registration, {}, self.value, self.current)
        self.old_scope.assert_called_once_with(self.registration, {}, self.previous, self.previous["implementation_hashes"])

    def test_changed_authorization_models_limits_identity_or_boundary_denied(self):
        for key, changed in (("human_authorization", ""), ("authorization_scope", "all408"), ("models", {}),
                             ("invariants", {}), ("cutover_after_ordinal", 1908), ("first_pending_id", "j01909"),
                             ("prior_resumption_sha256", "changed"), ("stop_sha256", "changed"),
                             ("recovery_plan", {}), ("status", "draft"), ("preregistered", False)):
            with self.subTest(field=key), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, key: changed}, self.current)

    def test_scientific_edits_unregistered_bytes_and_deletions_denied(self):
        for changed in ({**self.current, "science.py": "different"},
                        {k:v for k,v in self.current.items() if k != "science.py"},
                        {**self.current, "unregistered.py": "new"}):
            with self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "implementation_hashes": changed}, changed)
        with self.assertRaises(PermissionError):
            h.verify_scope(self.registration, {}, self.value, {**self.current, "research/e008_http408.py": "unfrozen"})
