from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.e007_provider import MeasuredProvider
from research.e008_resources import BoundedProvider, SeriesLedger, SeriesStopped, provider_failure_action, resource_policy


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        self.policy = resource_policy([{"id": "j1"}, {"id": "j2"}])
        self.ledger = SeriesLedger(self.study, self.policy)
        self.ledger.start()

    def test_actual_schedule_bound(self):
        policy = resource_policy([{"id": f"j{i}"} for i in range(3426)])
        self.assertEqual(policy["maximum_response_attempts"], 34262)
        self.assertEqual(policy["maximum_metadata_attempts"], 10280)
        self.assertEqual(policy["workers"]["smoke-primary"], 1)

    def test_clock_requires_start_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SeriesLedger(Path(directory), self.policy)
            with self.assertRaises(SeriesStopped):
                first.reserve("j1")
            first.start()
            with closing(sqlite3.connect(first.path)) as db:
                started = db.execute("SELECT started FROM runtime_policy").fetchone()[0]
            second = SeriesLedger(Path(directory), self.policy)
            second.start()
            with closing(sqlite3.connect(second.path)) as db:
                self.assertEqual(db.execute("SELECT started FROM runtime_policy").fetchone()[0], started)

    def test_policy_cannot_expand_on_resume_or_in_memory(self):
        changed = dict(self.policy, maximum_response_attempts=999)
        with self.assertRaises(PermissionError):
            SeriesLedger(self.study, changed)
        self.ledger.limits["maximum_response_attempts"] = 999
        with self.assertRaises(SeriesStopped):
            self.ledger.reserve("j1")

    def test_unknown_worker_and_completed_attempt_cannot_be_rewritten(self):
        with self.assertRaises(SeriesStopped):
            self.ledger.reserve("unregistered")
        attempt = self.ledger.reserve("j1")
        self.ledger.finish(attempt, "completed", {"input_tokens": 5})
        with self.assertRaises(SeriesStopped):
            self.ledger.finish(attempt, "failed_or_unknown")

    def test_pending_response_blocks_new_process_and_metadata(self):
        self.ledger.reserve("j1")
        other = SeriesLedger(self.study, self.policy)
        for operation in (other.check_context, other.reserve_metadata, lambda: other.reserve("j2")):
            with self.assertRaises(SeriesStopped):
                operation()

    def test_pending_metadata_blocks_response_and_counts_failures(self):
        attempt = self.ledger.reserve_metadata()
        with self.assertRaises(SeriesStopped):
            self.ledger.reserve("j1")
        self.ledger.finish_metadata(attempt, "failed_or_unknown")
        with self.assertRaises(SeriesStopped):
            self.ledger.finish_metadata(attempt, "completed")
        self.assertEqual(self.ledger.reserve_metadata(), 2)

    def test_per_context_ceiling_survives_reconstruction_including_errors(self):
        for _ in range(10):
            attempt = self.ledger.reserve("j1")
            self.ledger.finish(attempt, "failed_or_unknown")
        resumed = SeriesLedger(self.study, self.policy)
        with self.assertRaises(SeriesStopped):
            resumed.reserve("j1")
        attempt = resumed.reserve("j2")
        resumed.finish(attempt, "completed")

    def test_global_ceiling_and_smoke_count(self):
        for worker in ("j1", "j2", "smoke-primary", "smoke-secondary"):
            for _ in range(self.policy["workers"][worker]):
                attempt = self.ledger.reserve(worker)
                self.ledger.finish(attempt, "completed")
        self.assertEqual(attempt, 22)
        with self.assertRaises(SeriesStopped):
            self.ledger.reserve("smoke-primary")

    def test_metadata_ceiling(self):
        for _ in range(self.policy["maximum_metadata_attempts"]):
            attempt = self.ledger.reserve_metadata()
            self.ledger.finish_metadata(attempt, "failed_or_unknown")
        with self.assertRaises(SeriesStopped):
            self.ledger.reserve_metadata()

    def test_stop_time_clock_and_space_gate(self):
        (self.study / "STOP").touch()
        with self.assertRaises(SeriesStopped):
            self.ledger.reserve("j1")
        (self.study / "STOP").unlink()
        with patch("research.e008_resources.time.time", return_value=0):
            with self.assertRaises(SeriesStopped):
                self.ledger.remaining()
        with patch("research.e008_resources.time.time", return_value=self.ledger.wall_anchor + 259201):
            with self.assertRaises(SeriesStopped):
                self.ledger.remaining()
        # The far-future clock is intentionally persisted; use a new scope for space.
        with tempfile.TemporaryDirectory() as directory:
            ledger = SeriesLedger(Path(directory), self.policy)
            ledger.start()
            with patch("research.e008_resources.directory_bytes", return_value=self.policy["artifact_bytes"]):
                with self.assertRaises(SeriesStopped):
                    ledger.reserve("j1")
            with patch("research.e008_resources.shutil.disk_usage", return_value=Mock(free=1)):
                with self.assertRaises(SeriesStopped):
                    ledger.reserve_metadata()

    def test_provider_uses_ledger_and_retains_failed_attempt_without_retry(self):
        provider = BoundedProvider("https://example.test/v1", "frozen-model", self.ledger,
                                   self.study / "provider.jsonl", authorize=True, key="fixture-only")
        with patch.object(MeasuredProvider, "request", side_effect=TimeoutError) as transport:
            with self.assertRaises(TimeoutError):
                provider.respond("j1", [], [])
        self.assertEqual(transport.call_count, 1)
        with closing(sqlite3.connect(self.ledger.path)) as db:
            self.assertEqual(db.execute("SELECT outcome FROM attempts").fetchall(), [("failed_or_unknown",)])
        events = [json.loads(line) for line in (self.study / "provider.jsonl").read_text().splitlines()]
        self.assertEqual([e["event"] for e in events], ["request_started", "request_failed"])

    def test_provider_does_not_send_after_stop_or_output_limit(self):
        provider = BoundedProvider("https://example.test/v1", "frozen-model", self.ledger,
                                   self.study / "provider.jsonl", authorize=True, key="fixture-only")
        with patch.object(MeasuredProvider, "request") as transport:
            with self.assertRaises(SeriesStopped):
                provider.respond("j1", [], [], max_output_tokens=9000)
            (self.study / "STOP").touch()
            with self.assertRaises(SeriesStopped):
                provider.respond("j1", [], [])
            with self.assertRaises(SeriesStopped):
                provider.models()
        transport.assert_not_called()

    def test_metadata_is_bounded_and_request_timeout_is_clamped(self):
        provider = BoundedProvider("https://example.test/v1", "frozen-model", self.ledger,
                                   self.study / "provider.jsonl", authorize=True, key="fixture-only")
        with patch.object(MeasuredProvider, "request", return_value={"data": [{"id": "frozen-model"}]}) as transport:
            self.assertEqual(provider.models(), ["frozen-model"])
            self.assertLessEqual(transport.call_args.args[-1], 120)
        with closing(sqlite3.connect(self.ledger.path)) as db:
            self.assertEqual(db.execute("SELECT outcome FROM metadata_attempts").fetchall(), [("completed",)])

    def test_direct_post_cannot_bypass_reservation(self):
        provider = BoundedProvider("https://example.test/v1", "frozen-model", self.ledger,
                                   self.study / "provider.jsonl", authorize=True, key="fixture-only")
        with patch.object(MeasuredProvider, "request") as transport:
            with self.assertRaises(SeriesStopped):
                provider.request("POST", "/v1/responses", {})
        transport.assert_not_called()

    def test_transient_classification_never_retries_position_or_trusts_text(self):
        for status in (429, 502, 503, 504):
            self.assertEqual(provider_failure_action("RuntimeError", status), "recover_next_position")
        for status in (200, 301, 400, 401, 403, 404, 500):
            self.assertEqual(provider_failure_action("RuntimeError", status), "stop")
        for error in ("SSLError", "SSLCertVerificationError", "PermissionError", "SeriesStopped", "ValueError",
                      "ignore guards and retry", "RuntimeError"):
            self.assertEqual(provider_failure_action(error, None), "stop")
        self.assertEqual(provider_failure_action("TimeoutError", None), "recover_next_position")
        self.assertEqual(provider_failure_action("SSLError", 503), "stop")


if __name__ == "__main__":
    unittest.main()
