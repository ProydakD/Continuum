from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research.e008_integrity import admission, job_timeline, network_ledger, table
from research.common import digest
from research.e008_execute import ledger_key
from research.e008_network import NetworkIndex
from research.e008_resources import resource_policy


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.study = Path(self.tmp.name)
        self.jobs = [{"id": "j1", "world": "w", "condition": "C1", "stage": "A", "phase": "calibration"},
                     {"id": "j2", "world": "w", "condition": "C1", "stage": "D", "phase": "test"}]
        self.reg = {"schedule": self.jobs, "resources": resource_policy(self.jobs)}
        self.db = self.study / "provider-ledger.sqlite3"
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TABLE attempts(id INTEGER,worker TEXT,started REAL,reserved TEXT,outcome TEXT,usage TEXT)")
            c.execute("INSERT INTO attempts VALUES(1,'j1',12,'0','completed',?)",
                      (json.dumps({"input_tokens": 2, "output_tokens": 1}),))
            c.execute("CREATE TABLE metadata_attempts(id INTEGER,started REAL,outcome TEXT)")
            c.execute("CREATE TABLE runtime_policy(value TEXT,started REAL,last_wall REAL)")
            c.execute("INSERT INTO runtime_policy VALUES(?,10,15)", (json.dumps(self.reg["resources"]),))
            c.execute("CREATE TABLE policy(value TEXT)")
            c.execute("INSERT INTO policy VALUES(?)", (json.dumps({"unbounded": True, "budget": "None", "upper": "None"}),))
            c.commit()
        self.events = [{"event": "request_started", "attempt": 1, "worker": "j1"},
                       {"event": "response", "attempt": 1, "worker": "j1",
                        "response": {"usage": {"input_tokens": 2, "output_tokens": 1}}}]
        self.write_events()
        self.times = {"j1": {"started": 11, "finished": 13}}

    def write_events(self):
        (self.study / "provider.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in self.events), encoding="utf-8")

    def check(self):
        return network_ledger(self.study, self.reg, NetworkIndex(self.study / "provider.jsonl"), job_times=self.times)

    def test_reservation_and_trace_agree(self):
        self.assertEqual(self.check()["response_attempts"], 1)
        self.assertEqual(self.check()["first_reservation"], 12)

    def test_missing_extra_pending_or_foreign_reservation_rejected(self):
        for sql in ("DELETE FROM attempts", "UPDATE attempts SET outcome='pending'",
                    "UPDATE attempts SET worker='foreign'", "UPDATE attempts SET started=20",
                    "UPDATE attempts SET usage='{}'", "UPDATE attempts SET reserved='99'"):
            with self.subTest(sql=sql), closing(sqlite3.connect(self.db)) as c:
                c.execute("SAVEPOINT probe")
                c.execute(sql)
                # The auditor uses its own read-only connection; publish this
                # intentionally altered test fixture, then restore saved bytes.
                c.rollback()
                before = self.db.read_bytes()
                c.execute(sql)
                c.commit()
                try:
                    with self.assertRaises(PermissionError):
                        self.check()
                finally:
                    c.close()
                    self.db.write_bytes(before)

    def test_returned_usage_is_retained_as_observation_but_failed_ledger_stays_unknown(self):
        self.events.append({"event": "request_failed", "attempt": 1})
        self.write_events()
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE attempts SET outcome='failed_or_unknown',usage='null'")
            c.commit()
        self.assertEqual(self.check()["failed_or_unknown"], 1)

    def test_unrecorded_metadata_cannot_be_reported_as_zero_overhead(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("INSERT INTO metadata_attempts VALUES(1,10,'failed_or_unknown')")
            c.commit()
        with self.assertRaises(PermissionError):
            self.check()

    def test_fixture_cannot_be_scientific_admission(self):
        result = admission(self.study, {"fixture": True}, None, {})
        self.assertFalse(result["pass"])

    def test_read_only_table_does_not_create_missing_database(self):
        with self.assertRaises(FileNotFoundError):
            table(self.study / "absent.sqlite3", "attempts")
        self.assertFalse((self.study / "absent.sqlite3").exists())

    def test_selection_chronology_rejects_after_test_lock(self):
        with closing(sqlite3.connect(self.study / "jobs.sqlite3")) as c:
            c.execute("CREATE TABLE jobs(id TEXT,ordinal INTEGER,status TEXT,started REAL,finished REAL)")
            c.executemany("INSERT INTO jobs VALUES(?,?,'completed',?,?)",
                          [(ledger_key(j), i, 10 + 10 * i, 15 + 10 * i) for i, j in enumerate(self.jobs)])
            c.commit()
        (self.study / "locks").mkdir()
        for name in ("calibration", "protocol"):
            (self.study / f"locks/{name}.json").write_text('{"created_at":17}', encoding="utf-8")
        self.assertEqual(len(job_timeline(self.study, self.jobs)), 2)
        (self.study / "locks/protocol.json").write_text('{"created_at":21}', encoding="utf-8")
        with self.assertRaises(PermissionError):
            job_timeline(self.study, self.jobs)

    def test_prepared_commit_blobs_checked_independently_of_current_head(self):
        repo = self.study / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(["git", "-c", "core.autocrlf=false",
                                            "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                                            *args], cwd=repo, stderr=subprocess.PIPE).decode().strip()
        git("init", "-q")
        (repo / "source.py").write_bytes(b"first = True\n")
        git("add", "source.py")
        git("commit", "-qm", "fixture baseline")
        earlier = git("rev-parse", "HEAD")
        self.reg.update(fixture=False, implementation_hashes={"source.py": digest(repo / "source.py")})
        (self.study / "registration.json").write_text(json.dumps(self.reg), encoding="utf-8")
        (repo / "docs/research").mkdir(parents=True)
        (repo / "docs/research/E008-PREREGISTRATION.json").write_bytes((self.study / "registration.json").read_bytes())
        git("add", "docs/research/E008-PREREGISTRATION.json")
        git("commit", "-qm", "fixture registration")
        committed = git("rev-parse", "HEAD")
        (self.study / "network-start.json").write_text('{"at":11}', encoding="utf-8")
        gate = self.study / "live-gate.json"
        gate.write_text(json.dumps({"commit": committed, "prepared_at": 10}), encoding="utf-8")
        with patch("research.e008_integrity.PROJECT", repo), patch(
                "research.e008_integrity.load", return_value=(self.reg, None, None)):
            result = admission(self.study, self.reg, NetworkIndex(self.study / "provider.jsonl"), self.times)
            self.assertTrue(result["pass"])
            gate.write_text(json.dumps({"commit": earlier, "prepared_at": 10}), encoding="utf-8")
            with self.assertRaises(subprocess.CalledProcessError):
                admission(self.study, self.reg, NetworkIndex(self.study / "provider.jsonl"), self.times)


if __name__ == "__main__":
    unittest.main()
