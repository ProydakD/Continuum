"""Full revision opportunities, not an equivalent edge/path toy chain."""
from copy import deepcopy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from research.e009_episode import active_evidence, episode_corpus, make_episode, truth_set
from research.e009_episode_eval import (natural_opportunities, reference_chain, reference_snapshot,
                                       score_chain, score_natural_chain)
from research.e009_oracle import Oracle
from research.e009_raw import file_hash, record_fixture, replay
from research.e009_revision import canonical, sha
from research.e009_scm import models, quantity
from research.e009_sources import EvidenceRegistry, evidence_catalog, episode_input, verifier_notices


class EpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = Oracle(models())
        cls.corpus = episode_corpus()

    def setUp(self):
        self.episode = self.corpus["episodes"][0]
        self.trace = reference_chain(self.episode, self.oracle)

    def score(self):
        return score_chain(self.episode, self.trace, self.oracle)

    def test_strict_multilevel_implications(self):
        oracle = Oracle(models())
        episode = make_episode(344, "regression-deep")
        claims = {c["id"]: c for c in episode["claims"]}
        sets = [truth_set(oracle, claims[cid]["proposition"]) for cid in ("H", "D1", "D2", "D3")]
        self.assertTrue(all(left < right for left, right in zip(sets, sets[1:])))

    def test_all_graphs_have_strict_and_joint_necessity(self):
        for episode in self.corpus["episodes"]:
            claims = {c["id"]: c for c in episode["claims"]}
            sets = {cid: truth_set(self.oracle, c["proposition"]) for cid, c in claims.items()}
            self.assertTrue(sets["H"] < sets["D1"] < sets["D2"] < sets["D3"])
            self.assertTrue(sets["D1"] & sets["J"])
            self.assertTrue(sets["D1"] & sets["J"] <= sets["D4"])
            self.assertFalse(sets["D1"] <= sets["D4"])
            self.assertFalse(sets["J"] <= sets["D4"])

    def test_census_predicate_independent_implementations(self):
        predicate = next(c["proposition"] for c in self.episode["claims"] if c["id"] == "J")
        for i in range(len(models())):
            self.assertEqual(quantity(i, predicate["query"]), self.oracle.quantity(i, predicate["query"]))

    def test_repeated_revision_relative_to_current_evidence(self):
        for episode in self.corpus["episodes"]:
            p = episode["claims"][0]["proposition"]
            statuses = [self.oracle.status(self.oracle.compatible(active_evidence(episode, s)), p) for s in "ABCDE"]
            self.assertEqual(statuses, ["undetermined", "refuted", "undetermined", "refuted", "refuted"])
            self.assertNotIn("EB", {r["id"] for r in active_evidence(episode, "C")})

    def test_all_reference_chains_pass(self):
        for episode in self.corpus["episodes"]:
            self.assertEqual(score_chain(episode, reference_chain(episode, self.oracle), self.oracle)["bri"], 1)

    def test_answer_only_not_revision(self):
        self.trace[1]["claims"][0]["status"] = "supported"
        self.assertTrue(self.score()["new_answer_correct"])
        self.assertEqual(self.score()["bri"], 0)

    def test_final_correct_state_does_not_erase_bad_earlier_revision(self):
        self.trace[1]["claims"][2]["status"] = "supported"
        self.assertEqual(self.score()["bri"], 0)

    def test_stale_sources_after_revocation_fail(self):
        self.trace[2]["claims"][0]["bases"] = [["e:EB", "e:EC"]]
        self.assertFalse(self.score()["gates"]["P"])

    def test_withdrawal_reason_must_identify_changed_sources(self):
        self.trace[2]["claims"][0]["reasons"] = ["EA"]
        self.assertFalse(self.score()["gates"]["P"])

    def test_future_source_reason_fails(self):
        self.trace[1]["claims"][0]["reasons"] = ["EE"]
        self.assertFalse(self.score()["gates"]["P"])

    def test_overretraction_of_still_true_descendant_fails(self):
        episode = make_episode(43, "preservation")
        trace = reference_chain(episode, self.oracle)
        d3 = next(c for c in trace[1]["claims"] if c["id"] == "D3")
        self.assertEqual(d3["status"], "supported")
        d3["status"] = "refuted"
        result = score_chain(episode, trace, self.oracle)
        self.assertFalse(result["gates"]["N"])

    def test_refuted_to_uncertain_does_not_mean_supported(self):
        self.trace[2]["claims"][0]["status"] = "supported"
        self.assertFalse(self.score()["gates"]["R"])

    def test_dependent_skip_and_timeout_count_zero(self):
        for status in ("dependent_skip", "timeout", "failed"):
            self.trace[2]["terminal_status"] = status
            self.assertEqual(self.score()["bri"], 0)
            self.assertFalse(self.score()["technical_complete"])

    def test_lost_or_over_budget_memory_cannot_count_complete(self):
        for memory in (None, {"format": "S", "payload": []}, {"format": "S", "payload": ["x" * 9000]}):
            self.trace[1]["published_memory"] = memory
            self.assertEqual(self.score()["bri"], 0)
            self.assertIn("B", self.score()["memory_publication_failures"])

    def test_wrong_factorial_memory_format_rejected(self):
        self.assertEqual(score_chain(self.episode, self.trace, self.oracle, "F1")["bri"], 0)

    def test_fresh_instances_required(self):
        self.trace[3]["instance_id"] = self.trace[2]["instance_id"]
        self.assertFalse(self.score()["technical_complete"])

    def test_stage_missing_or_reordered_fails(self):
        self.assertEqual(score_chain(self.episode, self.trace[:-1], self.oracle)["bri"], 0)
        self.trace[1], self.trace[2] = self.trace[2], self.trace[1]
        self.assertEqual(self.score()["bri"], 0)

    def test_claim_redefinition_rejected(self):
        self.trace[3]["claims"][0]["proposition"]["value"] = 0
        self.assertFalse(self.score()["gates"]["P"])

    def test_new_correct_answer_needs_admissible_basis(self):
        self.trace[-1]["basis"] = ["c:H"]
        self.assertFalse(self.score()["gates"]["Q"])
        self.trace[-1]["basis"] = ["e:EB"]
        self.assertFalse(self.score()["gates"]["Q"])

    def test_missing_new_answer_is_not_null_answer(self):
        self.trace[-1].pop("answer")
        self.assertFalse(self.score()["gates"]["Q"])

    def test_c0_has_no_bri_denominator(self):
        self.assertIsNone(score_chain(self.episode, self.trace, self.oracle, "C0")["bri"])

    def test_natural_no_roots_is_not_success(self):
        result = natural_opportunities([], [], active_evidence(self.episode, "A"), active_evidence(self.episode, "B"), self.oracle)
        self.assertEqual(result["opportunities"], 0)
        self.assertIsNone(result["revision_rate"])

    def test_natural_no_new_information_does_not_invent_revision(self):
        old = deepcopy(self.trace[0]["claims"])
        old[0]["status"] = "supported"
        evidence = active_evidence(self.episode, "A")
        result = natural_opportunities(old, self.trace[0]["claims"], evidence, evidence, self.oracle)
        self.assertEqual(result["opportunities"], 0)
        self.assertIsNone(result["revision_rate"])

    def test_natural_observed_graph_kept_separate(self):
        old = deepcopy(self.trace[0]["claims"])
        # A natural writer may explicitly preserve graph links even when the asserted premise is uncertain.
        old[1]["bases"] = [["c:H"]]
        old[2]["bases"] = [["c:D1"]]
        new = deepcopy(self.trace[1]["claims"])
        result = natural_opportunities(old, new, active_evidence(self.episode, "A"), active_evidence(self.episode, "B"), self.oracle)
        self.assertGreater(result["opportunities"], 0)
        self.assertEqual(result["revision_rate"], 1)
        self.assertNotIn("bri", result)

    def test_natural_full_chain_not_controlled_primary(self):
        result = score_natural_chain(self.episode, self.trace, self.oracle)
        self.assertIsNone(result["bri"])
        self.assertIsNone(result["revision_rate"])
        self.assertEqual(result["opportunities"], 0)  # Reference rewrites proofs, has no inherited c: graph.


class EvidenceAndRawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = Oracle(models())
        cls.episode = make_episode(43, "raw-fixture")

    def setUp(self):
        self.catalog = evidence_catalog(self.episode)
        self.registry = EvidenceRegistry(self.catalog, sha(self.catalog))

    def test_revoked_counts_remain_archived_not_admissible(self):
        view = self.registry.view("C", full_journal=True)
        self.assertEqual({r["id"] for r in view["source_archive"]}, {"EA", "EB", "EC"})
        self.assertEqual({r["id"] for r in self.registry.active_sources("C")}, {"EA"})

    def test_future_metadata_and_hash_are_not_public(self):
        a = self.registry.view("A")
        self.assertEqual([m["id"] for m in a["source_metadata"]], ["EA"])
        self.assertNotIn(sha(self.catalog), canonical(a).decode())
        self.assertNotIn("ED", canonical(a).decode())

    def test_catalog_forgery_and_duplicate_identity_rejected(self):
        expected = sha(self.catalog)
        self.catalog["records"][0]["counts"][0] += 1
        with self.assertRaises(ValueError):
            EvidenceRegistry(self.catalog, expected)
        self.catalog = evidence_catalog(self.episode)
        self.catalog["records"].append(self.catalog["records"][0])
        with self.assertRaises(ValueError):
            EvidenceRegistry(self.catalog, sha(self.catalog))

    def test_reusing_revoked_source_id_is_not_reissue(self):
        self.catalog["updates"][3]["add"] = ["EB"]
        with self.assertRaises(ValueError):
            EvidenceRegistry(self.catalog, sha(self.catalog))

    def test_verification_cannot_read_future_source(self):
        candidate = next(r for r in self.catalog["records"] if r["id"] == "ED")
        self.assertFalse(self.registry.verify_source(candidate, "A"))
        self.assertTrue(self.registry.verify_source(candidate, "D"))
        candidate["counts"][0] += 1
        self.assertFalse(self.registry.verify_source(candidate, "D"))

    def test_registry_returns_detached_copies(self):
        view = self.registry.view("A")
        view["new_sources"][0]["counts"][0] += 1
        self.assertNotEqual(view, self.registry.view("A"))

    def test_factorial_information_identical(self):
        for a, b in (("F0", "F1"), ("S0", "S1")):
            for stage in "ABCDE":
                first = episode_input(self.episode, self.registry, stage, a, "published")
                second = episode_input(self.episode, self.registry, stage, b, "published")
                first.pop("condition"); second.pop("condition")
                self.assertEqual(first, second)

    def test_no_gold_measurement_future_question_in_projection(self):
        episode = deepcopy(self.episode)
        episode.update(gold="PRIVATE-GOLD", measurement="PRIVATE-MEASUREMENT")
        for stage in "ABCDE":
            value = episode_input(episode, self.registry, stage, "F1", "explicit-memory")
            self.assertNotIn("PRIVATE", canonical(value).decode())
            self.assertNotIn("hidden_model", value)
            self.assertNotIn("design_audit", value)
            self.assertEqual("question" in value, stage == "E")

    def test_natural_a_not_seeded_with_controlled_history(self):
        value = episode_input(self.episode, self.registry, "A", "F1", None, "natural")
        self.assertIsNone(value["memory"])
        self.assertNotIn("claims", value)

    def test_v1_has_no_private_predecessor_measurement(self):
        self.assertEqual(set(inspect.signature(verifier_notices).parameters), {"claims", "view", "changed_claims"})
        claims = reference_chain(self.episode, self.oracle)[1]["claims"]
        before = sha(claims)
        notices = verifier_notices(claims, self.registry.view("C"), ["H"])
        self.assertTrue(any(n["kind"] == "missing_source" for n in notices))
        self.assertEqual(before, sha(claims))

    def test_raw_replay_is_read_only_and_not_a_model_result(self):
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / "run"
            bound = record_fixture(run, self.episode, reference_chain(self.episode, self.oracle))
            result = replay(run, bound["manifest_sha256"], self.oracle)
            self.assertEqual(result["score"]["bri"], 1)
            self.assertTrue(result["raw_unchanged"])
            self.assertFalse(result["binding"]["live"])
            self.assertIsNone(result["api_usage"])

    def test_measurement_channel_not_hidden_f_memory(self):
        with tempfile.TemporaryDirectory() as root:
            trace = reference_chain(self.episode, self.oracle, "F")
            trace[0]["private_measurement_canary"] = "NEVER-HANDOFF"
            run = Path(root) / "run"
            bound = record_fixture(run, self.episode, trace, "F1")
            public = (run / "public/B.json").read_text()
            self.assertNotIn("NEVER-HANDOFF", public)
            self.assertEqual(json.loads(public)["memory"], trace[0]["published_memory"])
            self.assertEqual(replay(run, bound["manifest_sha256"], self.oracle)["score"]["bri"], 1)

    def test_raw_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / "run"
            trace = reference_chain(self.episode, self.oracle)
            record_fixture(run, self.episode, trace)
            with self.assertRaises(FileExistsError):
                record_fixture(run, self.episode, trace)

    def test_raw_tampering_and_extra_file_rejected(self):
        for mode in ("mutate", "extra", "manifest"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                run = Path(root) / "run"
                bound = record_fixture(run, self.episode, reference_chain(self.episode, self.oracle))
                target = run / {"mutate": "raw/C.json", "extra": "raw/extra.json", "manifest": "MANIFEST.json"}[mode]
                target.write_text("{}\n")
                with self.assertRaises(ValueError):
                    replay(run, bound["manifest_sha256"], self.oracle)

    def test_rehashed_hidden_memory_still_breaks_dataflow_binding(self):
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / "run"
            record_fixture(run, self.episode, reference_chain(self.episode, self.oracle, "F"), "F1")
            public_path = run / "public/B.json"
            public = json.loads(public_path.read_text())
            public["memory"] = {"format": "F", "payload": "hidden replacement"}
            public_path.write_bytes(canonical(public) + b"\n")
            # Rebind content hash to exercise semantic dataflow check, not just byte hash rejection.
            event_path = run / "raw/B.json"
            event = json.loads(event_path.read_text())
            event["public_input_sha256"] = sha(public)
            event_path.write_bytes(canonical(event) + b"\n")
            manifest = {p.relative_to(run).as_posix(): file_hash(p) for p in run.rglob("*")
                        if p.is_file() and p.name != "MANIFEST.json"}
            (run / "MANIFEST.json").write_bytes(canonical(manifest) + b"\n")
            with self.assertRaises(ValueError):
                replay(run, file_hash(run / "MANIFEST.json"), self.oracle)


if __name__ == "__main__":
    unittest.main()
