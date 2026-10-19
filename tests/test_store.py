import concurrent.futures
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from continuum.store import Store, ConflictError


class ContinuumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "shared.sqlite3"
        self.a = Store(self.db, actor="A")
        self.b = Store(self.db, actor="B")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_instance_inherits_work_and_state(self):
        task = self.a.create_task("Study", "Find and verify a principle", "Measure A")
        self.assertEqual(self.b.bootstrap()["open_tasks"][0]["id"], task["id"])
        leased = self.b.claim_task(task["id"], expected_revision=task["revision"])
        self.assertEqual(leased["revision"], 2)
        committed = self.b.checkpoint_task(task["id"], "Measure B", "Measurement A complete",
                                           expected_revision=leased["revision"])
        self.assertEqual(committed["status"], "open")
        c = Store(self.db, actor="C")
        self.assertEqual(c.bootstrap()["open_tasks"][0]["next_step"], "Measure B")
        self.assertEqual(c.bootstrap()["open_tasks"][0]["result"], "Measurement A complete")
        followup = c.claim_task(task["id"], expected_revision=committed["revision"])
        self.assertEqual(followup["lease_owner"], "C")

    def test_lease_blocks_concurrent_writes(self):
        task = self.a.create_task("A", "B", "C")
        leased = self.a.claim_task(task["id"], expected_revision=task["revision"])
        with self.assertRaises(ConflictError):
            self.b.claim_task(task["id"], expected_revision=leased["revision"])
        with self.assertRaises(ConflictError):
            self.b.checkpoint_task(task["id"], "new", "other")
        self.assertEqual(self.a.get_task(task["id"])["lease_owner"], "A")
        with self.assertRaises(ConflictError):
            self.b.claim_task(task["id"], takeover=True, expected_revision=leased["revision"], takeover_reason="test")
        self.assertEqual(self.b.changes()["events"][-1]["action"], "claimed")

    def test_revision_prevents_lost_updates(self):
        task = self.a.create_task("Study", "Find objective", "Start")
        leased = self.a.claim_task(task["id"], expected_revision=task["revision"])
        self.a.checkpoint_task(task["id"], "Next", "interim", release=False, expected_revision=leased["revision"])
        with self.assertRaises(ConflictError):
            self.a.finish_task(task["id"], "premature", expected_revision=leased["revision"])

    def test_claims_keep_contradictions(self):
        claim = self.a.add_claim({"subject": "observation:1", "predicate": "implies", "object": "hypothesis:1"})
        self.assertEqual(self.b.get_claim(claim["id"])["state"], "proposed")
        support = self.b.add_evidence(claim["id"], "supports", "test://run/1", "Observed in experiment", expected_revision=claim["revision"])
        self.assertEqual(support["state"], "supported")
        conflicted = self.a.add_evidence(claim["id"], "contradicts", "test://run/2", "Counterexample", expected_revision=support["revision"])
        self.assertEqual(conflicted["state"], "contested")
        self.assertEqual(len(conflicted["evidence"]), 2)
        other = self.a.add_claim({"subject": "observation:1", "predicate": "implies", "object": "hypothesis:2"})
        link = self.a.link_claims(claim["id"], other["id"], "contradicts", expected_from_revision=conflicted["revision"], expected_to_revision=other["revision"])
        self.assertEqual(link["relation"], "contradicts")
        self.assertEqual(len(self.b.get_claim(other["id"])["links"]), 1)

    def test_separate_workspaces(self):
        self.a.create_task("secret", "internal", "first", workspace="private")
        self.assertFalse(self.b.bootstrap("lab")["open_tasks"])
        self.assertEqual(len(self.b.bootstrap("private")["open_tasks"]), 1)

    def test_event_cursor_and_immutability(self):
        self.a.create_task("T1", "O1", "N1")
        first = self.b.changes()
        self.assertEqual(len(first["events"]), 1)
        cursor = first["next_seq"]
        self.b.create_task("T2", "O2", "N2")
        second = self.a.changes(after_seq=cursor)
        self.assertEqual(len(second["events"]), 1)
        self.assertGreater(second["next_seq"], cursor)
        with closing(sqlite3.connect(self.db)) as conn:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE events SET action='tampered' WHERE seq=1")

    def test_idempotent_create(self):
        a = self.a.create_task("A", "B", "C", request_key="req-1")
        b = self.b.create_task("A", "B", "C", request_key="req-1")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(self.b.list_tasks()), 1)
        with self.assertRaises(ConflictError):
            self.b.add_claim({"subject": "a", "predicate": "b", "object": "c"}, request_key="req-1")

    def test_two_contenders_one_lease(self):
        task = self.a.create_task("A", "B", "C")
        owners = [Store(self.db, actor=f"contender:{x}") for x in range(2)]
        def compete(store):
            try:
                return store.claim_task(task["id"], expected_revision=task["revision"])["lease_owner"]
            except ConflictError:
                return "conflict"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, owners))
        self.assertEqual(sum(x == "conflict" for x in results), 1)


if __name__ == "__main__":
    unittest.main()
