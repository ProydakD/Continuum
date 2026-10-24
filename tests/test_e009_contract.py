"""Public-contract identifiability and exact historical protocol compatibility."""
from copy import deepcopy
import hashlib
import json
import re
import unittest

from research.e009_episode import episode_corpus, make_episode
from research.e009_episode_eval import assess_snapshot, reference_chain
from research.e009_oracle import Oracle
from research.e009_protocol import assigned_seed, instructions_for, output_items, public_input, tools_for
from research.e009_revision import sha
from research.e009_replay import reconcile_final
from research.e009_scm import models
from research.e009_sources import EvidenceRegistry, evidence_catalog


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.episode = make_episode(321, "public-contract-regression")
        cls.oracle = Oracle(models())

    def test_original_instruction_bytes_remain_exact(self):
        expected = {1: "74c6360121f0a22b15faf473c82d0e2c2862be641079fe11be50afad667668f9",
                    2: "d4f225f985638f94adfd7cb5db385d7db935e9d2210d94ea447c13a9fcc79393"}
        for version, digest in expected.items():
            self.assertEqual(hashlib.sha256(instructions_for(version).encode()).hexdigest(), digest)
        self.assertNotEqual(instructions_for(2), instructions_for(3))

    def test_demonstrated_collision_is_legacy_only_and_not_silently_normalized(self):
        altered = deepcopy(self.episode)
        for claim in altered["claims"]:
            claim["reasons"] = []
        for version in (1, 2):
            self.assertEqual(assigned_seed(self.episode, "F1", "controlled", "A", version),
                             assigned_seed(altered, "F1", "controlled", "A", version))
        self.assertTrue(all(sha(a) != sha(b) for a, b in zip(self.episode["claims"], altered["claims"])))
        for condition in ("F0", "F1", "S0", "S1", "FULL-JOURNAL"):
            with self.subTest(condition=condition), self.assertRaisesRegex(ValueError, "six-field"):
                assigned_seed(altered, condition, "controlled", "A", 3)
        self.assertEqual(altered["claims"][0]["reasons"], [])
        self.assertIsNone(assigned_seed(altered, "F1", "natural", "A", 3))
        self.assertIsNone(assigned_seed(altered, "C0", "controlled", "A", 3))

    def test_missing_or_extra_initial_keys_rejected_equally_in_f_and_s(self):
        variants = []
        for key in self.episode["claims"][0]:
            changed = deepcopy(self.episode)
            del changed["claims"][0][key]
            variants.append(changed)
        changed = deepcopy(self.episode)
        changed["claims"][0]["previous_sha256"] = None
        variants.append(changed)
        for changed in variants:
            for condition in ("F0", "S0"):
                with self.assertRaisesRegex(ValueError, "six-field"):
                    assigned_seed(changed, condition, "controlled", "A", 3)

    def test_registered_initial_prose_reconstructs_exact_objects_without_private_lookup(self):
        pattern = re.compile(r"^(\S+) version ([0-9]+), origin ([^:]+): (\{.*\}); status (\w+); "
                             r"alternative justifications (\[.*\])\.$")
        for episode in [*episode_corpus()["episodes"], self.episode]:
            text = assigned_seed(episode, "F0", "controlled", "A", 3)["payload"]
            recovered = []
            for line in text.splitlines()[1:]:
                match = pattern.fullmatch(line)
                self.assertIsNotNone(match)
                cid, version, origin, proposition, status, bases = match.groups()
                recovered.append({"id": cid, "version": int(version), "origin": origin,
                                  "proposition": json.loads(proposition), "status": status,
                                  "bases": json.loads(bases)})
            structured = assigned_seed(episode, "S0", "controlled", "A", 3)["payload"]
            self.assertEqual(recovered, structured)
            self.assertEqual([sha(c) for c in recovered], [sha(c) for c in episode["claims"]])
            self.assertEqual(assigned_seed(episode, "F0", "controlled", "A", 3),
                             assigned_seed(episode, "F0", "controlled", "A", 2))

    def test_public_projection_tools_and_seed_do_not_gain_private_information(self):
        registry = EvidenceRegistry(evidence_catalog(self.episode), sha(evidence_catalog(self.episode)))
        altered = deepcopy(self.episode)
        altered.update(hidden_model=999, design_audit={"secret": "NOT-PUBLIC"}, private_gold="NOT-PUBLIC")
        for condition in ("F0", "F1", "S0", "S1", "C0", "FULL-JOURNAL"):
            for stage in "ABCDE":
                self.assertEqual(public_input(self.episode, registry, stage, condition, "controlled"),
                                 public_input(altered, registry, stage, condition, "controlled"))
                self.assertEqual(assigned_seed(self.episode, condition, "controlled", stage, 3),
                                 assigned_seed(altered, condition, "controlled", stage, 3))
            self.assertNotIn("get_object", {t["name"] for t in tools_for("A", condition)})

    def test_old_evaluator_keeps_uncertainty_and_unchanged_reason_requirements(self):
        trace = reference_chain(self.episode, self.oracle)
        previous = self.episode["claims"]
        for record in trace[:-1]:
            current = record["claims"]
            self.assertTrue(all(assess_snapshot(self.episode, record["stage"], previous, current,
                                                self.oracle)["gates"].values()))
            empty = deepcopy(current)
            next(c for c in empty if c["id"] == "I")["reasons"] = []
            self.assertFalse(assess_snapshot(self.episode, record["stage"], previous, empty,
                                             self.oracle)["gates"]["P"])
            if record["stage"] in "AC":
                empty = deepcopy(current)
                next(c for c in empty if c["status"] == "undetermined")["bases"] = []
                self.assertFalse(assess_snapshot(self.episode, record["stage"], previous, empty,
                                                 self.oracle)["gates"]["D"])
            previous = current

    def test_protocol_three_retains_batch_validation(self):
        call = {"type": "function_call", "call_id": "one", "name": "read_memory", "arguments": "{}"}
        for output in ([call, call], [{**call, "arguments": "[]"}], [{**call, "arguments": "{\"x\":NaN}"}]):
            with self.assertRaises(ValueError):
                output_items({"status": "completed", "output": output}, 3)
        second = {**call, "call_id": "two"}
        self.assertEqual(output_items({"status": "completed", "output": [call, second]}, 3), [call, second])

    def test_authentic_rejected_final_is_not_success_or_missing_evidence(self):
        terminal = {"status": "failed", "failure_type": "ValueError"}
        error = {"status": "error", "reason": "Publication failed"}
        self.assertFalse(reconcile_final(terminal, error, "A", 1, False))
        self.assertFalse(reconcile_final(terminal, {"status": "published"}, "A", 1, False))
        self.assertFalse(reconcile_final(terminal, error, "E", 1, False))
        self.assertFalse(reconcile_final(terminal, {"answer": 1, "basis": []}, "E", 0, False))

    def test_missing_accepted_final_or_forged_terminal_still_rejected(self):
        final = {"status": "published"}
        terminal = {"status": "failed", "failure_type": "ValueError"}
        for record, observed, stage, published in [
                (terminal, final, "A", True),
                (terminal, {"answer": 1, "basis": []}, "E", False),
                ({"status": "completed"}, final, "A", False),
                ({**terminal, "failure_type": "TimeoutError"}, final, "A", False),
                ({**terminal, "final": final}, {"status": "error"}, "A", False)]:
            with self.assertRaisesRegex(ValueError, "terminal answer differs"):
                reconcile_final(record, observed, stage, 1, published)
        self.assertTrue(reconcile_final({"status": "completed", "final": final}, final, "A", 1, True))


if __name__ == "__main__":
    unittest.main()
