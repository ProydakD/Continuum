import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from research.common import digest
from research.e008_locks import read, write_once
from research.e008_live import resume_failure
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy
from research import e008_deadline_resumption as h, e008_resumption as dispatch


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"implementation_hashes": {"science.py": "fixed", "research/e008_resources.py": "old"},
                         "models": {"primary": "p", "secondary": "s"}, "invariants": {"original_deadline": 123}}
        self.current = {**self.previous["implementation_hashes"], "research/e008_resources.py": "new",
                        "research/e008_deadline_resumption.py": "new"}
        self.registration = {"schedule": [{"id": f"j{n:05d}"} for n in range(1, 3427)]}
        self.value = {"amendment_id": h.IDENTITY, "status": "approved_for_execution", "preregistered": True,
            "human_authorization": h.AUTHORIZATION, "authorization_sha256": h.AUTHORIZATION_SHA,
            "prior_resumption_sha256": h.PRIOR_SHA, "stop_sha256": h.STOP_SHA,
            "model_amendment_sha256": dispatch.MODEL_AMENDMENT_SHA, "cutover_after_ordinal": h.CUTOVER,
            "first_pending_id": h.NEXT, "models": self.previous["models"], "invariants": self.previous["invariants"],
            "clock_extension": copy.deepcopy(h.CLOCK), "recovery_plan": copy.deepcopy(h.PLAN),
            "base_implementation_hashes": self.previous["implementation_hashes"], "implementation_hashes": self.current}
        patch.object(h, "parent", return_value=self.previous).start()
        self.prior_scope = patch.object(h.prior, "verify_scope").start()
        self.addCleanup(patch.stopall)

    def test_exact_extension_dispatch_checks_immutable_parent(self):
        dispatch.verify_scope(self.registration, {}, self.value, self.current)
        self.prior_scope.assert_called_once_with(self.registration, {}, self.previous, self.previous["implementation_hashes"])

    def test_changed_authorization_boundary_models_or_other_limits_denied(self):
        for key, bad in (("human_authorization", ""), ("authorization_sha256", ""), ("models", {}),
                         ("invariants", {}), ("cutover_after_ordinal", 2857), ("first_pending_id", "j02858"),
                         ("prior_resumption_sha256", "bad"), ("stop_sha256", "bad"), ("recovery_plan", {}),
                         ("status", "draft"), ("preregistered", False)):
            with self.subTest(field=key), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, key: bad}, self.current)

    def test_no_clock_reset_unbounded_extension_or_second_extension(self):
        for key in h.CLOCK:
            clock = {**h.CLOCK, key: h.CLOCK[key] + 1}
            with self.subTest(field=key), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "clock_extension": clock}, self.current)

    def test_scientific_change_new_unregistered_file_and_deletion_denied(self):
        for changed in ({**self.current, "science.py": "changed"}, {**self.current, "other.py": "new"},
                        {k: v for k, v in self.current.items() if k != "science.py"}):
            with self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "implementation_hashes": changed}, changed)


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.policy = resource_policy([{"id": h.NEXT}])
        self.value = {"amendment_id": h.IDENTITY, "clock_extension": h.CLOCK}
        with patch("research.e008_resources.time.time", return_value=h.CLOCK["original_started"]):
            self.original = SeriesLedger(self.study, self.policy)
            self.original.start()

    def extended(self):
        with patch.object(h, "require_prepared"):
            return SeriesLedger(self.study, self.policy, deadline_extension=self.value)

    def test_original_expired_extended_alive_same_start_and_policy(self):
        with patch("research.e008_resources.time.time", return_value=h.CLOCK["original_deadline"] + 10):
            with self.assertRaisesRegex(SeriesStopped, "registered series deadline"):
                self.original.remaining()
            guard = self.extended()
            self.assertAlmostEqual(guard.remaining(), 259190, delta=1)
        with closing(sqlite3.connect(self.original.path)) as db:
            encoded, started = db.execute("SELECT value,started FROM runtime_policy").fetchone()
        self.assertEqual(json.loads(encoded), self.policy)
        self.assertEqual(started, h.CLOCK["original_started"])
        self.assertEqual(guard.limits, self.original.limits)

    def test_extended_deadline_still_stops(self):
        with patch("research.e008_resources.time.time", return_value=h.CLOCK["extended_deadline"] + 1):
            guard = self.extended()
            with self.assertRaisesRegex(SeriesStopped, "registered series deadline"):
                guard.remaining()

    def test_stop_file_still_stops(self):
        guard = self.extended()
        (self.study / "STOP").touch()
        with self.assertRaisesRegex(SeriesStopped, "operator STOP"):
            guard.check_context()

    def test_missing_or_wrong_admission_denied(self):
        with self.assertRaises(FileNotFoundError):
            SeriesLedger(self.study, self.policy, deadline_extension=self.value)
        with patch.object(h, "require_prepared"):
            with self.assertRaises(PermissionError):
                SeriesLedger(self.study, self.policy, deadline_extension={**self.value, "clock_extension": {}})

    def test_changed_original_start_denied(self):
        with closing(sqlite3.connect(self.original.path)) as db:
            db.execute("UPDATE runtime_policy SET started=started+1")
            db.commit()
        with self.assertRaises(PermissionError):
            self.extended()

    def test_pending_network_and_request_ceiling_still_stop(self):
        guard = self.extended()
        for _ in range(self.policy["workers"][h.NEXT]):
            attempt = guard.reserve(h.NEXT)
            with self.assertRaisesRegex(SeriesStopped, "pending or orphan"):
                guard.check_context()
            guard.finish(attempt, "failed_or_unknown")
        with self.assertRaisesRegex(SeriesStopped, "attempt ceiling"):
            guard.reserve(h.NEXT)

    def test_backward_clock_still_stops(self):
        guard = self.extended()
        guard.remaining()
        with patch("research.e008_resources.time.time", return_value=h.CLOCK["original_started"] - 1):
            with self.assertRaisesRegex(SeriesStopped, "backwards"):
                guard.remaining()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        guard = SimpleNamespace(study=self.study, deadline_extension_seconds=259200, check_context=Mock(return_value=1000))
        self.provider = Mock(model="p", ledger=guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.provider.models.side_effect = self.available
        self.value = {"amendment_id": h.IDENTITY, "models": {"primary": "p", "secondary": "s"},
                      "recovery_plan": h.PLAN}
        self.admitted = patch.object(h, "require_prepared", return_value={
            "prepared_at": 20, "commit": "a007", "resumption_sha256": "new-sha"}).start()
        self.wait = patch("research.e008_live.wait_until").start()
        self.addCleanup(patch.stopall)
        self.folder = self.study / "recovery" / h.FAILURE
        write_once(self.folder / "1-started.json", {"at": 5, "delay": 30, "model": "p"})

    def available(self):
        with self.provider.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "transport_bytes", "method": "GET", "worker": None,
                "http_status": 200, "request_sent": True, "response_complete": True,
                "request_body_bytes": 0, "response_body_bytes": 10}) + "\n")
        return ["p"]

    def gate(self):
        return dispatch.recovery_gate(self.study, self.value, self.provider)

    def test_pending_slot_reused_cached_no_responses_and_start_unchanged(self):
        before = digest(self.folder / "1-started.json")
        self.assertEqual(self.gate(), {"pass": True, "attempts": 1, "model": "p"})
        self.assertEqual(dispatch.require_recovered(self.study, self.value), self.gate())
        self.provider.models.assert_called_once()
        self.provider.respond.assert_not_called()
        self.wait.assert_called_once_with(35, self.provider.ledger)
        self.assertEqual(digest(self.folder / "1-started.json"), before)

    def test_wrong_model_plan_or_unextended_guard_denied(self):
        for value in ({**self.value, "models": {"primary": "other"}}, {**self.value, "recovery_plan": {}}):
            with self.assertRaises(PermissionError):
                h.recovery_gate(self.study, value, self.provider)
        self.provider.ledger.deadline_extension_seconds = 0
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_started_but_sent_orphan_never_replayed(self):
        write_once(self.folder / "1-sending.json", {"at": 35})
        with self.assertRaisesRegex(SeriesStopped, "orphan"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_missing_model_three_slots_no_extra_request(self):
        self.provider.models.side_effect = lambda: (self.available(), [])[1]
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "exhausted"):
                self.gate()
        self.assertEqual(self.provider.models.call_count, 3)

    def test_future408_still_fatal(self):
        with patch("research.e008_live.last_http_status", return_value=408):
            with self.assertRaisesRegex(SeriesStopped, "non-transient"):
                resume_failure(self.study, {"id": h.NEXT}, {"failure_origin": "provider", "failure_type": "RuntimeError"},
                               self.provider, resumption=self.value)
        self.provider.models.assert_not_called()

    def test_historical502_delegates_parent_but_future_uses_new_binding(self):
        result = {"failure_origin": "provider", "failure_type": "RuntimeError"}
        with patch.object(h, "require_recovered"), patch.object(h, "parent", return_value={"prior": True}), \
             patch.object(h.prior, "recover_failure", return_value="cached") as old, \
             patch("research.e008_live.last_http_status", return_value=502):
            job = {"id": "j02781", "model_role": "primary"}
            self.assertEqual(resume_failure(self.study, job, result, self.provider, resumption=self.value), "cached")
            old.assert_called_once_with(self.study, job, result, self.provider, {"prior": True})
        with patch.object(h, "require_recovered"), patch.object(h.minute, "verify_future_failure") as verify, \
             patch.object(h.minute.minute, "recover", return_value="next"):
            job = {"id": h.NEXT, "model_role": "primary"}
            self.assertEqual(h.recover_failure(self.study, job, result, self.provider, self.value), "next")
            verify.assert_called_once_with(self.study, job, result, self.value)

    def test_bindings_retain_old_and_attribute_new_commit(self):
        previous = {"commit": "old", "resumption_sha256": "old-sha", "model": "p"}
        with patch.object(h, "parent", return_value={}), patch.object(h.prior, "execution_binding", side_effect=lambda *a: previous.copy()):
            self.assertEqual(dispatch.execution_binding(self.study, {"id": h.FAILURE}, {}, self.value), previous)
            value = dispatch.execution_binding(self.study, {"id": h.NEXT}, {}, self.value)
            self.assertEqual(value["commit"], "a007")
            self.assertEqual(value["prior_resumption_sha256"], h.PRIOR_SHA)

    def test_exact_retained_failure_only(self):
        result = {"failure": "retained"}
        path = self.study / "units" / h.FAILURE / "outcome.json"
        write_once(path, {"result": result})
        stop = self.study / "stop.json"
        write_once(stop, {"failed_outcome_sha256": digest(path)})
        with patch.object(h, "require_recovered"), patch.object(h, "parent", return_value={}), \
             patch.object(h.prior, "reconciles", return_value=False) as old:
            value = {**self.value, "stop_path": str(stop)}
            self.assertTrue(dispatch.reconciles(self.study, {"id": h.FAILURE}, result, value))
            with self.assertRaises(PermissionError):
                h.reconciles(self.study, {"id": h.FAILURE}, {}, value)
            self.assertFalse(h.reconciles(self.study, {"id": h.NEXT}, result, value))
            old.assert_called_once()

    def test_final_gate_audit_preserves_pending_start_and_counts_get_once(self):
        with patch("research.e008_live.time.time", return_value=40):
            self.gate()
        timeline = {h.FAILURE: {"finished": 10}, h.NEXT: {"started": 50, "finished": 51}}
        write_once(self.study / "units" / h.NEXT / "outcome.json", {"result": {}, "status": "completed"})
        with patch.object(h, "parent", return_value={}), patch.object(h.prior, "audit_resumption", return_value={"pass": True}), \
             patch.object(h, "verify_preserved"), patch.object(h, "audit_clock", return_value={"pass": True}):
            report = h.audit_resumption(self.study, self.value, timeline)
            self.assertEqual(report["overhead_already_in_main_ledger"]["metadata_requests"], 1)
            self.assertTrue(report["prior_operational_resumption"]["pass"])
            timeline[h.NEXT]["started"] = 39
            with self.assertRaises(PermissionError):
                h.audit_resumption(self.study, self.value, timeline)


class AdmissionAndAuditTests(unittest.TestCase):
    def test_cached_transition_gate_does_not_restart_expired_overhead_clock(self):
        from research import e008_transition as transition
        parent = Mock(deadline_extension_seconds=259200)
        guard = Mock()
        with patch.object(transition, "prepare_admission"), patch.object(transition, "TransitionLedger", return_value=guard), \
             patch.object(transition, "BoundedProvider"), patch.object(transition, "compatibility", return_value={"pass": True}):
            result = transition.check_gate("study", {"provider": {}}, {"proposed_models": {"secondary": "s"}}, parent)
            self.assertTrue(result["pass"])
            parent.check_context.assert_called_once()
            guard.start.assert_not_called()
            parent.deadline_extension_seconds = 0
            transition.check_gate("study", {"provider": {}}, {"proposed_models": {"secondary": "s"}}, parent)
            guard.start.assert_called_once()

    def test_prospective_admission_preserves_original_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            study = Path(folder)
            auth = study / "authorization.json"
            write_once(auth, {"at": 1})
            value = {"authorization_path": str(auth)}
            rows = [{"status": "completed", "started": 1}] * h.CUTOVER + [
                {"status": "pending", "started": None}] * (3426 - h.CUTOVER)
            with patch.object(h.base, "ledger_rows", return_value=rows), patch.object(h, "verify_preserved"), \
                 patch("research.e008_live.git_bytes", return_value=b"new-commit"), patch.object(h, "digest", return_value="new-sha"):
                admitted = h.prepare_admission(study, value)
                self.assertEqual(admitted["clock_extension"], h.CLOCK)
                self.assertEqual(admitted["new_network_requests_before_gate"], 0)
                with patch.object(h, "require_prepared", return_value=admitted):
                    self.assertEqual(h.prepare_admission(study, value), admitted)

    def test_prospective_context_blocks_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            study = Path(folder)
            (study / "units" / h.NEXT).mkdir(parents=True)
            rows = [{"status": "completed", "started": 1}] * h.CUTOVER + [
                {"status": "pending", "started": None}] * (3426 - h.CUTOVER)
            with patch.object(h.base, "ledger_rows", return_value=rows):
                with self.assertRaises(SeriesStopped):
                    h.prepare_admission(study, {})
                self.assertFalse(h.root(study).exists())

    def test_clock_audit_preserves_last_overrun_not_relabels_it(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [{"started": 1, "finished": 2}] * (h.CUTOVER - 1) + [{
                "started": h.CLOCK["original_deadline"] - 75, "finished": h.CLOCK["original_deadline"] + .34}]
            ledger = Path(folder) / "rows.json"
            write_once(ledger, rows)
            value = {"preserved_ledger_path": str(ledger)}
            at = h.CLOCK["original_deadline"] + 600
            timeline = {h.FAILURE: rows[-1].copy(), h.NEXT: {"started": at + 1, "finished": at + 2}}
            with patch.object(h, "require_prepared", return_value={"prepared_at": at}):
                report = h.audit_clock(folder, value, timeline)
                self.assertAlmostEqual(report["retained_last_completion_overrun_seconds"], .34, places=5)
                timeline[h.NEXT]["finished"] = h.CLOCK["extended_deadline"] + 1
                with self.assertRaises(PermissionError):
                    h.audit_clock(folder, value, timeline)
                timeline = {h.FAILURE: {**rows[-1], "finished": rows[-1]["finished"] - 1}}
                with self.assertRaises(PermissionError):
                    h.audit_clock(folder, value, timeline)

    def test_parent_audit_does_not_adopt_new_contexts(self):
        timeline = {h.FAILURE: {"finished": 10}, h.NEXT: {"started": 30}}
        with patch.object(h, "parent", return_value={"prior": True}), \
             patch.object(h.prior, "audit_resumption", side_effect=RuntimeError("parent-boundary")) as old:
            with self.assertRaisesRegex(RuntimeError, "parent-boundary"):
                h.audit_resumption("study", {}, timeline)
        old.assert_called_once_with("study", {"prior": True}, {h.FAILURE: {"finished": 10}})

    def test_historical_a006_load_uses_admitted_git_not_new_source(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            study = project / "study"
            study.mkdir()
            evidence = project / "evidence.json"
            write_once(evidence, {"pass": True})
            hashes = {"source.py": "old"}
            gate = project / "gate.json"
            write_once(gate, {"pass": True, "implementation_hashes": hashes, "checks": {
                name: {"pass": True, "evidence": [{"path": str(evidence), "sha256": digest(evidence)}]}
                for name in ("unit", "source_scope", "preservation", "no_replay")}})
            value = {"study": str(study), "implementation_hashes": hashes,
                     "offline_gate_path": str(gate), "offline_gate_sha256": digest(gate)}
            path = project / h.prior.RESUMPTION
            write_once(path, value)
            original = project / h.prior.BASE_RESUMPTION
            write_once(original, {"implementation_hashes": {}})
            sha = digest(original)
            write_once(h.prior.root(study) / "admission.json", {"commit": "original", "resumption_sha256": sha})
            write_once(study / "registration.json", {})
            with patch.object(h.prior, "PROJECT", project), patch.object(h.prior, "BASE_RESUMPTION_SHA", sha), \
                 patch.object(h.prior, "implementation_hashes", return_value={"source.py": "new"}), \
                 patch.object(h.prior, "verify_revision"), patch.object(h.prior, "verify_scope") as scope, \
                 patch.object(h.prior, "verify_preserved"), patch.object(h.prior.prior, "load_resumption"), \
                 patch.object(h.prior, "require_prepared", return_value={"commit": "admitted-a006"}), \
                 patch("research.e008_live.git_bytes", return_value=b"current"), \
                 patch("research.e008_transition.verify_clock"), patch("research.e008_transition.verify_git_files") as verify:
                h.prior.load_resumption(study, path, {}, _historical=True)
                self.assertEqual(scope.call_args.args[-1], hashes)
                self.assertEqual(verify.call_args.args[0], "admitted-a006")
                bound = [call for call in verify.call_args_list if "working" in call.kwargs]
                self.assertEqual(len(bound), 1)
                self.assertFalse(bound[0].kwargs["working"])
