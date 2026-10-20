import copy
import json
from pathlib import Path
import tempfile
import unittest

from research.e003 import Jobs
from research.e008_execute import ledger_key, ledger_record
from research.e008_locks import EvidenceSnapshot, SnapshotDecisions, read, seal_outcome, write_once
from research.e008_resources import SeriesLedger, SeriesStopped, directory_bytes, resource_policy


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.study = Path(self.tmp.name)
        self.jobs = [{"id": "a", "world": "w", "stage": "A", "condition": "C1", "phase": "calibration",
                      "role": "investigator", "source": None, "budget": 1024, "protocol_version": None},
                     {"id": "b", "world": "w", "stage": "D", "condition": "C1", "phase": "calibration",
                      "role": "investigator", "source": "a", "budget": 1024, "protocol_version": None}]
        write_once(self.study / "registration.json", {"schedule": self.jobs})
        write_once(self.study / "oracle.json", {"worlds": []})
        self.ledger = Jobs(self.study / "jobs.sqlite3", [ledger_record(j) for j in self.jobs])
        self.finish(self.jobs[0])

    def finish(self, job):
        self.ledger.claim(ledger_key(job))
        unit = self.study / "units" / job["id"]
        unit.mkdir(parents=True, exist_ok=True)
        (unit / "raw.txt").write_bytes(b"original")
        result = {"status": "completed", "job": job, "fixture": True}
        write_once(unit / "result.json", result)
        seal_outcome(self.study, job, {"pass": True}, {"verified_count": 1})
        self.ledger.finish(ledger_key(job), result)

    def test_cursor_and_resume_only_pending_then_terminal(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        self.assertEqual(evidence.next_job(), self.jobs[1])
        self.finish(self.jobs[1])
        evidence.record("b")
        self.assertIsNone(evidence.next_job())
        evidence.verify_all()
        self.assertIsNone(EvidenceSnapshot(self.study, self.jobs).next_job())
        with self.assertRaises(PermissionError):
            evidence.record("b")

    def test_unverified_raw_changes_cannot_change_cached_selection_and_fail_exit(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        original = evidence.get(self.jobs[0])
        (self.study / "units/a/raw.txt").write_bytes(b"tampered")
        self.assertEqual(evidence.get(self.jobs[0]), original)
        with self.assertRaises(PermissionError):
            evidence.verify_all()
        with self.assertRaises(PermissionError):
            EvidenceSnapshot(self.study, self.jobs)

    def test_returned_values_and_external_schedule_do_not_mutate_frozen_snapshot(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        value = evidence.get(self.jobs[0])
        value["score"]["verified_count"] = 999
        self.assertEqual(evidence.get(self.jobs[0])["score"]["verified_count"], 1)
        other = copy.deepcopy(self.jobs[0])
        other["budget"] = 2048
        with self.assertRaises(PermissionError):
            evidence.get(other)

    def test_memo_reopens_lock_bytes_and_returns_copy(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        store = SnapshotDecisions(self.study, [], self.jobs, evidence)
        lock = self.study / "locks/calibration.json"
        write_once(lock, {"chosen": 1024})
        calls = []
        def create():
            calls.append(True)
            return {"decision": {"budget": 1024}}
        first = store._cached(("test",), create)
        first["decision"]["budget"] = 999
        self.assertEqual(store._cached(("test",), create)["decision"]["budget"], 1024)
        self.assertEqual(len(calls), 1)
        lock.write_text('{"chosen":2048}', encoding="utf-8")
        with self.assertRaises(PermissionError):
            store._cached(("test",), create)

    def test_frozen_source_seals_not_replaced_with_mutated_disk_hash(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        store = SnapshotDecisions(self.study, [], self.jobs, evidence)
        expected = store._sources([self.jobs[0]])
        with (self.study / "units/a/outcome.json").open("a", encoding="utf-8") as f:
            f.write(" ")
        self.assertEqual(store._sources([self.jobs[0]]), expected)
        with self.assertRaises(PermissionError):
            evidence.verify_all()

    def test_space_counts_closed_active_and_control_files_exactly(self):
        (self.study / "gold").mkdir()
        (self.study / "gold/manifest.json").write_text("{}", encoding="utf-8")
        (self.study / "gold/world.json").write_bytes(b"x" * 8192)
        evidence = EvidenceSnapshot(self.study, self.jobs)
        self.assertEqual(directory_bytes(self.study, evidence=evidence), directory_bytes(self.study))
        evidence.active = "b"
        active = self.study / "units/b"
        active.mkdir()
        (active / "payload").write_bytes(b"x" * 16384)
        (self.study / "provider.jsonl").write_bytes(b"real growing root journal\n")
        self.assertEqual(directory_bytes(self.study, evidence=evidence), directory_bytes(self.study))
        self.finish(self.jobs[1])
        evidence.record("b")
        self.assertEqual(directory_bytes(self.study, evidence=evidence), directory_bytes(self.study))
        evidence.verify_all()
        (self.study / "gold/world.json").write_bytes(b"y" * 8192)
        with self.assertRaises(PermissionError):
            evidence.verify_all()

    def test_orphan_directory_and_running_ledger_never_resumed(self):
        (self.study / "units/b").mkdir()
        with self.assertRaises(PermissionError):
            EvidenceSnapshot(self.study, self.jobs)
        (self.study / "units/b").rmdir()
        self.ledger.claim(ledger_key(self.jobs[1]))
        with self.assertRaises(PermissionError):
            EvidenceSnapshot(self.study, self.jobs)

    def test_stop_and_request_quota_remain_active_with_cached_space(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        guard = SeriesLedger(self.study, resource_policy(self.jobs))
        guard.use_evidence(evidence)
        guard.start()
        for _ in range(10):
            guard.finish(guard.reserve("a"), "completed")
        with self.assertRaises(SeriesStopped):
            guard.reserve("a")
        (self.study / "STOP").touch()
        with self.assertRaises(SeriesStopped):
            guard.reserve("b")
        evidence.verify_all()

    def test_foreign_snapshot_and_foreign_new_unit_rejected(self):
        evidence = EvidenceSnapshot(self.study, self.jobs)
        with tempfile.TemporaryDirectory() as tmp:
            guard = SeriesLedger(Path(tmp), resource_policy(self.jobs))
            with self.assertRaises(SeriesStopped):
                guard.use_evidence(evidence)
        (self.study / "units/foreign").mkdir()
        with self.assertRaises(PermissionError):
            evidence.verify_all()


if __name__ == "__main__":
    unittest.main()
