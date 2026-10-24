import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.common import digest
from research.e008_locks import write_once
from research.e008_live import resume_failure
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy
from research import e008_direct_resumption as h, e008_minute_resumption as prior, e008_resumption as dispatch


class DirectResumptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.study = Path(temporary.name)
        folder = self.study / "separate-diagnostic"
        folder.mkdir()
        self.log = folder / "provider.jsonl"
        self.events = [
            {"event": "request_started", "attempt": 1, "worker": "probe", "payload": {
                "model": "p", "input": [{"role": "user", "content": [{"type": "input_text", "text": "Reply exactly OK."}]}],
                "tools": [], "max_output_tokens": 256}},
            {"event": "transport_bytes", "worker": "probe", "method": "POST", "http_status": 200,
                "request_sent": True, "response_complete": True, "request_body_bytes": 100, "response_body_bytes": 30},
            {"event": "response", "attempt": 1, "worker": "probe", "seconds": 3, "response": {
                "model": "p", "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 1},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]}}]
        self.log.write_text("".join(json.dumps(event) + "\n" for event in self.events), encoding="utf-8")
        self.result = {"at": 100, "requested_model": "p", "returned_model": "p",
            "http_status": 200, "response_status": "completed", "output_text": "OK", "exception_type": None,
            "request_sent": True, "response_complete": True, "POST_attempts": 1, "GET_attempts": 0,
            "retry_attempts": 0, "provider_log_sha256": digest(self.log), "usage": {"input_tokens": 10, "output_tokens": 1}}
        self.path = folder / "result.json"
        write_once(self.path, self.result)
        self.value = {"amendment_id": h.IDENTITY, "models": {"primary": "p", "secondary": "s"},
                      "recovery_plan": copy.deepcopy(h.PLAN), "diagnostic_path": str(self.path),
                      "diagnostic_sha256": digest(self.path)}
        self.fixed_sha = patch.object(h, "DIAGNOSTIC_SHA", digest(self.path)).start()
        guard = SeriesLedger(self.study, resource_policy([{"id": "j1"}]))
        guard.start()
        self.provider = Mock(model="p", ledger=guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.admission = {"prepared_at": 200, "commit": "a005", "resumption_sha256": "new-sha"}
        patch.object(h, "require_prepared", return_value=self.admission).start()
        self.addCleanup(patch.stopall)

    def gate(self):
        return dispatch.recovery_gate(self.study, self.value, self.provider)

    def replace_result(self, changes):
        changed = {**self.result, **changes}
        self.path.write_text(json.dumps(changed), encoding="utf-8")
        self.value["diagnostic_sha256"] = digest(self.path)
        return patch.object(h, "DIAGNOSTIC_SHA", digest(self.path))

    def test_success_reuses_exact_existing_response_without_network(self):
        expected = self.gate()
        self.assertEqual(expected["new_network_requests"], 0)
        self.assertEqual(self.gate(), expected)
        self.assertEqual(dispatch.require_recovered(self.study, self.value), expected)
        self.provider.models.assert_not_called()
        self.provider.respond.assert_not_called()
        self.assertFalse((self.study / "recovery").exists())

    def test_different_diagnostic_or_trace_rejected(self):
        self.path.write_bytes(b"changed")
        with self.assertRaises(PermissionError):
            self.gate()
        self.path.write_text(json.dumps(self.result), encoding="utf-8")
        self.value["diagnostic_sha256"] = digest(self.path)
        with patch.object(h, "DIAGNOSTIC_SHA", digest(self.path)):
            self.log.write_bytes(b"changed")
            with self.assertRaises(PermissionError):
                self.gate()
        self.provider.models.assert_not_called()

    def test_wrong_status_model_or_multiple_requests_not_success(self):
        for key, value in (("http_status", 502), ("response_status", "incomplete"), ("returned_model", "s"),
                           ("requested_model", "s"), ("output_text", ""), ("exception_type", "TimeoutError"),
                           ("request_sent", False), ("response_complete", False), ("POST_attempts", 2),
                           ("GET_attempts", 1), ("retry_attempts", 1)):
            with self.subTest(field=key), self.replace_result({key: value}), self.assertRaises(PermissionError):
                h.verify_diagnostic(self.value)

    def test_semantic_trace_checks_even_with_resealed_fixture(self):
        changes = [
            lambda e: e.append(copy.deepcopy(e[1])),
            lambda e: e[0]["payload"].update(model="s"),
            lambda e: e[0]["payload"].update(tools=[{"name": "unexpected"}]),
            lambda e: e[0]["payload"].update(input=[]),
            lambda e: e[0]["payload"].update(max_output_tokens=8192),
            lambda e: e[1].update(method="GET"),
            lambda e: e[2]["response"].update(status="incomplete")]
        for change in changes:
            events = copy.deepcopy(self.events)
            change(events)
            self.log.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
            with self.replace_result({"provider_log_sha256": digest(self.log)}), self.assertRaises(PermissionError):
                h.verify_diagnostic(self.value)

    def test_existing_exhausted_catalogue_is_not_overwritten(self):
        path = self.study / "recovery/E008-A004/exhausted.json"
        write_once(path, {"attempts": 10, "http502_responses": 0, "catalogue_model_absent": 10})
        original = path.read_bytes()
        self.gate()
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((path.parent / "complete.json").exists())

    def test_diagnostic_must_precede_admission(self):
        self.admission["prepared_at"] = 99
        with self.assertRaises(PermissionError):
            self.gate()
        self.assertFalse((h.root(self.study) / "direct-gate.json").exists())

    def test_changed_gate_record_is_not_trusted(self):
        self.gate()
        path = h.root(self.study) / "direct-gate.json"
        path.write_text(json.dumps({"pass": True}), encoding="utf-8")
        with self.assertRaises(PermissionError):
            h.require_recovered(self.study, self.value)

    def test_stop_or_clock_guard_prevents_admission(self):
        (self.study / "STOP").touch()
        with self.assertRaises(SeriesStopped):
            self.gate()
        self.assertFalse((h.root(self.study) / "direct-gate.json").exists())

    def test_model_plan_clock_and_journal_cannot_change(self):
        for changes in ({"models": {"primary": "s"}}, {"recovery_plan": {}}):
            with self.assertRaises(PermissionError):
                h.recovery_gate(self.study, {**self.value, **changes}, self.provider)
        self.provider.log = self.study / "changed.jsonl"
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.log = self.study / "provider.jsonl"
        self.provider.ledger.study = self.study / "new-clock"
        with self.assertRaises(PermissionError):
            self.gate()

    def test_future_502_routes_through_original_bounded_policy(self):
        self.gate()
        job = {"id": h.NEXT, "model_role": "primary", "budget": None, "protocol_version": None}
        result = {"failure_origin": "provider", "failure_type": "RuntimeError",
                  "failure": "provider HTTP status 502; no retry or redirect"}
        event = {"event": "transport_bytes", "worker": h.NEXT, "method": "POST",
                 "http_status": 502, "request_sent": True, "response_complete": True}
        raw = (json.dumps(event) + "\n").encode()
        self.provider.log.write_bytes(raw)
        unit = self.study / "units" / h.NEXT
        write_once(unit / "outcome.json", {"job": {**job, "budget": 4096, "protocol_version": "L1-v2"},
                                         "result": result, "status": "failed"})
        write_once(unit / "provider-span.json", {"offset": 0, "length": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest(), "worker": h.NEXT})
        write_once(unit / "execution-binding.json", {"commit": "a005"})
        project = self.study / "project"
        write_once(project / "docs/research/E008-MODEL-AMENDMENT.json", {})
        with patch.object(prior, "PROJECT", project), patch.object(h, "execution_binding", return_value={"commit": "a005"}), \
             patch.object(h.minute, "recover", return_value={"pass": True, "attempts": 1}) as recovery:
            self.assertTrue(resume_failure(self.study, job, result, self.provider, resumption=self.value)["pass"])
            recovery.assert_called_once_with(self.study, h.NEXT, self.provider)
        self.provider.respond.assert_not_called()

    def test_future_408_still_stops(self):
        self.provider.log.write_text(json.dumps({"event": "transport_bytes", "worker": h.NEXT,
            "method": "POST", "http_status": 408}) + "\n", encoding="utf-8")
        with self.assertRaises(SeriesStopped):
            resume_failure(self.study, {"id": h.NEXT},
                           {"failure_origin": "provider", "failure_type": "RuntimeError"},
                           self.provider, resumption=self.value)

    def test_old_binding_unchanged_new_binding_uses_a005(self):
        old = {"commit": "old", "amendment_sha256": "a001"}
        with patch.object(h, "parent", return_value={}), patch.object(prior, "execution_binding", side_effect=lambda *args: old.copy()):
            self.assertEqual(h.execution_binding(self.study, {"id": h.FAILURE}, {}, self.value), old)
            after = h.execution_binding(self.study, {"id": h.NEXT}, {}, self.value)
        self.assertEqual(after["commit"], "a005")
        self.assertEqual(after["prior_resumption_sha256"], h.PRIOR_SHA)

    def test_exact_retained_failure_only(self):
        self.gate()
        path = self.study / "units" / h.FAILURE / "outcome.json"
        result = {"failure": "retained"}
        write_once(path, {"result": result})
        stop = self.study / "stop.json"
        write_once(stop, {"failed_outcome_sha256": digest(path)})
        value = {**self.value, "stop_path": str(stop)}
        self.assertTrue(h.reconciles(self.study, {"id": h.FAILURE}, result, value))
        with self.assertRaises(PermissionError):
            h.reconciles(self.study, {"id": h.FAILURE}, {}, value)

    def test_external_diagnostic_cost_remains_measurable_separately(self):
        from research.e008_measurements import api_measurements
        result, events = h.verify_diagnostic(self.value)
        measured = api_measurements(events)
        self.assertEqual(measured["workers"]["probe"]["input_tokens"]["observed"], 10)
        self.assertEqual(result["usage"]["output_tokens"], 1)
        self.assertEqual(self.provider.log.read_bytes(), b"")

    def test_audit_keeps_negative_catalogue_and_external_probe_distinct(self):
        self.admission["prepared_at"] = 1000
        self.gate()
        clock = [100.0]
        def wait(deadline, guard):
            clock[0] = deadline
        def missing():
            with self.provider.log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": "transport_bytes", "method": "GET", "worker": None,
                    "http_status": 200, "request_sent": True, "response_complete": True,
                    "request_body_bytes": 0, "response_body_bytes": 12}) + "\n")
            return []
        self.provider.models.side_effect = missing
        with patch("research.e008_minute_recovery.time.time", side_effect=lambda: clock[0]), \
             patch("research.e008_minute_recovery.wait_until", side_effect=wait), \
             patch.object(self.provider.ledger, "check_context", return_value=10000):
            with self.assertRaises(SeriesStopped):
                h.minute.recover(self.study, prior.IDENTITY, self.provider)
        write_once(self.study / "units" / h.NEXT / "outcome.json", {"result": {}, "status": "completed"})
        with patch.object(prior, "parent", return_value={}), patch.object(prior.prior, "audit_resumption", return_value={"pass": True}), \
             patch.object(prior, "audit_resumption", side_effect=AssertionError("exhausted A004 is not recovered")), \
             patch.object(h, "verify_preserved", return_value={"exhausted": {"attempts": 10}}):
            report = h.audit_resumption(self.study, self.value, {h.FAILURE: {"finished": 1}, h.NEXT: {"started": 1010}})
        self.assertEqual(report["overhead_already_in_main_ledger"]["metadata_requests"], 10)
        self.assertEqual(report["external_diagnostic_overhead"]["workers"]["probe"]["input_tokens"]["observed"], 10)
        self.assertEqual(report["direct_gate"]["new_network_requests"], 0)
        self.assertEqual(self.provider.models.call_count, 10)
        self.provider.respond.assert_not_called()


class DirectScopeTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"implementation_hashes": {"science.py": "fixed", "research/e008_live.py": "old"},
                         "models": {"primary": "p", "secondary": "s"}, "invariants": {"deadline": 123}}
        self.current = {**self.previous["implementation_hashes"], "research/e008_live.py": "new",
                        "research/e008_direct_resumption.py": "new"}
        self.registration = {"schedule": [{"id": f"j{n:05d}"} for n in range(1, 3427)]}
        self.value = {"amendment_id": h.IDENTITY, "status": "approved_for_execution", "preregistered": True,
            "human_authorization": h.AUTHORIZATION, "authorization_sha256": h.AUTHORIZATION_SHA,
            "authorization_scope": "preserve2139; firstj02140; reuse successful direct probe; same models; no repeats",
            "prior_resumption_sha256": h.PRIOR_SHA, "stop_sha256": h.STOP_SHA,
            "model_amendment_sha256": dispatch.MODEL_AMENDMENT_SHA, "cutover_after_ordinal": h.CUTOVER,
            "first_pending_id": h.NEXT, "models": self.previous["models"], "invariants": self.previous["invariants"],
            "recovery_plan": h.PLAN, "base_implementation_hashes": self.previous["implementation_hashes"],
            "implementation_hashes": self.current}
        patch.object(h, "parent", return_value=self.previous).start()
        self.old_scope = patch.object(prior, "verify_scope").start()
        self.addCleanup(patch.stopall)

    def test_narrow_overlay_verifies_historical_parent(self):
        dispatch.verify_scope(self.registration, {}, self.value, self.current)
        self.old_scope.assert_called_once_with(self.registration, {}, self.previous, self.previous["implementation_hashes"])

    def test_changed_boundaries_models_clock_and_authorization_rejected(self):
        for key, changed in (("human_authorization", ""), ("models", {}), ("invariants", {}),
                             ("cutover_after_ordinal", 2140), ("first_pending_id", h.FAILURE),
                             ("status", "draft"), ("recovery_plan", {}), ("authorization_sha256", "")):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, key: changed}, self.current)

    def test_science_or_unregistered_source_changes_rejected(self):
        for current in ({**self.current, "science.py": "changed"},
                        {k: v for k, v in self.current.items() if k != "science.py"},
                        {**self.current, "new.py": "unapproved"}):
            with self.assertRaises(PermissionError):
                h.verify_scope(self.registration, {}, {**self.value, "implementation_hashes": current}, current)

    def test_historical_a004_dispatch_is_explicit(self):
        with patch.object(prior, "load_resumption", return_value="historical") as load:
            self.assertEqual(dispatch.load_resumption("study", prior.PROJECT / prior.RESUMPTION, {}, _historical=True), "historical")
            load.assert_called_once_with("study", prior.PROJECT / prior.RESUMPTION, {}, _historical=True)
        with patch.object(h, "load_resumption", return_value="historical-a005") as load:
            self.assertEqual(dispatch.load_resumption("study", h.PROJECT / h.RESUMPTION, {}, _historical=True), "historical-a005")
            load.assert_called_once_with("study", h.PROJECT / h.RESUMPTION, {}, _historical=True)
        from research import e008_http408_followup, e008_deadline_resumption
        with patch.object(e008_http408_followup, "load_resumption", return_value="historical-a006") as load:
            self.assertEqual(dispatch.load_resumption("study", h.PROJECT / e008_http408_followup.RESUMPTION, {}, _historical=True), "historical-a006")
            load.assert_called_once_with("study", h.PROJECT / e008_http408_followup.RESUMPTION, {}, _historical=True)
        with patch.object(e008_deadline_resumption, "load_resumption", return_value="historical-a007") as load:
            self.assertEqual(dispatch.load_resumption("study", h.PROJECT / e008_deadline_resumption.RESUMPTION, {}, _historical=True), "historical-a007")
            load.assert_called_once_with("study", h.PROJECT / e008_deadline_resumption.RESUMPTION, {}, _historical=True)
        from research import e008_socket_resumption
        with self.assertRaises(PermissionError):
            dispatch.load_resumption("study", h.PROJECT / e008_socket_resumption.RESUMPTION, {}, _historical=True)
