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
from research.e008_resources import SeriesStopped
from research import e008_socket_resumption as h, e008_resumption as dispatch


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"implementation_hashes": {"science.py": "fixed", "research/e008_live.py": "old"},
                         "models": {"primary": "p", "secondary": "s"}, "invariants": {"deadline": 123}}
        self.current = {**self.previous["implementation_hashes"], "research/e008_live.py": "new",
                        "research/e008_socket_resumption.py": "new"}
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

    def test_dispatch_validates_immutable_parent(self):
        dispatch.verify_scope(self.registration, {}, self.value, self.current)
        self.prior_scope.assert_called_once_with(self.registration, {}, self.previous, self.previous["implementation_hashes"])

    def test_authorization_boundary_model_clock_and_policy_cannot_change(self):
        for key, bad in (("human_authorization", ""), ("authorization_sha256", ""), ("models", {}),
                         ("invariants", {}), ("cutover_after_ordinal", 3370), ("first_pending_id", "j03371"),
                         ("prior_resumption_sha256", "bad"), ("stop_sha256", "bad"), ("recovery_plan", {}),
                         ("status", "draft"), ("preregistered", False)):
            with self.subTest(field=key), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, key: bad}, self.current)
        for field in h.CLOCK:
            clock = {**h.CLOCK, field: h.CLOCK[field] + 1}
            with self.subTest(clock=field), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "clock_extension": clock}, self.current)

    def test_science_new_unregistered_file_and_deletion_denied(self):
        for changed in ({**self.current, "science.py": "changed"}, {**self.current, "other.py": "new"},
                        {k: v for k, v in self.current.items() if k != "science.py"}):
            with self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "implementation_hashes": changed}, changed)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.transport = {"event": "transport_bytes", "worker": h.FAILURE, "method": "POST",
                          "request_sent": False, "http_status": None, "response_complete": False,
                          "response_body_bytes": 0}

    def record(self, transport):
        raw = (json.dumps(transport) + "\n").encode()
        (self.study / "provider.jsonl").write_bytes(raw)
        p = self.study / "units" / h.FAILURE / "provider-span.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"worker": h.FAILURE, "offset": 0, "length": len(raw),
                               "sha256": hashlib.sha256(raw).hexdigest()}))

    def test_unsent_transport_accepted(self):
        self.record(self.transport)
        self.assertEqual(h.verify_failed_transport(self.study), self.transport)

    def test_sent_http_wrong_worker_method_or_response_denied(self):
        for key, bad in (("request_sent", True), ("http_status", 408), ("worker", h.NEXT),
                         ("method", "GET"), ("response_complete", True), ("response_body_bytes", 1)):
            self.record({**self.transport, key: bad})
            with self.subTest(field=key), self.assertRaises(PermissionError):
                h.verify_failed_transport(self.study)

    def test_trace_tampering_denied(self):
        self.record(self.transport)
        p = self.study / "provider.jsonl"
        p.write_bytes(p.read_bytes().replace(b"POST", b"GET "))
        with self.assertRaises(PermissionError):
            h.verify_failed_transport(self.study)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        guard = SimpleNamespace(study=self.study, deadline_extension_seconds=259200, check_context=Mock())
        self.provider = Mock(model="p", ledger=guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.provider.models.side_effect = self.available
        self.value = {"amendment_id": h.IDENTITY, "models": {"primary": "p", "secondary": "s"},
                      "recovery_plan": h.PLAN}
        patch.object(h, "require_prepared", return_value={"prepared_at": 20, "commit": "a008",
                                                       "resumption_sha256": "new-sha"}).start()
        patch("research.e008_live.wait_until").start()
        self.addCleanup(patch.stopall)
        self.folder = self.study / "recovery" / h.FAILURE

    def available(self):
        with self.provider.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "transport_bytes", "method": "GET", "worker": None,
                "http_status": 200, "request_sent": True, "response_complete": True,
                "request_body_bytes": 0, "response_body_bytes": 10}) + "\n")
        return ["p"]

    def gate(self):
        return dispatch.recovery_gate(self.study, self.value, self.provider)

    def test_one_get_cached_and_never_responses(self):
        expected = {"pass": True, "attempts": 1, "model": "p"}
        self.assertEqual(self.gate(), expected)
        self.assertEqual(dispatch.require_recovered(self.study, self.value), expected)
        self.assertEqual(self.gate(), expected)
        self.provider.models.assert_called_once()
        self.provider.respond.assert_not_called()

    def test_missing_model_exhausts_three_slots_without_replay(self):
        self.provider.models.side_effect = lambda: (self.available(), [])[1]
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "exhausted"):
                self.gate()
        self.assertEqual(self.provider.models.call_count, 3)

    def test_orphan_sent_gate_never_replayed(self):
        write_once(self.folder / "1-started.json", {"at": 5, "delay": 30, "model": "p"})
        write_once(self.folder / "1-sending.json", {"at": 35})
        with self.assertRaisesRegex(SeriesStopped, "orphan"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_changed_model_plan_or_extension_denied(self):
        for value in ({**self.value, "models": {"primary": "other"}}, {**self.value, "recovery_plan": {}}):
            with self.assertRaises(PermissionError):
                h.recovery_gate(self.study, value, self.provider)
        self.provider.ledger.deadline_extension_seconds = 0
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_future_socket_and_http408_remain_fatal(self):
        for failure, status in (("OSError", None), ("RuntimeError", 408)):
            with patch("research.e008_live.last_http_status", return_value=status):
                with self.assertRaisesRegex(SeriesStopped, "non-transient"):
                    resume_failure(self.study, {"id": h.NEXT}, {"failure_origin": "provider", "failure_type": failure},
                                   self.provider, resumption=self.value)
        self.provider.models.assert_not_called()

    def test_historical502_delegates_parent_future502_uses_new_binding(self):
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

    def test_exact_retained_failure_and_old_bindings_preserved(self):
        result = {"failure": "retained"}
        path = self.study / "units" / h.FAILURE / "outcome.json"
        write_once(path, {"result": result})
        stop = self.study / "stop.json"
        write_once(stop, {"failed_outcome_sha256": digest(path)})
        with patch.object(h, "require_recovered"), patch.object(h, "parent", return_value={}), \
             patch.object(h.prior, "reconciles", return_value=False):
            value = {**self.value, "stop_path": str(stop)}
            self.assertTrue(dispatch.reconciles(self.study, {"id": h.FAILURE}, result, value))
            with self.assertRaises(PermissionError):
                h.reconciles(self.study, {"id": h.FAILURE}, {}, value)
            self.assertFalse(h.reconciles(self.study, {"id": h.NEXT}, result, value))
        previous = {"commit": "old", "resumption_sha256": "old-sha", "model": "p"}
        with patch.object(h, "parent", return_value={}), patch.object(h.prior, "execution_binding", side_effect=lambda *a: previous.copy()):
            self.assertEqual(dispatch.execution_binding(self.study, {"id": h.FAILURE}, {}, self.value), previous)
            self.assertEqual(dispatch.execution_binding(self.study, {"id": h.NEXT}, {}, self.value)["commit"], "a008")

    def test_audit_counts_gate_once_and_checks_chronology(self):
        write_once(self.folder / "1-started.json", {"at": 5, "delay": 30, "model": "p"})
        with patch("research.e008_live.time.time", return_value=40):
            self.gate()
        timeline = {h.FAILURE: {"finished": 10}, h.NEXT: {"started": 50, "finished": 51}}
        write_once(self.study / "units" / h.NEXT / "outcome.json", {"result": {}, "status": "completed"})
        with patch.object(h, "parent", return_value={}), patch.object(h.prior, "audit_resumption", return_value={"pass": True}), \
             patch.object(h, "verify_preserved"), patch.object(h, "audit_clock", return_value={"pass": True}):
            report = h.audit_resumption(self.study, self.value, timeline)
            self.assertEqual(report["overhead_already_in_main_ledger"]["metadata_requests"], 1)
            timeline[h.NEXT]["started"] = 39
            with self.assertRaises(PermissionError):
                h.audit_resumption(self.study, self.value, timeline)


class AdmissionTests(unittest.TestCase):
    def test_no_new_extension_and_clock_audit_uses_original_a007(self):
        with patch.object(h, "parent", return_value={"original": True}), patch.object(h, "require_prepared"), \
             patch.object(h.prior, "audit_clock", return_value={"pass": True}) as audit:
            self.assertEqual(h.audit_clock("study", {}, {"timeline": True}), {"pass": True})
            audit.assert_called_once_with("study", {"original": True}, {"timeline": True})
        self.assertEqual(h.CLOCK, h.prior.CLOCK)

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

    def test_historical_a007_load_checks_admitted_not_current_source(self):
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
            write_once(study / "registration.json", {})
            with patch.object(h.prior, "PROJECT", project), \
                 patch.object(h.prior, "implementation_hashes", return_value={"source.py": "new"}), \
                 patch.object(h.prior, "verify_scope") as scope, patch.object(h.prior, "verify_preserved"), \
                 patch.object(h.prior.prior, "load_resumption"), \
                 patch.object(h.prior, "require_prepared", return_value={"commit": "admitted-a007"}), \
                 patch("research.e008_live.git_bytes", return_value=b"current"), \
                 patch("research.e008_transition.verify_clock"), patch("research.e008_transition.verify_git_files") as verify:
                h.prior.load_resumption(study, path, {}, _historical=True)
                self.assertEqual(scope.call_args.args[-1], hashes)
                bound = [c for c in verify.call_args_list if "working" in c.kwargs]
                self.assertEqual(len(bound), 1)
                self.assertEqual(bound[0].args[0], "admitted-a007")
                self.assertFalse(bound[0].kwargs["working"])
