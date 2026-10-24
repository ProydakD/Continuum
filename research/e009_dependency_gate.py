"""Source-bound offline audit of full episodes, negative outcomes and raw replay."""
import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

from .common import PROJECT
from .e009_episode import active_evidence, episode_corpus, truth_set
from .e009_episode_eval import reference_chain, score_chain
from .e009_oracle import Oracle
from .e009_raw import file_hash, record_fixture, replay, write_once
from .e009_scm import models


def negative_traces(trace):
    mutations = {}
    wrong_root = deepcopy(trace); wrong_root[1]["claims"][0]["status"] = "supported"
    mutations["root_not_revised"] = wrong_root
    stale = deepcopy(trace); stale[2]["claims"][0]["bases"] = [["e:EB", "e:EC"]]
    mutations["revoked_source_reused"] = stale
    over = deepcopy(trace); next(c for c in over[1]["claims"] if c["id"] == "K")["status"] = "refuted"
    mutations["independent_false_retraction"] = over
    reason = deepcopy(trace); reason[0]["claims"][0]["reasons"] = ["EE"]
    mutations["future_source"] = reason
    origin = deepcopy(trace); origin[1]["claims"][0]["origin"] = "rewritten-origin"
    mutations["history_origin_changed"] = origin
    final = deepcopy(trace); final[-1]["basis"] = ["c:H"]
    mutations["correct_answer_stale_basis"] = final
    lost = deepcopy(trace); lost[1]["published_memory"] = None
    mutations["memory_lost"] = lost
    skip = deepcopy(trace); skip[2]["terminal_status"] = "dependent_skip"
    mutations["dependent_skip"] = skip
    reused = deepcopy(trace); reused[3]["instance_id"] = reused[2]["instance_id"]
    mutations["instance_reused"] = reused
    definitions = deepcopy(trace); definitions[1]["claims"][0]["proposition"]["value"] = 0
    mutations["claim_redefined"] = definitions
    return mutations


def execute(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    sources = sorted(PROJECT.glob("research/e009_*.py")) + sorted(PROJECT.glob("tests/test_e009*.py"))
    hashes = {}
    for path in sources:
        relative = path.relative_to(PROJECT)
        destination = output / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
        hashes[relative.as_posix()] = file_hash(path)
    write_once(output / "PROVENANCE.json", {
        "source_hashes": hashes, "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "working_tree": subprocess.check_output(["git", "status", "--short"], cwd=PROJECT, text=True),
        "python": sys.version, "mcp_version": importlib.metadata.version("mcp"),
        "host_model": "not_exposed", "experimental_model": "deterministic-reference-fixture",
        "argv": sys.argv, "scope": "offline code and data audit, not empirical model outcomes"})
    corpus = episode_corpus()
    write_once(output / "CORPUS.json", corpus)
    oracle = Oracle(models())
    results, graph_checks = [], []
    for episode in corpus["episodes"]:
        claims = {c["id"]: c for c in episode["claims"]}
        truth = {cid: truth_set(oracle, c["proposition"]) for cid, c in claims.items()}
        assert truth["H"] < truth["D1"] < truth["D2"] < truth["D3"]
        assert truth["D1"] & truth["J"] <= truth["D4"]
        assert not truth["D1"] <= truth["D4"] and not truth["J"] <= truth["D4"]
        statuses = [oracle.status(oracle.compatible(active_evidence(episode, s)), claims["H"]["proposition"]) for s in "ABCDE"]
        assert statuses == ["undetermined", "refuted", "undetermined", "refuted", "refuted"]
        graph_checks.append({"world": episode["id"], "strict_sizes": [len(truth[c]) for c in ("H", "D1", "D2", "D3")],
                             "AND_premises_necessary": True, "root_statuses": statuses,
                             "D3_at_B": oracle.status(oracle.compatible(active_evidence(episode, "B")), claims["D3"]["proposition"])})
        for condition in ("F0", "F1", "S0", "S1", "FULL-JOURNAL", "C0"):
            trace = reference_chain(episode, oracle, "S" if condition.startswith("S") else "F")
            run = output / "cases" / episode["id"] / condition
            bound = record_fixture(run, episode, trace, condition)
            result = replay(run, bound["manifest_sha256"], oracle)
            assert result["score"]["bri"] == (None if condition == "C0" else 1)
            results.append({"world": episode["id"], "case": condition, **bound, **result})
        reference = reference_chain(episode, oracle)
        for label, trace in negative_traces(reference).items():
            run = output / "cases" / episode["id"] / label
            bound = record_fixture(run, episode, trace)
            result = replay(run, bound["manifest_sha256"], oracle)
            assert result["score"]["bri"] == 0, (episode["id"], label)
            results.append({"world": episode["id"], "case": label, **bound, **result})
        # This reference has no c: dependencies after its first update: natural 0/0 must stay undefined.
        run = output / "cases" / episode["id"] / "natural-no-observed-dependencies"
        bound = record_fixture(run, episode, reference, "S1", "natural")
        result = replay(run, bound["manifest_sha256"], oracle)
        assert result["score"]["opportunities"] == 0 and result["score"]["revision_rate"] is None
        results.append({"world": episode["id"], "case": "natural-no-observed-dependencies", **bound, **result})
    write_once(output / "GRAPH-AUDIT.json", graph_checks)
    write_once(output / "RAW-REPLAY.json", results)
    assert all(file_hash(PROJECT / name) == digest for name, digest in hashes.items())
    summary = {"pass": True, "scope": "offline full-chain kernel; not model validation or final study",
               "worlds": len(corpus["episodes"]), "cases": len(results),
               "positive_controlled_cases": 60, "negative_controlled_cases": 120,
               "C0_BRI_not_applicable": 12, "natural_zero_denominators_preserved": 12,
               "raw_files_read_only_verified": sum(r["raw_files_verified"] for r in results),
               "non_equivalent_depth": 3, "AND_premises_necessary": True,
               "D3_preservation_worlds": sum(g["D3_at_B"] == "supported" for g in graph_checks),
               "new_model_requests": 0, "heldout_created": False,
               "elapsed_seconds": time.monotonic() - started,
               "remaining": ["sandboxed MCP worker and authentic execution provenance",
                             "complete serialized MCP read budget and raw transport accounting",
                             "live provider/controller retry/STOP/terminal-outcome binding",
                             "natural selective-retraction/provenance guardrails and final analysis",
                             "T2 two-line development, updated full-episode power and calibration",
                             "final preregistration, model series, independent scientific report"]}
    write_once(output / "SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    execute(args.output)
