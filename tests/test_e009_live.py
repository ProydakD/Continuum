import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from research.e009_live import amend_plan, create_plan, load_plan, next_assignment, pilot_next, verify_model
from research.e009_provider import ProviderFailure
from research.e009_raw import write_once
from research.common import digest


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "pilot"
        self.source_patch = patch("research.e009_live.execution_sources", return_value={"source.py": "hash"})
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        create_plan(self.directory, "sha256:pinned-test-fixture")
        self.plan = load_plan(self.directory)[1]

    def provider(self):
        provider = Mock()
        provider.respond.return_value = {"model": "gpt-6.1-sol", "output": []}
        provider.ledger.records.return_value = []
        provider.accounting.return_value = {"fixture": True}
        return provider

    def confirm(self):
        provider = self.provider()
        with patch("research.e009_live.HTTPSProvider", return_value=provider):
            result = verify_model(self.directory, authorize=True)
        return result, provider

    def test_disjoint_reserved_splits_and_complete_pilot_assignments(self):
        names = ["development_worlds", "pilot_worlds", "t2_training_worlds", "t2_validation_worlds"]
        splits = [set(self.plan[name]) for name in names]
        self.assertTrue(all(len(s) == 12 for s in splits))
        self.assertEqual(len(set.union(*splits)), 48)
        self.assertEqual(len(set(self.plan["non_test_reserved"])), 96)
        self.assertFalse(self.plan["heldout_generated"])
        assignments = self.plan["assignments"]
        self.assertEqual(len({(a["world"], a["condition"], a["track"]) for a in assignments}), 120)
        self.assertEqual(self.plan["maximum_contexts"], 5 * len(assignments))
        with self.assertRaises(FileExistsError): create_plan(self.directory, "unused")

    def test_plan_and_source_changes_are_rejected(self):
        with patch("research.e009_live.execution_sources", return_value={}):
            with self.assertRaisesRegex(ValueError, "source binding"): load_plan(self.directory)
        (self.directory / "PLAN.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "plan hash"): load_plan(self.directory)

    def test_no_implicit_live_authorization(self):
        with self.assertRaisesRegex(ProviderFailure, "authorization_required"):
            verify_model(self.directory)
        self.assertFalse((self.directory / "availability").exists())

    def test_success_is_reused_and_interrupted_pointer_is_repaired_without_calls(self):
        result, provider = self.confirm()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(provider.respond.call_count, 1)
        self.assertEqual(provider.respond.call_args.args[1]["model"], "gpt-6.1-sol")
        (self.directory / "availability/VERIFIED.json").unlink()
        with patch("research.e009_live.HTTPSProvider", side_effect=AssertionError("must not submit")):
            self.assertEqual(verify_model(self.directory), result)
        pointer = json.loads((self.directory / "availability/VERIFIED.json").read_text())
        self.assertEqual(digest(Path(pointer["result"])), pointer["sha256"])

    def test_failure_requires_explicit_spaced_append_only_retry(self):
        provider = self.provider()
        provider.respond.side_effect = ProviderFailure("network_failure")
        with patch("research.e009_live.HTTPSProvider", return_value=provider), patch("research.e009_live.time.time", return_value=100):
            first = verify_model(self.directory, authorize=True)
            self.assertEqual(verify_model(self.directory, authorize=True), first)
            with self.assertRaisesRegex(ValueError, "60 seconds"):
                verify_model(self.directory, authorize=True, retry_failed=True)
        with patch("research.e009_live.HTTPSProvider", return_value=provider), patch("research.e009_live.time.time", return_value=161):
            second = verify_model(self.directory, authorize=True, retry_failed=True)
        self.assertEqual(provider.respond.call_count, 2)
        self.assertNotEqual(first["finished"], second["finished"])
        self.assertEqual(len(list((self.directory / "availability").glob("attempt-*/RESULT.json"))), 2)
        self.assertFalse((self.directory / "availability/VERIFIED.json").exists())

    def test_orphan_availability_never_retries(self):
        (self.directory / "availability/attempt-001").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "orphan availability"):
            verify_model(self.directory, authorize=True, retry_failed=True)

    def test_stop_before_assignment_or_provider_creation(self):
        (self.directory / "STOP").touch()
        with self.assertRaisesRegex(ValueError, "operator stop"):
            pilot_next(self.directory, authorize=True)
        self.assertFalse((self.directory / "runs").exists())

    def test_orphan_assignment_never_repeats(self):
        assignment = next_assignment(self.directory, self.plan)
        (self.directory / "runs" / assignment["id"]).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "orphan assignment"):
            next_assignment(self.directory, self.plan)

    def test_failed_assigned_outcomes_are_kept_and_three_failures_stop_new_work(self):
        self.confirm()
        def run(directory, episode, condition, track, provider, image, *, limits, protocol_version):
            directory.mkdir(parents=True)
            write_once(directory / "MANIFEST.json", {"fixture": True})
            self.assertEqual(limits, self.plan["limits"])
            self.assertEqual(protocol_version, 2)
            return {"directory": str(directory), "manifest_sha256": digest(directory / "MANIFEST.json"),
                    "statuses": ["provider_failure"] + ["upstream_missing"] * 4, "fixture": True, "response_calls": 1}
        with patch("research.e009_live.HTTPSProvider", return_value=self.provider()), patch("research.e009_live.run_chain", side_effect=run) as runner:
            for _ in range(3): pilot_next(self.directory, authorize=True)
            with self.assertRaisesRegex(ValueError, "three assignments"):
                pilot_next(self.directory, authorize=True)
            self.assertEqual(runner.call_count, 3)
        self.assertEqual(len(list((self.directory / "receipts").glob("*.json"))), 3)

    def test_receipt_assignment_tamper_rejected(self):
        assignment = self.plan["assignments"][0]
        target = self.directory / "runs" / assignment["id"]
        target.mkdir(parents=True)
        write_once(target / "MANIFEST.json", {})
        write_once(self.directory / "receipts" / (assignment["id"] + ".json"), {
            "directory": str(target), "manifest_sha256": digest(target / "MANIFEST.json"),
            "assignment": {**assignment, "world": -1}, "plan_sha256": digest(self.directory / "PLAN.json")})
        with self.assertRaisesRegex(ValueError, "outcome binding"):
            next_assignment(self.directory, self.plan)

    def test_amendment_keeps_parent_plan_and_changes_only_unfinished_execution(self):
        original = (self.directory / "PLAN.json").read_bytes()
        with patch("research.e009_live.execution_sources", return_value={"source.py": "new-hash"}):
            result = amend_plan(self.directory, "public schema and sequential batch correction")
            self.assertEqual(result["next_assignment"], "pilot-001")
            self.assertEqual((self.directory / "PLAN.json").read_bytes(), original)
            _, amended, _ = load_plan(self.directory)
            self.assertEqual(amended["assignments"], self.plan["assignments"])
            self.assertEqual(amended["_execution_binding_sha256"], result["sha256"])
            self.assertEqual(amended["source_hashes"], {"source.py": "new-hash"})
        with self.assertRaisesRegex(ValueError, "source binding"):
            load_plan(self.directory)

    def test_amendment_freezes_prior_receipt_and_cannot_repeat_it(self):
        assignment = self.plan["assignments"][0]
        target = self.directory / "runs" / assignment["id"]
        target.mkdir(parents=True)
        write_once(target / "MANIFEST.json", {})
        receipt = self.directory / "receipts" / (assignment["id"] + ".json")
        write_once(receipt, {"directory": str(target), "manifest_sha256": digest(target / "MANIFEST.json"),
            "assignment": assignment, "plan_sha256": digest(self.directory / "PLAN.json"), "statuses": ["failed"] * 5})
        result = amend_plan(self.directory, "versioned correction after retained failure")
        _, plan, _ = load_plan(self.directory)
        self.assertEqual(result["next_assignment"], "pilot-002")
        self.assertEqual(next_assignment(self.directory, plan)["id"], "pilot-002")
        receipt.write_text("{}")
        with self.assertRaisesRegex(ValueError, "pre-amendment outcome"):
            load_plan(self.directory)


if __name__ == "__main__":
    unittest.main()
