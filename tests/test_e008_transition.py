from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from research.common import digest
from research.e008_live import save_network_result
from research.e008_locks import read, write_once
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy
from research.e008_transition import (AMENDMENT, TransitionLedger, compatibility, gate_policy,
    load_amendment, reconciles, root, verify_clock, verify_git_files, verify_plan, verify_source_scope,
    verify_original_controls, charge_overhead)


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.registration = {"resources": resource_policy([{"id": "one"}])}
        self.parent = SeriesLedger(self.study, self.registration["resources"])
        self.parent.start()
        root(self.study).mkdir(parents=True)
        self.guard = TransitionLedger(self.study, self.registration, self.parent)
        self.guard.start()
        self.original_log = self.study / "provider.jsonl"
        self.original_log.write_text("", encoding="utf-8")
        reused = self.study / "compatibility/secondary/result.json"
        save_network_result(reused, SimpleNamespace(log=self.original_log), 0,
                            {"model": "new-primary", "pass": True})
        self.amendment = {"proposed_models": {"primary": "new-primary", "secondary": "new-secondary"},
            "prospective_admission": {
                "maximum_additional_Responses_attempts": 1, "maximum_additional_catalogue_GETs": 1,
                "no_retry_or_new_smoke_after_failure": True, "original_series_ledger_policy_not_reset": True,
                "additional_setup_cost_charged_in_final_report": True,
                "aggregate_Response_ceiling": self.registration["resources"]["maximum_response_attempts"] + 1,
                "reuse_existing_same_model_compatibility": {
                    "path": str(reused), "sha256": digest(reused),
                    "evidence_sha256": digest(reused.with_suffix(".evidence.json")),
                    "model": "new-primary", "new_Response_for_this_model": False}}}
        self.provider = Mock(model="new-secondary", ledger=self.guard, log=root(self.study) / "provider.jsonl")
        self.provider.models.return_value = ["new-primary", "new-secondary"]
        self.provider.respond.return_value = {"output": [
            {"type": "function_call", "call_id": "id", "name": "echo", "arguments": '{"value":17}'}]}

    def gate(self):
        return compatibility(self.study, self.amendment, self.provider, self.original_log)

    def test_primary_reuse_one_get_and_one_secondary_smoke_on_resume(self):
        before = self.original_log.read_bytes()
        result = self.gate()
        self.assertTrue(result["pass"])
        self.assertEqual(self.gate(), result)
        self.assertEqual(self.provider.models.call_count, 1)
        self.assertEqual(self.provider.respond.call_count, 1)
        self.assertEqual(self.provider.respond.call_args.args[0], "smoke-secondary")
        self.assertEqual(self.original_log.read_bytes(), before)

    def test_absent_primary_stops_without_smoke_or_replacement(self):
        self.provider.models.return_value = ["new-secondary", "some-other-model"]
        self.assertEqual(self.gate()["action"], "stop")
        self.provider.respond.assert_not_called()
        self.gate()
        self.assertEqual(self.provider.models.call_count, 1)

    def test_absent_secondary_only_omits_its_controls(self):
        self.provider.models.return_value = ["new-primary"]
        result = self.gate()
        self.assertTrue(result["pass"])
        self.assertEqual(result["action"], "unavailable")
        self.provider.respond.assert_not_called()

    def test_bad_smoke_stops_and_is_never_retried(self):
        self.provider.respond.return_value["output"][0]["arguments"] = '{"value":99}'
        result = self.gate()
        self.assertFalse(result["pass"])
        self.assertEqual(self.gate(), result)
        self.assertEqual(self.provider.respond.call_count, 1)

    def test_metadata_502_cannot_skip_primary_availability(self):
        def fail():
            self.provider.log.write_text(json.dumps({"event": "transport_bytes", "worker": None,
                                                    "http_status": 502}) + "\n", encoding="utf-8")
            raise RuntimeError("transport")
        self.provider.models.side_effect = fail
        self.assertEqual(self.gate()["action"], "stop")
        self.provider.respond.assert_not_called()

    def test_secondary_429_is_retained_as_unavailable_not_retried(self):
        def fail(*args, **kwargs):
            self.provider.log.write_text(json.dumps({"event": "transport_bytes", "worker": "smoke-secondary",
                                                    "http_status": 429}) + "\n", encoding="utf-8")
            raise RuntimeError("transport")
        self.provider.respond.side_effect = fail
        result = self.gate()
        self.assertTrue(result["pass"])
        self.assertEqual(result["action"], "unavailable")
        self.assertEqual(self.gate(), result)
        self.assertEqual(self.provider.respond.call_count, 1)

    def test_orphan_never_replayed(self):
        write_once(root(self.study) / "compatibility/started.json", {"started": True})
        with self.assertRaises(SeriesStopped):
            self.gate()
        self.provider.models.assert_not_called()

    def test_reused_model_and_original_trace_must_match(self):
        self.amendment["proposed_models"]["primary"] = "different-primary"
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_result_tampering_rejected_without_new_network(self):
        self.gate()
        path = root(self.study) / "compatibility/result.json"
        value = read(path)
        path.write_text(json.dumps({**value, "pass": False}), encoding="utf-8")
        with self.assertRaises(PermissionError):
            self.gate()
        self.assertEqual(self.provider.models.call_count, 1)

    def test_original_stop_also_stops_additional_gate(self):
        (self.study / "STOP").touch()
        with self.assertRaisesRegex(SeriesStopped, "STOP"):
            self.guard.reserve_metadata()
        with self.assertRaisesRegex(SeriesStopped, "STOP"):
            self.guard.reserve("smoke-secondary")

    def test_original_deadline_not_reset_by_fresh_gate_clock(self):
        with closing(sqlite3.connect(self.parent.path)) as db:
            db.execute("UPDATE runtime_policy SET started=started-?", (self.parent.limits["series_seconds"],))
            db.commit()
        with self.assertRaisesRegex(SeriesStopped, "deadline"):
            self.guard.reserve_metadata()

    def test_original_pending_request_prevents_gate_request(self):
        self.parent.reserve("one")
        with self.assertRaisesRegex(SeriesStopped, "pending"):
            self.guard.reserve_metadata()

    def test_gate_has_one_request_per_type_and_never_claims_old_context(self):
        get = self.guard.reserve_metadata()
        self.guard.finish_metadata(get, "completed")
        with self.assertRaisesRegex(SeriesStopped, "ceiling"):
            self.guard.reserve_metadata()
        response = self.guard.reserve("smoke-secondary")
        self.guard.finish(response, "failed_or_unknown")
        with self.assertRaisesRegex(SeriesStopped, "ceiling"):
            self.guard.reserve("smoke-secondary")
        with self.assertRaisesRegex(SeriesStopped, "unregistered"):
            self.guard.reserve("one")
        with closing(sqlite3.connect(self.parent.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM metadata_attempts").fetchone()[0], 0)
            self.assertEqual(json.loads(db.execute("SELECT value FROM runtime_policy").fetchone()[0]),
                             self.registration["resources"])

    def test_clock_and_deadline_tampering_rejected(self):
        with closing(sqlite3.connect(self.parent.path)) as db:
            started = db.execute("SELECT started FROM runtime_policy").fetchone()[0]
        self.amendment["invariants"] = {"original_clock_started": started,
            "original_deadline": started + self.registration["resources"]["series_seconds"]}
        verify_clock(self.study, self.registration, self.amendment)
        self.amendment["invariants"]["original_deadline"] += 1
        with self.assertRaises(PermissionError):
            verify_clock(self.study, self.registration, self.amendment)

    def test_gate_limit_extension_and_primary_replay_rejected(self):
        verify_plan(self.registration, self.amendment)
        for key in ("maximum_additional_Responses_attempts", "maximum_additional_catalogue_GETs"):
            changed = copy.deepcopy(self.amendment)
            changed["prospective_admission"][key] += 1
            with self.assertRaises(PermissionError):
                verify_plan(self.registration, changed)
        self.amendment["prospective_admission"]["reuse_existing_same_model_compatibility"]["new_Response_for_this_model"] = True
        with self.assertRaises(PermissionError):
            verify_plan(self.registration, self.amendment)

    def test_scientific_source_and_deleted_source_rejected(self):
        original = {"research/e008_live.py": "old", "research/e008_scm.py": "fixed"}
        current = {**original, "research/e008_live.py": "new"}
        reg = {"implementation_hashes": original}
        amendment = {"base_implementation_hashes": original, "implementation_hashes": current}
        verify_source_scope(reg, amendment, current)
        changed = {**current, "research/e008_scm.py": "changed"}
        amendment["implementation_hashes"] = changed
        with self.assertRaises(PermissionError):
            verify_source_scope(reg, amendment, changed)
        current.pop("research/e008_live.py")
        amendment["implementation_hashes"] = current
        with self.assertRaises(PermissionError):
            verify_source_scope(reg, amendment, current)

    def test_exact_failed_bytes_only_are_reconciled(self):
        result = {"failure_origin": "provider", "failure": "provider HTTP status 502; no retry or redirect"}
        path = self.study / "units/stopped/outcome.json"
        write_once(path, {"result": result})
        amendment = {"reconciled_failure": {"id": "stopped", "sha256": digest(path)}}
        with patch("research.e008_transition.require_prepared"):
            self.assertTrue(reconciles(self.study, {"id": "stopped"}, result, amendment))
            self.assertFalse(reconciles(self.study, {"id": "future"}, result, amendment))
            with self.assertRaises(PermissionError):
                reconciles(self.study, {"id": "stopped"}, {**result, "failure_origin": "controller"}, amendment)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(PermissionError):
                reconciles(self.study, {"id": "stopped"}, result, amendment)

    def test_draft_rejected_before_git_or_network(self):
        project = self.study / "project"
        path = project / AMENDMENT
        write_once(path, {"status": "draft", "preregistered": False})
        write_once(self.study / "registration.json", {})
        with patch("research.e008_transition.PROJECT", project), self.assertRaisesRegex(PermissionError, "draft"):
            load_amendment(self.study, path)

    def test_original_recovery_and_journal_prefix_immutable_but_append_allowed(self):
        import hashlib
        for name in ("manifest.json", "live-gate.json", "network-start.json", "recovery/stopped/3-result.json"):
            write_once(self.study / name, {"fixed": True})
        self.amendment["reconciled_failure"] = {"id": "stopped"}
        names = {"manifest.json", "live-gate.json", "network-start.json", "recovery/stopped/3-result.json"}
        names.update(p.relative_to(self.study).as_posix() for p in (self.study / "compatibility").rglob("*") if p.is_file())
        self.amendment["preserved_control_hashes"] = {name: digest(self.study / name) for name in names}
        original = b'{"fixed":"journal"}\n'
        self.original_log.write_bytes(original + b'{"prospective":"journal"}\n')
        self.amendment["original_provider_prefix"] = {"bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
        verify_original_controls(self.study, self.amendment)
        self.original_log.write_bytes(original.replace(b"fixed", b"other"))
        with self.assertRaises(PermissionError):
            verify_original_controls(self.study, self.amendment)
        self.original_log.write_bytes(original)
        (self.study / "recovery/stopped/3-result.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(PermissionError):
            verify_original_controls(self.study, self.amendment)

    def test_overhead_is_charged_once_and_unknown_usage_stays_unknown(self):
        from research.e008_measurements import measure
        keys = ("api_body_bytes", "api_seconds", "input_tokens", "output_tokens",
                "cached_input_tokens", "reasoning_output_tokens")
        worker = {key: measure(10) for key in keys}
        worker["failed_or_unknown"] = 0
        extra_worker = {key: measure(unknown=1) for key in keys}
        extra_worker["failed_or_unknown"] = 1
        resources = {"network": {"workers": {"old": worker}, "attempts": 2, "metadata_requests": 3,
                                 "metadata_api_body_bytes": measure(100)}, "experiment_overhead": {}}
        transition = {"operational_overhead": {"workers": {"smoke-secondary": extra_worker}, "attempts": 1,
                      "metadata_requests": 1, "metadata_api_body_bytes": measure(5)}}
        before = copy.deepcopy(resources["network"])
        charge_overhead(resources, transition)
        charge_overhead(resources, transition)
        total = resources["network_including_transition"]
        self.assertEqual(total["response_attempts"], 3)
        self.assertEqual(total["metadata_requests"], 4)
        self.assertEqual(total["input_tokens"], measure(10, 1))
        self.assertEqual(total["metadata_api_body_bytes"], measure(105))
        self.assertEqual(resources["network"], before)

    def test_historical_git_blob_can_differ_from_worktree_but_new_binding_cannot(self):
        repo = self.study / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout
        git("init")
        source = repo / "source.py"
        source.write_text("value = 1\n", encoding="utf-8", newline="\n")
        old = digest(source)
        git("add", "source.py")
        git("-c", "user.name=E008 fixture", "-c", "user.email=fixture@invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", "Synthetic original")
        commit = git("rev-parse", "HEAD").decode().strip()
        source.write_text("value = 2\n", encoding="utf-8", newline="\n")
        with patch("research.e008_transition.PROJECT", repo):
            verify_git_files(commit, {"source.py": old})
            with self.assertRaises(PermissionError):
                verify_git_files(commit, {"source.py": old}, working=True)
            with self.assertRaises(PermissionError):
                verify_git_files(commit, {"source.py": digest(source)}, working=True)


if __name__ == "__main__":
    unittest.main()
