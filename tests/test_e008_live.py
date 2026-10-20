from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.e008_live import (REGISTRATION, commit_binding, compatibility, controller_lock,
                                recover, resume_failure, run, verified_gold)
from research.e008_locks import write_once
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.guard = SeriesLedger(self.study, resource_policy([{"id": "j1"}, {"id": "j2"}]))
        self.guard.start()
        self.provider = Mock()
        self.provider.ledger = self.guard
        self.provider.model = "test-model"
        self.provider.log = self.study / "provider.jsonl"
        self.provider.models.return_value = ["test-model"]
        self.provider.respond.return_value = {"output": [{"type": "function_call", "name": "echo",
                                                          "arguments": '{"value":17}', "call_id": "test-call"}]}

    def transport(self, status, worker=None):
        with self.provider.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "transport_bytes", "worker": worker,
                                     "http_status": status}) + "\n")

    def test_smoke_one_response_and_no_repeat_after_resume(self):
        first = compatibility(self.study, "primary", self.provider)
        self.assertTrue(first["pass"])
        self.assertEqual(compatibility(self.study, "primary", self.provider), first)
        self.assertEqual(self.provider.models.call_count, 1)
        self.assertEqual(self.provider.respond.call_count, 1)
        args = self.provider.respond.call_args.args
        self.assertEqual(args[0], "smoke-primary")
        self.assertIn("function_call_output", [item.get("type") for item in args[1]])

    def test_failed_smoke_is_retained_not_repeated(self):
        self.provider.respond.return_value["output"][0]["arguments"] = '{"value":99}'
        first = compatibility(self.study, "primary", self.provider)
        self.assertFalse(first["pass"])
        self.assertEqual(first["action"], "stop")
        self.assertEqual(compatibility(self.study, "primary", self.provider), first)
        self.assertEqual(self.provider.respond.call_count, 1)

    def test_smoke_result_or_original_trace_mutation_is_rejected(self):
        def available():
            self.transport(200)
            return ["test-model"]
        self.provider.models.side_effect = available
        first = compatibility(self.study, "primary", self.provider)
        result = self.study / "compatibility/primary/result.json"
        result.write_text(json.dumps({**first, "reason": "tampered"}), encoding="utf-8")
        with self.assertRaises(PermissionError):
            compatibility(self.study, "primary", self.provider)
        result.write_text(json.dumps(first), encoding="utf-8")
        self.provider.log.write_text("", encoding="utf-8")
        with self.assertRaises(PermissionError):
            compatibility(self.study, "primary", self.provider)
        self.assertEqual(self.provider.respond.call_count, 1)

    def test_orphan_smoke_never_replayed(self):
        write_once(self.study / "compatibility/primary/started.json", {"model": "test-model"})
        with self.assertRaises(SeriesStopped):
            compatibility(self.study, "primary", self.provider)
        self.provider.models.assert_not_called()
        self.provider.respond.assert_not_called()

    def test_missing_secondary_does_not_start_response_or_substitute_model(self):
        self.provider.models.return_value = ["a-different-model"]
        value = compatibility(self.study, "secondary", self.provider)
        self.assertEqual(value["action"], "unavailable")
        self.provider.respond.assert_not_called()
        self.provider.model = "a-different-model"
        with self.assertRaises(PermissionError):
            compatibility(self.study, "secondary", self.provider)

    def test_secondary_auth_failure_stops_entire_series(self):
        def unauthorized():
            self.transport(401)
            raise RuntimeError("provider HTTP status")
        self.provider.models.side_effect = unauthorized
        value = compatibility(self.study, "secondary", self.provider)
        self.assertEqual(value["action"], "stop")
        self.assertEqual(value["http_status"], 401)
        self.provider.respond.assert_not_called()

    def test_secondary_transient_failure_is_unavailable(self):
        def limited():
            self.transport(429)
            raise RuntimeError("not parsed to classify error")
        self.provider.models.side_effect = limited
        value = compatibility(self.study, "secondary", self.provider)
        self.assertEqual(value["action"], "unavailable")
        self.assertEqual(value["http_status"], 429)

    def test_metadata_status_does_not_mask_failed_smoke_status(self):
        self.transport(503, None)  # Earlier unrelated request.
        self.provider.respond.side_effect = ValueError("wrong model")
        value = compatibility(self.study, "secondary", self.provider)
        self.assertEqual(value["action"], "stop")
        self.assertIsNone(value["http_status"])

    def test_operator_stop_blocks_smoke_before_started_record(self):
        (self.study / "STOP").touch()
        with self.assertRaises(SeriesStopped):
            compatibility(self.study, "primary", self.provider)
        self.assertFalse((self.study / "compatibility/primary").exists())
        self.provider.models.assert_not_called()

    @patch("research.e008_live.wait_until")
    def test_recovery_only_next_position_and_durable_success(self, wait):
        self.provider.models.side_effect = [[], ["test-model"]]
        first = recover(self.study, "j1", self.provider)
        self.assertEqual(first["attempts"], 2)
        self.assertEqual(recover(self.study, "j1", self.provider), first)
        self.assertEqual(self.provider.models.call_count, 2)
        self.provider.respond.assert_not_called()
        self.assertEqual([read_delay(self.study, i) for i in (1, 2)], [30, 120])

    @patch("research.e008_live.wait_until")
    def test_recovery_exhaustion_cannot_reset_probes(self, wait):
        self.provider.models.return_value = []
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "exhausted"):
                recover(self.study, "j1", self.provider)
        self.assertEqual(self.provider.models.call_count, 3)
        self.provider.respond.assert_not_called()

    @patch("research.e008_live.wait_until")
    def test_recovery_network_orphan_stops_without_retry(self, wait):
        write_once(self.study / "recovery/j1/1-started.json", {"at": 0, "delay": 30, "model": "test-model"})
        write_once(self.study / "recovery/j1/1-sending.json", {"at": 30})
        with self.assertRaisesRegex(SeriesStopped, "orphan recovery"):
            recover(self.study, "j1", self.provider)
        self.provider.models.assert_not_called()

    @patch("research.e008_live.wait_until")
    def test_recovery_nontransient_http_stops_before_second_probe(self, wait):
        def forbidden():
            self.transport(403)
            raise RuntimeError("HTTP 403")
        self.provider.models.side_effect = forbidden
        with self.assertRaisesRegex(SeriesStopped, "non-transient"):
            recover(self.study, "j1", self.provider)
        self.assertEqual(self.provider.models.call_count, 1)

    @patch("research.e008_live.recover")
    def test_resumed_failure_uses_structured_status_and_not_error_string(self, recovery):
        self.transport(429, "j1")
        result = {"failure_origin": "provider", "failure_type": "RuntimeError", "failure": "fake auth error"}
        resume_failure(self.study, {"id": "j1"}, result, self.provider)
        recovery.assert_called_once_with(self.study, "j1", self.provider)
        self.transport(401, "j2")
        with self.assertRaises(SeriesStopped):
            resume_failure(self.study, {"id": "j2"}, result, self.provider)

    def test_prior_controller_and_safeguard_failures_still_stop(self):
        for origin in ("controller", "safeguard"):
            with self.assertRaises(SeriesStopped):
                resume_failure(self.study, {"id": "j1"}, {"failure_origin": origin}, None)

    def test_double_controller_lock_rejected_and_released(self):
        with controller_lock(self.study):
            with self.assertRaises(SeriesStopped):
                with controller_lock(self.study):
                    self.fail("two simultaneous controllers")
        with controller_lock(self.study):
            pass

    def test_no_authorization_never_opens_or_starts_study(self):
        with self.assertRaises(PermissionError):
            run(self.study / "absent")
        self.assertFalse((self.study / "absent").exists())

    def test_wrong_directory_does_not_create_controller_state(self):
        with self.assertRaises(PermissionError):
            run(self.study, authorize_api=True)
        self.assertFalse((self.study / "controller.lock").exists())

    def test_gold_requires_all_worlds_and_evaluator_identity(self):
        cache = self.study / "gold"
        write_once(cache / "w.json", {"subsets": {}})
        manifest = {"complete": True, "worlds": {"w": {"file": "w.json", "split": "test",
                                                       "sha256": sha(cache / "w.json")}},
                    "binding": {"source_hashes": {"oracle.py": "expected"}}}
        write_once(cache / "manifest.json", manifest)
        corpus = {"worlds": [{"id": "w", "split": "test"}]}
        _, gold = verified_gold(cache, corpus, {"oracle.py": "expected"})
        self.assertEqual(gold, {"w": {"subsets": {}}})
        with self.assertRaises(PermissionError):
            verified_gold(cache, corpus, {"oracle.py": "changed"})
        corpus["worlds"].append({"id": "missing", "split": "test"})
        with self.assertRaises(PermissionError):
            verified_gold(cache, corpus, {"oracle.py": "expected"})

    def test_real_git_commit_precedes_admission_and_dirty_bytes_rejected(self):
        repo = self.study / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        git("init")
        source = repo / "source.py"
        source.write_text("value = 1\n", encoding="utf-8", newline="\n")
        registration = repo / REGISTRATION
        write_once(registration, {"fixture": True, "not_real_preregistration": True})
        hashes = {"source.py": sha(source)}
        with self.assertRaises(subprocess.CalledProcessError):
            commit_binding(repo, registration, hashes)
        git("add", "source.py", REGISTRATION)
        git("-c", "user.name=E008 local fixture", "-c", "user.email=fixture@invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", "Synthetic gate fixture only")
        first = commit_binding(repo, registration, hashes)
        self.assertEqual(first["commit"], git("rev-parse", "HEAD").stdout.decode().strip())
        source.write_text("value = 2\n", encoding="utf-8", newline="\n")
        with self.assertRaises(PermissionError):
            commit_binding(repo, registration, hashes)
        with self.assertRaises(PermissionError):
            commit_binding(repo, registration, {"source.py": sha(source)})


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_delay(study, number):
    return json.loads((study / f"recovery/j1/{number}-started.json").read_text())["delay"]


if __name__ == "__main__":
    unittest.main()
