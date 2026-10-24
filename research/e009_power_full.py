"""Versioned full-episode power assumptions, never estimates of unseen model performance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

from .e009_raw import write_once
from .e009_statistics import analyze_worlds

SCENARIOS = {
    "null": {"stage_gain": 0.0, "structured_gain": 0.0, "failure": .003, "loss_v0": .001, "loss_v1": .001},
    "safe-small": {"stage_gain": .035, "structured_gain": .01, "failure": .003, "loss_v0": .001, "loss_v1": .001},
    "safe-strong": {"stage_gain": .07, "structured_gain": .01, "failure": .003, "loss_v0": .001, "loss_v1": .001},
    "unsafe-v1": {"stage_gain": .14, "structured_gain": .01, "failure": .003, "loss_v0": .001, "loss_v1": .03},
    "high-failure": {"stage_gain": .07, "structured_gain": .01, "failure": .03, "loss_v0": .001, "loss_v1": .001},
}


def derived_seed(*values):
    raw = json.dumps(values, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def simulate_worlds(n, scenario, seed, *, feasible=None):
    if n < 2 or scenario not in SCENARIOS:
        raise ValueError("invalid planning cell")
    config, rng = SCENARIOS[scenario], random.Random(seed)
    # Feasibility audit gives these two patterns, 288 parameterizations each.
    population = feasible if feasible is not None else [
        {"model_index": i, "supported_slots": [3, 5, 3, 5] if i < 288 else [3, 3, 3, 3]} for i in range(576)]
    if n > len(population):
        raise ValueError("sample exceeds finite available world population")
    selected = rng.sample(population, n)
    worlds, technical_failures, skipped, false_losses = [], [0] * 4, [0] * 4, [0] * 4
    for assigned in selected:
        difficulty = rng.betavariate(17.2, 2.8)
        failure = min(.5, config["failure"] * rng.gammavariate(2, .5))
        loss_multiplier = rng.gammavariate(2, .5)
        quality = [difficulty, min(.999, difficulty + config["stage_gain"]),
                   min(.999, difficulty + config["structured_gain"]),
                   min(.999, difficulty + config["stage_gain"] + config["structured_gain"])]
        loss_rate = [min(1, config["loss_v0"] * loss_multiplier), min(1, config["loss_v1"] * loss_multiplier)] * 2
        successes, losses = [0] * 4, [0] * 4
        for _ in range(2):
            alive, integrity = [True] * 4, [True] * 4
            for stage in range(5):
                shared_failure, shared_quality = rng.random(), rng.random()
                for condition in range(4):
                    if not alive[condition]:
                        skipped[condition] += 1
                    elif (shared_failure if rng.random() < .6 else rng.random()) < failure:
                        alive[condition] = False
                        technical_failures[condition] += 1
                    passed = (shared_quality if rng.random() < .6 else rng.random()) < quality[condition]
                    integrity[condition] &= alive[condition] and passed
                if stage < 4:
                    for _ in range(assigned["supported_slots"][stage]):
                        shared_loss = rng.random()
                        for condition in range(4):
                            retracted = (shared_loss if rng.random() < .6 else rng.random()) < loss_rate[condition]
                            losses[condition] += int(not alive[condition] or retracted)
                            false_losses[condition] += int(alive[condition] and retracted)
                            integrity[condition] &= not retracted
            for condition in range(4):
                successes[condition] += int(integrity[condition])
        worlds.append({"id": str(assigned["model_index"]), "successes": successes,
                       "worst_losses": losses, "slots": 2 * sum(assigned["supported_slots"])})
    return worlds, {"technical_failures": technical_failures, "dependent_skips": skipped,
                    "observed_false_losses": false_losses, "assigned_contexts_per_condition": n * 2 * 5}


def binomial_summary(count, total):
    p = count / total
    # Wilson interval remains informative when zero events occur.
    z = 1.959963984540054
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return {"count": count, "simulations": total, "rate": p, "mc_se": math.sqrt(p * (1 - p) / total),
            "mc_wilson_95": [max(0, center - half), min(1, center + half)]}


def cell(n, scenario, repetitions, resamples, seed, backend, feasible):
    if repetitions < 1:
        raise ValueError("positive simulation count required")
    outcomes = []
    for index in range(repetitions):
        worlds, resources = simulate_worlds(n, scenario, derived_seed(seed, n, scenario, index, "worlds"), feasible=feasible)
        result = analyze_worlds(worlds, resamples=resamples, seed=derived_seed(seed, n, scenario, index, "bootstrap"), backend=backend)
        outcomes.append({"index": index, "contrasts": result["contrasts"], "safety": result["safety"],
                         "mean_success": [sum(w["successes"][c] for w in worlds) / (2 * n) for c in range(4)],
                         "mean_worst_loss": [sum(w["worst_losses"][c] / w["slots"] for w in worlds) / n for c in range(4)],
                         "resources": resources})
    summaries = []
    for c, name in enumerate(("F1-F0", "S1-S0", "S1-F1")):
        summaries.append({"name": name,
            "mean_effect": sum(o["contrasts"][c]["estimate"] for o in outcomes) / repetitions,
            **{key: binomial_summary(sum(o["contrasts"][c][key] for o in outcomes), repetitions)
               for key in ("test_pass", "decision_without_guardrail", "decision")}})
    return {"worlds": n, "scenario": scenario, "assumptions": SCENARIOS[scenario], "simulations": repetitions,
            "bootstrap_resamples": resamples, "contrasts": summaries,
            "any_holm_rejection": binomial_summary(sum(any(c["p_holm"] < .05 for c in o["contrasts"]) for o in outcomes), repetitions),
            "safety_pass": [binomial_summary(sum(o["safety"][i]["pass"] for o in outcomes), repetitions) for i in range(2)],
            "outcomes": outcomes}


def run(output, feasibility, repetitions=200, resamples=10000, seed=2026102409, backend="numpy",
        world_counts=(60, 120, 240, 480), scenarios=tuple(SCENARIOS)):
    directory = Path(output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    audit_path = Path(feasibility)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["universe_size"] != 576 or len(audit["accepted"]) != 576 or audit["model_api_calls"]:
        raise ValueError("unexpected finite-universe audit")
    config = {"schema": "e009-power-full-v1", "seed": seed, "repetitions": repetitions, "bootstrap_resamples": resamples,
              "world_counts": list(world_counts), "scenarios": list(scenarios), "backend": backend,
              "python": sys.version, "executable": sys.executable, "scope": "planning assumptions only; no observed model outcomes",
              "feasibility_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
              "heldout_generated": False, "model_api_calls": 0,
              "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                  Path(__file__), Path(__file__).with_name("e009_statistics.py"))}}
    if backend == "numpy":
        import numpy as np
        config["numpy_version"] = np.__version__
    write_once(directory / "CONFIG.json", config)
    results, started = [], time.monotonic()
    for n in world_counts:
        for scenario in scenarios:
            result = cell(n, scenario, repetitions, resamples, seed, backend, audit["accepted"])
            name = f"n{n}-{scenario}.json"
            write_once(directory / name, result)
            result.pop("outcomes")
            results.append(result)
            print(json.dumps({"cell": name, "seconds": round(time.monotonic() - started, 3),
                              "effect": result["contrasts"][0]["mean_effect"],
                              "test_power": result["contrasts"][0]["test_pass"]["rate"],
                              "full_decision_power": result["contrasts"][0]["decision"]["rate"]}), flush=True)
    write_once(directory / "SUMMARY.json", {"config": config, "cells": results, "seconds": time.monotonic() - started})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--feasibility", required=True)
    parser.add_argument("--repetitions", type=int, default=200)
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--worlds", type=int, nargs="+", default=[60, 120, 240, 480])
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    parser.add_argument("--backend", choices=["python", "numpy"], default="numpy")
    args = parser.parse_args()
    run(args.output, args.feasibility, args.repetitions, args.resamples, backend=args.backend,
        world_counts=args.worlds, scenarios=args.scenarios)
