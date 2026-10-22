import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.common import digest
from research.e008_locks import read, write_once
from research.e008_live import resume_failure
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy
from research import e008_minute_resumption as h, e008_http408 as prior, e008_resumption as dispatch


class MinuteResumptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.study = Path(temporary.name)
        guard = SeriesLedger(self.study, resource_policy([{"id": "j1"}]))
        guard.start()
        self.provider = Mock(model="p", ledger=guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.provider.models.side_effect = self.available
        self.value = {"amendment_id": h.IDENTITY, "models": {"primary": "p", "secondary": "s"},
                      "recovery_plan": copy.deepcopy(h.PLAN)}
        self.clock = 100.0
        patch("research.e008_minute_recovery.time.time", side_effect=lambda: self.clock).start()
        patch.object(guard, "check_context", return_value=10000).start()
        patch("research.e008_minute_recovery.wait_until", side_effect=self.advance).start()
        patch.object(h, "require_prepared", return_value={
            "prepared_at": 90, "commit": "a004", "resumption_sha256": "a004-sha"}).start()
        self.addCleanup(patch.stopall)

    def advance(self, deadline, guard):
        self.assertIs(guard, self.provider.ledger)
        self.clock = max(self.clock, deadline)

    def transport(self, status=200, method="GET", worker=None, sent=True):
        with self.provider.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "transport_bytes", "method": method, "worker": worker,
                "http_status": status, "request_sent": sent, "response_complete": True,
                "request_body_bytes": 0, "response_body_bytes": 12}) + "\n")

    def available(self):
        self.transport()
        return [self.provider.model]

    def gate(self):
        return dispatch.recovery_gate(self.study, self.value, self.provider)

    def failure(self, identity=h.NEXT, status=502, sent=True, binding=None):
        job = {"id": identity, "model_role": "primary", "budget": None, "protocol_version": None}
        result = {"failure_origin": "provider", "failure_type": "RuntimeError",
                  "failure": f"provider HTTP status {status}; no retry or redirect"}
        offset = self.provider.log.stat().st_size
        self.transport(200, "POST", identity)
        self.transport(status, "POST", identity, sent=sent)
        raw = self.provider.log.read_bytes()[offset:]
        unit = self.study / "units" / identity
        write_once(unit / "provider-span.json", {"offset": offset, "length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "worker": identity})
        resolved = {**job, "budget": 4096, "protocol_version": "L1-v2"}
        write_once(unit / "outcome.json", {"job": resolved, "result": result, "status": "failed"})
        write_once(unit / "execution-binding.json", binding or {"commit": "a004"})
        return job, result

    def test_initial_gate_cached_offline_and_old_episode_untouched(self):
        old = self.study / "recovery" / h.FAILURE / "retained.json"
        write_once(old, {"three_old_attempts": "immutable"})
        before = old.read_bytes()
        expected = {"pass": True, "attempts": 1, "model": "p"}
        self.assertEqual(self.gate(), expected)
        self.assertEqual(self.gate(), expected)
        self.assertEqual(dispatch.require_recovered(self.study, self.value), expected)
        self.assertEqual(old.read_bytes(), before)
        self.provider.models.assert_called_once()
        self.provider.respond.assert_not_called()

    def test_ten_missing_checks_stop_and_cannot_be_read_as_recovered(self):
        self.provider.models.side_effect = lambda: (self.transport(), [])[1]
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "HTTP502=0, model_absent=10"):
                self.gate()
        with self.assertRaisesRegex(SeriesStopped, "ten attempts exhausted"):
            h.require_recovered(self.study, self.value)
        self.assertEqual(self.provider.models.call_count, 10)
        self.assertEqual(self.clock, 700)
        self.provider.respond.assert_not_called()

    def test_plan_model_and_constants_must_stay_frozen(self):
        for field, value in (("models", {"primary": "other"}), ("recovery_plan", {})):
            with self.assertRaises(PermissionError):
                h.recovery_gate(self.study, {**self.value, field: value}, self.provider)
        with patch.object(h.minute, "ATTEMPTS", 11), self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_no_completion_without_proof(self):
        write_once(h.recovery_root(self.study) / "complete.json", {"pass": True})
        with self.assertRaises(PermissionError):
            h.require_recovered(self.study, self.value)
        self.provider.models.assert_not_called()

    def test_short_wait_rejected_by_offline_check(self):
        self.gate()
        path = h.recovery_root(self.study) / "1-sending.json"
        path.write_text(json.dumps({"at": 159}), encoding="utf-8")
        with self.assertRaisesRegex(PermissionError, "wait changed"):
            h.require_recovered(self.study, self.value)
        self.provider.models.assert_called_once()

    def test_changed_trace_and_completion_rejected(self):
        self.gate()
        path = h.recovery_root(self.study) / "complete.json"
        original = path.read_bytes()
        path.write_text(json.dumps({"pass": True, "attempts": 2, "model": "p"}), encoding="utf-8")
        with self.assertRaises(PermissionError):
            h.require_recovered(self.study, self.value)
        path.write_bytes(original)
        self.provider.log.write_bytes(b"changed")
        with self.assertRaises(PermissionError):
            h.require_recovered(self.study, self.value)

    def test_future_502_uses_new_gate_and_preserves_failed_outcome(self):
        self.gate()
        job, result = self.failure()
        outcome = self.study / "units" / job["id"] / "outcome.json"
        before = outcome.read_bytes()
        with patch.object(h, "execution_binding", return_value={"commit": "a004"}):
            recovered = resume_failure(self.study, job, result, self.provider, resumption=self.value)
            self.assertEqual(recovered["attempts"], 1)
            resume_failure(self.study, job, result, self.provider, resumption=self.value)
        self.assertEqual(self.provider.models.call_count, 2)
        self.assertEqual(outcome.read_bytes(), before)
        self.provider.respond.assert_not_called()
        self.assertTrue((self.study / "recovery" / job["id"] / "complete.json").exists())

    def test_future_secondary_model_stays_secondary(self):
        self.gate()
        job, result = self.failure()
        job["model_role"] = "secondary"
        path = self.study / "units" / job["id"] / "outcome.json"
        value = read(path)
        value["job"] = job
        path.write_text(json.dumps(value), encoding="utf-8")
        with patch.object(h, "execution_binding", return_value={"commit": "a004"}):
            with self.assertRaisesRegex(PermissionError, "assigned model"):
                h.recover_failure(self.study, job, result, self.provider, self.value)
            self.provider.model = "s"
            recovered = h.recover_failure(self.study, job, result, self.provider, self.value)
        self.assertEqual(recovered["model"], "s")

    def test_future_non502_remains_fatal(self):
        job, result = self.failure(status=408)
        with self.assertRaisesRegex(SeriesStopped, "non-transient"):
            resume_failure(self.study, job, result, self.provider, resumption=self.value)
        self.provider.models.assert_not_called()

    def test_old_failures_and_no_a004_use_original_recovery(self):
        for identity, value in ((h.FAILURE, self.value), (h.NEXT, None),
                                (h.NEXT, {"amendment_id": "E008-A003"})):
            self.transport(502, "POST", identity)
            with patch("research.e008_live.recover") as old, patch.object(h, "recover_failure") as new:
                resume_failure(self.study, {"id": identity},
                    {"failure_origin": "provider", "failure_type": "RuntimeError"},
                    self.provider, resumption=value)
                old.assert_called_once()
                new.assert_not_called()

    def test_future_failure_binding_transport_and_result_are_verified(self):
        job, result = self.failure(binding={"commit": "wrong"})
        with patch.object(h, "execution_binding", return_value={"commit": "a004"}):
            with self.assertRaises(PermissionError):
                h.verify_future_failure(self.study, job, result, self.value)
        with self.assertRaises(PermissionError):
            h.verify_future_failure(self.study, {"id": h.FAILURE}, result, self.value)
        with self.assertRaises(PermissionError):
            h.verify_future_failure(self.study, job, {**result, "failure_origin": "worker"}, self.value)
        with self.assertRaises(PermissionError):
            h.verify_future_failure(self.study, {**job, "model_role": "secondary"}, result, self.value)
        other_job, other_result = self.failure(identity="j02141", sent=False)
        with patch.object(h, "execution_binding", return_value={"commit": "a004"}), self.assertRaises(PermissionError):
            h.verify_future_failure(self.study, other_job, other_result, self.value)
        self.provider.models.assert_not_called()

    def test_future_sealed_proof_ignores_incomplete_tail_but_not_tamper(self):
        job, result = self.failure()
        raw = self.provider.log.read_bytes()
        self.provider.log.write_bytes(raw + b'{"partial":')
        with patch.object(h, "execution_binding", return_value={"commit": "a004"}):
            h.verify_future_failure(self.study, job, result, self.value)
            self.provider.log.write_bytes(raw.replace(b"502", b"429"))
            with self.assertRaises(PermissionError):
                h.verify_future_failure(self.study, job, result, self.value)

    def test_old_binding_unchanged_new_binding_is_a004(self):
        old = {"commit": "a003", "resumption_sha256": "a003-sha", "amendment_sha256": "a001"}
        with patch.object(h, "parent", return_value={}), patch.object(prior, "execution_binding", side_effect=lambda *args: old.copy()):
            self.assertEqual(dispatch.execution_binding(self.study, {"id": h.FAILURE}, {}, self.value), old)
            after = dispatch.execution_binding(self.study, {"id": h.NEXT}, {}, self.value)
        self.assertEqual(after, {**old, "commit": "a004", "resumption_sha256": "a004-sha",
                                 "prior_resumption_sha256": h.PRIOR_SHA})

    def test_exact_retained_failure_and_nested_reconciliation(self):
        outcome = self.study / "units" / h.FAILURE / "outcome.json"
        result = {"failure": "retained"}
        write_once(outcome, {"result": result})
        stop = self.study / "stop.json"
        write_once(stop, {"failed_outcome_sha256": digest(outcome)})
        value = {**self.value, "stop_path": str(stop)}
        with patch.object(h, "require_recovered"), patch.object(h, "parent", return_value={}), \
             patch.object(prior, "reconciles", return_value=False) as old:
            self.assertTrue(dispatch.reconciles(self.study, {"id": h.FAILURE}, result, value))
            with self.assertRaises(PermissionError):
                h.reconciles(self.study, {"id": h.FAILURE}, {}, value)
            self.assertFalse(h.reconciles(self.study, {"id": h.NEXT}, result, value))
            old.assert_called_once()

    def test_initial_and_future_audit_account_for_both_gets_once(self):
        self.gate()
        self.clock = 180
        job, result = self.failure()
        with patch.object(h, "execution_binding", return_value={"commit": "a004"}):
            h.recover_failure(self.study, job, result, self.provider, self.value)
            timeline = {h.FAILURE: {"finished": 80}, h.NEXT: {"started": 170, "finished": 180}}
            with patch.object(h, "parent", return_value={}), patch.object(prior, "audit_resumption", return_value={"pass": True}), \
                 patch.object(h, "verify_preserved"):
                audit = dispatch.audit_resumption(self.study, self.value, timeline)
                self.assertEqual(audit["overhead_already_in_main_ledger"]["metadata_requests"], 2)
                self.assertEqual(audit["future_http502_recoveries"], [{"job": h.NEXT, "pass": True, "attempts": 1, "model": "p"}])
                timeline[h.NEXT]["started"] = 159
                with self.assertRaises(PermissionError):
                    h.audit_resumption(self.study, self.value, timeline)

    def test_episode_cannot_overlap_next_worker_or_contain_responses(self):
        self.gate()
        with self.assertRaises(PermissionError):
            h.audit_episode(self.study, h.IDENTITY, "p", 90, 159)
        with self.assertRaises(PermissionError):
            h.audit_episode(self.study, h.IDENTITY, "p", 101, 200)
        with tempfile.TemporaryDirectory() as folder:
            self.study = Path(folder)
            self.provider.log = self.study / "provider.jsonl"
            self.provider.log.write_bytes(b"")
            self.provider.ledger.study = self.study.resolve()
            self.provider.models.side_effect = lambda: (self.transport(method="POST"), ["p"])[1]
            self.gate()
            with self.assertRaisesRegex(PermissionError, "exactly one GET"):
                h.audit_episode(self.study, h.IDENTITY, "p", 90, 1000)

    def test_future_admission_rejects_any_started_context(self):
        rows = [{"status": "completed", "started": 1}] * h.CUTOVER + [
            {"status": "pending", "started": None} for _ in range(3426 - h.CUTOVER)]
        rows[h.CUTOVER]["started"] = 1
        with patch.object(dispatch, "ledger_rows", return_value=rows), self.assertRaises(SeriesStopped):
            dispatch.prepare_admission(self.study, self.value)
        self.assertFalse(h.root(self.study).exists())


class MinuteScopeTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"implementation_hashes": {"science.py": "fixed", "research/e008_live.py": "old"},
                         "models": {"primary": "p", "secondary": "s"}, "invariants": {"deadline": 123}}
        self.current = {**self.previous["implementation_hashes"], "research/e008_live.py": "new",
                        "research/e008_minute_resumption.py": "new"}
        self.registration = {"schedule": [{"id": f"j{n:05d}"} for n in range(1, 3427)]}
        self.value = {"amendment_id": h.IDENTITY, "status": "approved_for_execution", "preregistered": True,
            "human_authorization": h.AUTHORIZATION, "authorization_sha256": h.AUTHORIZATION_SHA,
            "authorization_scope": "preserve2139; firstj02140; same models; future502 60s/10; no repeats",
            "prior_resumption_sha256": h.PRIOR_SHA, "stop_sha256": h.STOP_SHA,
            "model_amendment_sha256": dispatch.MODEL_AMENDMENT_SHA, "cutover_after_ordinal": h.CUTOVER,
            "first_pending_id": h.NEXT, "models": self.previous["models"], "invariants": self.previous["invariants"],
            "recovery_plan": h.PLAN, "base_implementation_hashes": self.previous["implementation_hashes"],
            "implementation_hashes": self.current}
        patch.object(h, "parent", return_value=self.previous).start()
        self.old_scope = patch.object(prior, "verify_scope").start()
        self.addCleanup(patch.stopall)

    def test_narrow_overlay_verifies_immutable_parent(self):
        dispatch.verify_scope(self.registration, {}, self.value, self.current)
        self.old_scope.assert_called_once_with(self.registration, {}, self.previous, self.previous["implementation_hashes"])

    def test_authorization_models_limits_identity_or_boundary_cannot_change(self):
        for key, changed in (("human_authorization", ""), ("authorization_sha256", ""), ("models", {}),
                             ("invariants", {}), ("cutover_after_ordinal", 2138), ("first_pending_id", h.FAILURE),
                             ("prior_resumption_sha256", ""), ("stop_sha256", ""), ("recovery_plan", {}),
                             ("status", "draft"), ("preregistered", False), ("authorization_scope", "all-errors")):
            with self.subTest(field=key), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, key: changed}, self.current)

    def test_scientific_edits_deletions_and_unregistered_source_rejected(self):
        for current in ({**self.current, "science.py": "changed"},
                        {k: v for k, v in self.current.items() if k != "science.py"},
                        {**self.current, "unregistered.py": "new"}):
            with self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "implementation_hashes": current}, current)
        with self.assertRaises(PermissionError):
            h.verify_scope(self.registration, {}, self.value, {**self.current, "research/e008_live.py": "unfrozen"})


class HistoricalA003Tests(unittest.TestCase):
    def test_dispatch_passes_historical_flag_only_to_old_parent(self):
        with patch.object(prior, "load_resumption", return_value="historical") as load:
            self.assertEqual(dispatch.load_resumption("study", prior.PROJECT / prior.RESUMPTION, {}, _historical=True), "historical")
            load.assert_called_once_with("study", prior.PROJECT / prior.RESUMPTION, {}, _historical=True)
        from research import e008_direct_resumption
        with self.assertRaises(PermissionError):
            dispatch.load_resumption("study", h.PROJECT / e008_direct_resumption.RESUMPTION, {}, _historical=True)

    def test_historical_load_checks_admitted_git_not_current_source(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            study = project / "study"
            study.mkdir()
            evidence = project / "evidence.json"
            write_once(evidence, {"pass": True})
            hashes = {"source.py": "old"}
            gate_path = project / "gate.json"
            write_once(gate_path, {"pass": True, "implementation_hashes": hashes, "checks": {
                name: {"pass": True, "evidence": [{"path": str(evidence), "sha256": digest(evidence)}]}
                for name in ("unit", "source_scope", "preservation", "no_replay")}})
            value = {"study": str(study), "implementation_hashes": hashes,
                     "offline_gate_path": str(gate_path), "offline_gate_sha256": digest(gate_path)}
            path = project / prior.RESUMPTION
            write_once(path, value)
            write_once(study / "registration.json", {})
            with patch.object(prior, "PROJECT", project), patch.object(prior, "implementation_hashes", return_value={"source.py": "new"}), \
                 patch.object(prior, "verify_scope") as scope, patch.object(prior, "verify_preserved"), \
                 patch.object(dispatch, "load_resumption"), patch.object(prior, "require_prepared", return_value={"commit": "admitted-a003"}), \
                 patch("research.e008_live.git_bytes", return_value=b"current-head"), \
                 patch("research.e008_transition.verify_clock"), patch("research.e008_transition.verify_git_files") as verify:
                prior.load_resumption(study, path, {}, _historical=True)
                self.assertEqual(scope.call_args.args[-1], hashes)
                self.assertEqual(verify.call_args.args[0], "admitted-a003")
                self.assertFalse(verify.call_args.kwargs["working"])
                prior.load_resumption(study, path, {})
                self.assertEqual(scope.call_args.args[-1], {"source.py": "new"})
                self.assertEqual(verify.call_args.args[0], "current-head")
                self.assertTrue(verify.call_args.kwargs["working"])
