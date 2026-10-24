"""Private synthetic guardrail controls; never a model result or live natural input seed."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from .e009_episode import episode_corpus, make_episode
from .e009_episode_eval import reference_chain, reference_snapshot
from .e009_oracle import Oracle
from .e009_raw import record_fixture, replay, write_once
from .e009_revision import canonical, memory_envelope
from .e009_scm import models


def natural_fixture(episode, oracle, representation="S"):
    trace = reference_chain(episode, oracle, representation)
    previous = deepcopy(episode["claims"])
    for claim in previous:
        claim.update(origin="synthetic-natural-A", reasons=["EA"])
    for index, stage in enumerate("ABCD"):
        current = previous if stage == "A" else reference_snapshot(episode, stage, previous, oracle)
        for claim in current:
            claim["origin"] = "synthetic-natural-A"
        trace[index]["claims"] = current
        trace[index]["published_memory"] = memory_envelope(
            deepcopy(current) if representation == "S" else canonical(current).decode(), representation)
        previous = current
    return trace


def mutate(trace, mode):
    trace = deepcopy(trace)
    target = trace[1]["claims"][0]
    if mode == "hash": target["previous_sha256"] = "0" * 64
    elif mode == "version": target["version"] += 1
    elif mode == "origin": target["origin"] = "forged-author"
    elif mode == "reason": target["reasons"] = ["FUTURE"]
    elif mode == "delete-root": trace[1]["claims"].pop(0)
    elif mode == "missing-current": trace[1]["claims"] = None
    elif mode == "delete-supported": trace[1]["claims"] = [c for c in trace[1]["claims"] if c["id"] != "I"]
    elif mode == "downgrade-supported":
        next(c for c in trace[1]["claims"] if c["id"] == "I")["status"] = "undetermined"
    elif mode == "stale-later": trace[2]["claims"][0]["bases"] = [["e:EB", "e:EC"]]
    elif mode == "failed": trace[1]["terminal_status"] = "failed"
    elif mode == "missing-publication": trace[1]["published_memory"] = None
    elif mode == "false-answer-basis": trace[4]["basis"] = ["e:EB"]
    elif mode != "positive": raise ValueError("unknown mutation")
    return trace


def run(directory, image=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    oracle = Oracle(models())
    results = []
    modes = ["positive", "hash", "version", "origin", "reason", "delete-root", "missing-current",
             "delete-supported", "downgrade-supported", "stale-later", "failed", "missing-publication", "false-answer-basis"]
    for episode in episode_corpus()["episodes"]:
        for mode in modes:
            trace = mutate(natural_fixture(episode, oracle), mode)
            bound = record_fixture(directory / (episode["id"] + "-" + mode), episode, trace, "S1", "natural")
            evaluated = replay(bound["directory"], bound["manifest_sha256"], oracle)
            score = evaluated["score"]
            assert score["post_update_integrity"] == (mode == "positive"), (mode, score)
            expected_rate = None if mode == "missing-current" else 1 if mode in {
                "positive", "stale-later", "false-answer-basis"} else 0
            assert score["revision_rate"] == expected_rate, (mode, score)
            assert score["transitions"][0]["opportunities"] == 1
            if mode in {"delete-supported", "downgrade-supported"}:
                assert score["transitions"][0]["false_retractions"] >= 1
            results.append({**bound, "mode": mode, "revision_rate": score["revision_rate"],
                            "post_update_integrity": score["post_update_integrity"],
                            "raw_files_verified": evaluated["raw_files_verified"]})
    write_once(directory / "OFFLINE-RESULTS.json", results)
    live_fixtures = []
    if image:
        from .e009_controller_gate import ScriptedProvider
        from .e009_execute import run_chain
        from .e009_replay import replay as replay_controller
        episode = make_episode(43, "natural-controller-dev-43")
        for condition, mode in [("F1", "positive"), ("S1", "hash"), ("C0", "positive")]:
            trace = mutate(natural_fixture(episode, oracle, "S" if condition.startswith("S") else "F"), mode)
            observed = run_chain(directory / (condition.lower() + "-" + mode), episode,
                                 condition, "natural", ScriptedProvider(trace), image)
            evaluated = replay_controller(observed["directory"], observed["manifest_sha256"], oracle)
            write_once(directory / (condition.lower() + "-replay.json"), evaluated)
            score = evaluated["score"]
            assert score["revision_rate"] == (None if condition == "C0" else int(mode == "positive"))
            assert score["technical_complete"]
            live_fixtures.append({**observed, "revision_rate": score["revision_rate"],
                                  "raw_files_verified": evaluated["raw_files_verified"]})
    summary = {"pass": True, "offline_cases": len(results), "offline_raw_files": sum(r["raw_files_verified"] for r in results),
               "controller_cases": live_fixtures, "model_api_calls": 0,
               "scope": "Synthetic fixtures exercise evaluator/controller; not natural model formation or research success"}
    write_once(directory / "SUMMARY.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--image")
    args = parser.parse_args()
    run(args.output, args.image)
