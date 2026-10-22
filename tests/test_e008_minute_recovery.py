import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

from research import e008_minute_recovery as minute
from research.e008_locks import read, write_once
from research.e008_resources import SeriesLedger, SeriesStopped, resource_policy


class MinuteRecoveryTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.study = Path(folder.name)
        guard = SeriesLedger(self.study, resource_policy([{"id": "j1"}]))
        guard.start()
        self.provider = Mock(model="p", ledger=guard, log=self.study / "provider.jsonl")
        self.provider.log.write_bytes(b"")
        self.provider.models.side_effect = self.available
        self.wait = patch.object(minute, "wait_until").start()
        self.addCleanup(patch.stopall)
        self.base = minute.recovery_root(self.study, "E008-A004")

    def transport(self, status=200):
        with self.provider.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "transport_bytes", "method": "GET", "worker": None,
                "http_status": status, "request_sent": status is not None, "response_complete": status is not None,
                "request_body_bytes": 0, "response_body_bytes": 12}) + "\n")

    def available(self):
        self.transport()
        return ["p"]

    def missing(self):
        self.transport()
        return []

    def fail502(self):
        self.transport(502)
        raise RuntimeError("synthetic HTTP502")

    def gate(self):
        return minute.recover(self.study, "E008-A004", self.provider)

    def test_success_cached_without_responses(self):
        expected = {"pass": True, "attempts": 1, "model": "p"}
        self.assertEqual(self.gate(), expected)
        self.assertEqual(self.gate(), expected)
        self.provider.models.assert_called_once()
        self.provider.respond.assert_not_called()

    def test_ten_502_then_ask_without_eleventh_on_restart(self):
        self.provider.models.side_effect = self.fail502
        for _ in range(2):
            with self.assertRaisesRegex(SeriesStopped, "10 attempts; ask user: HTTP502=10, model_absent=0"):
                self.gate()
        self.assertEqual(self.provider.models.call_count, 10)
        self.assertEqual(read(self.base / "exhausted.json")["http502_responses"], 10)
        self.assertFalse((self.base / "11-started.json").exists())
        self.provider.respond.assert_not_called()

    def test_missing_catalogue_is_not_reported_as_502(self):
        self.provider.models.side_effect = self.missing
        with self.assertRaisesRegex(SeriesStopped, "HTTP502=0, model_absent=10"):
            self.gate()
        self.assertEqual(self.provider.models.call_count, 10)

    def test_success_on_last_attempt_stops_at_ten(self):
        count = 0
        def models():
            nonlocal count
            count += 1
            return self.available() if count == 10 else self.missing()
        self.provider.models.side_effect = models
        self.assertEqual(self.gate()["attempts"], 10)
        self.assertFalse((self.base / "exhausted.json").exists())
        self.assertEqual(self.gate()["attempts"], 10)
        self.assertEqual(self.provider.models.call_count, 10)

    def test_each_attempt_waits_a_minute_using_original_guard(self):
        self.provider.models.side_effect = self.missing
        with self.assertRaises(SeriesStopped):
            self.gate()
        self.assertEqual(self.wait.call_count, 10)
        for number, call in enumerate(self.wait.call_args_list, 1):
            started = read(self.base / f"{number}-started.json")
            self.assertEqual(started["delay"], 60)
            self.assertEqual(call.args, (started["at"] + 60, self.provider.ledger))

    def test_unsent_wait_resumes_original_deadline(self):
        write_once(self.base / "1-started.json", {"at": 100, "delay": 60, "model": "p"})
        self.gate()
        self.wait.assert_called_once_with(160, self.provider.ledger)

    def test_orphan_send_is_never_repeated(self):
        write_once(self.base / "1-started.json", {"at": 100, "delay": 60, "model": "p"})
        write_once(self.base / "1-sending.json", {"at": 160})
        with self.assertRaisesRegex(SeriesStopped, "orphan"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_stop_deadline_and_quota_remain_enforced(self):
        (self.study / "STOP").touch()
        with self.assertRaises(SeriesStopped):
            self.gate()
        (self.study / "STOP").unlink()
        for reason in ("deadline", "quota"):
            with patch.object(self.provider.ledger, "check_context", side_effect=SeriesStopped(reason)):
                with self.assertRaisesRegex(SeriesStopped, reason):
                    self.gate()
        self.provider.models.assert_not_called()

    def test_fatal_status_stops_without_ten_retries(self):
        for status, error in ((401, RuntimeError), (403, RuntimeError), (408, RuntimeError), (None, OSError)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                self.study = Path(folder)
                self.provider.log = self.study / "provider.jsonl"
                self.provider.log.write_bytes(b"")
                self.provider.ledger = SeriesLedger(self.study, resource_policy([{"id": "j1"}]))
                self.provider.ledger.start()
                def fail():
                    self.transport(status)
                    raise error("synthetic")
                self.provider.models.reset_mock()
                self.provider.models.side_effect = fail
                for _ in range(2):
                    with self.assertRaisesRegex(SeriesStopped, "non-transient"):
                        self.gate()
                self.provider.models.assert_called_once()

    def test_cached_model_change_rejected(self):
        self.gate()
        self.provider.model = "changed"
        with self.assertRaisesRegex(PermissionError, "assignment changed"):
            self.gate()
        self.provider.models.assert_called_once()

    def test_tampered_evidence_rejected_without_new_request(self):
        self.gate()
        self.provider.log.write_bytes(b"tampered")
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_called_once()

    def test_old_episodes_and_escape_paths_rejected(self):
        for identity in ("j02139", "j00264", "../outside", "j03427", "j2140", "E008-A003"):
            with self.assertRaises(PermissionError):
                minute.recover(self.study, identity, self.provider)
        self.provider.models.assert_not_called()

    def test_extra_attempt_file_rejected(self):
        write_once(self.base / "11-started.json", {"at": 100})
        with self.assertRaisesRegex(PermissionError, "unexpected"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_different_clock_or_journal_rejected(self):
        self.provider.log = self.study / "other.jsonl"
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.log = self.study / "provider.jsonl"
        self.provider.ledger = Mock(study=self.study / "reset-clock")
        with self.assertRaises(PermissionError):
            self.gate()
        self.provider.models.assert_not_called()

    def test_completion_or_exhaustion_without_evidence_starts_no_request(self):
        for name in ("complete.json", "exhausted.json"):
            path = self.base / name
            write_once(path, {"pass": True})
            with self.assertRaises(PermissionError):
                self.gate()
            path.unlink()
        self.provider.models.assert_not_called()

    def test_noncontiguous_episode_starts_no_request(self):
        write_once(self.base / "2-started.json", {"at": 100, "delay": 60, "model": "p"})
        with self.assertRaisesRegex(PermissionError, "noncontiguous"):
            self.gate()
        self.provider.models.assert_not_called()

    def test_after_success_attempt_is_not_ignored(self):
        self.gate()
        write_once(self.base / "2-started.json", {"at": 100, "delay": 60, "model": "p"})
        with self.assertRaisesRegex(PermissionError, "after successful"):
            self.gate()
        self.provider.models.assert_called_once()

    def test_mixed_failures_keep_distinct_counts(self):
        calls = iter([self.fail502] * 5 + [self.missing] * 5)
        self.provider.models.side_effect = lambda: next(calls)()
        with self.assertRaisesRegex(SeriesStopped, "HTTP502=5, model_absent=5"):
            self.gate()
        self.assertEqual(self.provider.models.call_count, 10)

    def test_future_episode_has_its_own_bounded_records(self):
        result = minute.recover(self.study, "j02140", self.provider)
        self.assertEqual(result["attempts"], 1)
        self.assertTrue((self.study / "recovery/j02140/complete.json").exists())
        self.assertFalse((self.study / "recovery/j02139").exists())
