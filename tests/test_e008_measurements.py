import json
from pathlib import Path
import tempfile
import unittest

from research.e008_measurements import (
    amortize, api_measurements, chain_ids, combine, context_measurements,
    correct_counts, measure, resource_report,
)


def start(attempt=1, worker="j1"):
    return {"event": "request_started", "attempt": attempt, "worker": worker, "payload": {}}


def response(attempt=1, worker="j1", usage=None):
    return {"event": "response", "attempt": attempt, "worker": worker, "seconds": .5,
            "response": {"usage": usage}}


def transport(worker="j1", complete=True):
    return {"event": "transport_bytes", "worker": worker, "method": "POST",
            "request_body_bytes": 100, "response_body_bytes": 20,
            "request_sent": True, "response_complete": complete}


class MeasurementTests(unittest.TestCase):
    def test_missing_and_failed_usage_is_not_zero_cost(self):
        result = api_measurements([start(), transport(),
                                   {"event": "request_failed", "attempt": 1, "seconds": 2},
                                   start(2), response(2)])
        row = result["workers"]["j1"]
        self.assertEqual(row["input_tokens"], measure(0, 2))
        self.assertEqual(row["api_body_bytes"], measure(120, 1))
        self.assertEqual(row["failed_or_unknown"], 1)
        self.assertEqual(row["api_seconds"], measure(2.5))

    def test_validation_failure_preserves_returned_usage_without_double_count(self):
        result = api_measurements([start(), transport(), response(usage={"input_tokens": 12, "output_tokens": 3}),
                                   {"event": "request_failed", "attempt": 1, "seconds": .6}])
        row = result["workers"]["j1"]
        self.assertEqual(row["input_tokens"], measure(12))
        self.assertEqual(row["api_seconds"], measure(.6))
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["failed_or_unknown"], 1)

    def test_invalid_usage_is_unknown_not_negative_or_boolean(self):
        for value in (True, -1, 1.2, float("nan"), "9"):
            with self.subTest(value=value):
                result = api_measurements([start(), response(usage={"input_tokens": value})])
                self.assertEqual(result["workers"]["j1"]["input_tokens"], measure(0, 1))

    def test_details_are_subsets_not_added_to_totals(self):
        result = api_measurements([start(), response(usage={
            "input_tokens": 10, "output_tokens": 8, "input_tokens_details": {"cached_tokens": 5},
            "output_tokens_details": {"reasoning_tokens": 6}})])
        row = result["workers"]["j1"]
        self.assertEqual(row["input_tokens"], measure(10))
        self.assertEqual(row["cached_input_tokens"], measure(5))

    def test_ambiguous_network_is_rejected(self):
        cases = ([start(), start(2)], [response()], [transport()],
                 [start(), transport(), transport()], [start(), response(worker="other")])
        for events in cases:
            with self.subTest(events=events), self.assertRaises(ValueError):
                api_measurements(events)

    def test_orphan_and_truncated_transport_remain_incomplete(self):
        result = api_measurements([start(), transport(complete=False)])["workers"]["j1"]
        self.assertEqual(result["api_body_bytes"], measure(120, 1))
        self.assertEqual(result["input_tokens"], measure(0, 1))
        self.assertEqual(result["failed_or_unknown"], 1)
        result = api_measurements([start(), dict(transport(complete=False), request_sent=False)])["workers"]["j1"]
        self.assertEqual(result["api_body_bytes"], measure(20, 1))

    def test_metadata_kept_outside_worker_tokens(self):
        event = dict(transport(None), method="GET", request_body_bytes=0)
        result = api_measurements([event])
        self.assertEqual(result["workers"], {})
        self.assertEqual(result["metadata_api_body_bytes"], measure(20))

    def test_full_journal_does_not_pay_for_imaginary_ancestors(self):
        jobs = {"a": {"id": "a"}, "b": {"id": "b", "source": "a"},
                "d": {"id": "d", "source": "b"}, "full": {"id": "full"}}
        self.assertEqual(chain_ids(jobs["d"], jobs), ["d", "b", "a"])
        self.assertEqual(chain_ids(jobs["full"], jobs), ["full"])
        jobs["a"]["source"] = "d"
        with self.assertRaises(ValueError):
            chain_ids(jobs["d"], jobs)

    def test_abstention_not_counted_as_identified_causal_result(self):
        score = {"questions": [
            {"id": "Q1", "valid": True, "target_correct": True, "target_expected": None},
            {"id": "Q2", "valid": True, "target_correct": True, "target_expected": False, "integrative": True},
            {"id": "P1", "valid": True, "target_correct": True, "target_expected": "1"}]}
        self.assertEqual(correct_counts(score), {"identified_new": 1, "correct_abstentions": 1, "integrative_new": 1})

    def test_unknown_setup_prevents_efficiency_ratio(self):
        self.assertIsNone(amortize(measure(20, 1), measure(10), 2, 10)["per_identified_result"])
        self.assertEqual(amortize(measure(20), measure(10), 2, 10)["per_identified_result"], 6)
        self.assertIsNone(amortize(measure(), measure(), 0, 1)["per_identified_result"])

    def test_mcp_counts_seed_and_session_and_rejected_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit = Path(tmp)
            (unit / "supervisor").mkdir()
            for name in ("seed", "session"):
                records = [{"channel": "mcp", "message": {"id": 1}},
                           {"event": "tool_result", "name": "save_memory",
                            "arguments": {"encoding": "base64", "content": "YWJj"}, "value": {"saved": False}}]
                (unit / f"supervisor/{name}.jsonl").write_text(
                    "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            result = context_measurements(unit)
            self.assertEqual(result["mcp_reencoded_bytes"], measure(18))
            self.assertEqual(result["proposed_memory_bytes"], measure(6))

    def test_all_t2_versions_both_lines_and_failures_charged(self):
        jobs = [
            {"id": "dev1", "phase": "development", "condition": "T2", "stage": "designer"},
            {"id": "dev2", "phase": "validation", "condition": "T2", "stage": "D"},
            {"id": "test", "phase": "test", "condition": "T2", "stage": "D"},
            {"id": "full", "phase": "test", "condition": "FULL-JOURNAL", "stage": "D"},
        ]
        events = [e for i, job in enumerate(jobs, 1) for e in
                  [start(i, job["id"]), response(i, job["id"], {"input_tokens": 5, "output_tokens": 1})]]
        outcomes = {j["id"]: {"status": "failed_controller", "audit": {"pass": False}, "score": None} for j in jobs}
        with tempfile.TemporaryDirectory() as tmp:
            report = resource_report(Path(tmp), {"schedule": jobs, "fixture": True}, outcomes, events)
        self.assertEqual(report["scenarios"]["T2"]["costs"]["input_tokens"]["setup"], measure(10))
        self.assertEqual(report["scenarios"]["FULL-JOURNAL"]["actual_contexts"], 1)
        self.assertEqual(report["scenarios"]["T2"]["results_per_use"]["identified_new"], 0)
        self.assertFalse(report["model_efficiency_claim_permitted"])


if __name__ == "__main__":
    unittest.main()
