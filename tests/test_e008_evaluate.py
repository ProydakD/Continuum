import unittest

from research.e008_evaluate import ReadOnlyDecisions, chain, control_report
from research.e008_locks import validate_assignment


def row(identity, phase="test", status="completed", control=None, replicate=1):
    return {"job": {"id": identity, "stage": "D", "world": "w", "condition": "T1",
                    "phase": phase, "replicate": replicate, "lineage": None, "control": control},
            "status": status, "audit": {"pass": status == "completed"},
            "score": {"new_target_correct": 8, "new_total": 10}}


class EvaluationTests(unittest.TestCase):
    def test_controls_average_repetitions_inside_world(self):
        main = [row("main1"), row("main2", replicate=2)]
        controls = [row("crash1", "robustness", "failed_controller", "crash"),
                    row("crash2", "robustness", control="crash", replicate=2)]
        result = control_report(main + controls, [{"id": "w", "truth": {"family": "relay"}}], draws=100)
        cell = result["T1|crash"]["paired_control_minus_main"]
        self.assertEqual(cell["eligible_worlds"], 1)
        self.assertEqual(cell["mean"], -.4)

    def test_missing_secondary_is_not_claimed_as_cross_model_failure(self):
        rows = [row("main"), row("cross", "robustness", "secondary_unavailable", "cross_model")]
        result = control_report(rows, [{"id": "w", "truth": {"family": "relay"}}], draws=100)["T1|cross_model"]
        self.assertEqual(result["unavailable_secondary"], 1)
        self.assertIsNone(result["paired_control_minus_main"]["mean"])
        self.assertEqual(result["assigned_contexts"], 1)

    def test_control_requires_unique_registered_comparator(self):
        worlds = [{"id": "w", "truth": {"family": "relay"}}]
        with self.assertRaises(ValueError):
            control_report([row("control", "robustness", control="crash")], worlds, draws=100)
        with self.assertRaises(ValueError):
            control_report([row("a"), row("b")], worlds, draws=100)

    def test_unverified_predecessor_is_not_a_belief_observation(self):
        predecessor = {"job": {"id": "a", "stage": "A", "source": None},
                       "audit": {"pass": False}, "result": {"answer": {"untrusted": True}}}
        self.assertEqual(chain({"id": "b", "source": "a"}, {"a": predecessor})[0]["result"], {})
        predecessor["job"]["source"] = "b"
        with self.assertRaises(PermissionError):
            chain({"id": "b", "source": "a"}, {"a": predecessor})

    def test_cached_assignment_still_rejects_foreign_fixed_protocol(self):
        job = {"id": "a", "phase": "validation", "protocol_version": "L1-v2"}
        with self.assertRaises(PermissionError):
            validate_assignment(job, {"job": dict(job, protocol_version="L2-v2")})
        with self.assertRaises(PermissionError):
            validate_assignment(job, {"job": dict(job, hidden_prompt="answer")})

    def test_read_only_evaluator_cannot_create_missing_lock(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            store = object.__new__(ReadOnlyDecisions)
            store.study, store.binding = Path(tmp), {}
            with self.assertRaises(FileNotFoundError):
                store._seal("protocol", {}, {})
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
