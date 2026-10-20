"""Pre-API E008 assignments, disjoint causal worlds and deterministic selection."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import secrets

from .e008_scm import FAMILIES, design_world

SPLIT_COUNTS = {"training": 4, "calibration": 2, "validation": 4, "test": 20}
MEMORY_BUDGETS = (1024, 2048, 4096)
ARMS = (("C1", None), ("T1", None), ("T2", "L1"), ("T2", "L2"))
VERSIONS = (1, 2, 3)
REPLICATES = (1, 2)


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def truth_signature(world):
    truth = world["truth"]
    return signature({k: truth[k] for k in ("family", "order", "gate", "flips")})


def corpus(seed, *, per_family=None, excluded_worlds=()):
    counts = SPLIT_COUNTS if per_family is None else per_family
    rng = random.Random(seed)
    truths = {truth_signature(w) for w in excluded_worlds}
    observations = {signature(w["evidence"]) for w in excluded_worlds}
    worlds, rejected = [], 0
    for split, count in counts.items():
        if type(count) is not int or count <= 0:
            raise ValueError("positive count per family required")
        for family in FAMILIES:
            for ordinal in range(count):
                identity = f"{split}-{family}-{ordinal + 1:03}"
                for _ in range(2000):
                    world = design_world(rng, family, identity)
                    truth, observed = truth_signature(world), signature(world["evidence"])
                    if truth not in truths and observed not in observations:
                        break
                    rejected += 1
                else:
                    raise ValueError("disjoint-world rejection ceiling reached before API")
                truths.add(truth)
                observations.add(observed)
                worlds.append(dict(world, split=split))
    return {"generation_seed": seed, "counts_per_family": counts, "worlds": worlds,
            "duplicate_rejections": rejected, "excluded_worlds": len(excluded_worlds),
            "selection": "information-feasibility and uniqueness only; never model outcomes"}


def schedule(worlds, *, seed=20261020081):
    """All positions fixed before API; selected budget/protocol resolved by locks."""
    by_split = {split: [w for w in worlds if w["split"] == split] for split in SPLIT_COUNTS}
    if any(not values for values in by_split.values()):
        raise ValueError("all four disjoint splits required")
    jobs = []
    rng = random.Random(seed)
    main = {}

    def add(stage, condition, world, *, phase, source=None, budget=None, lineage=None, version=None,
            replicate=1, control=None, role="investigator"):
        identity = f"j{len(jobs) + 1:05}"
        job = {"id": identity, "world": world["id"] if world else None, "stage": stage,
               "condition": condition, "phase": phase, "role": role, "source": source,
               "budget": budget, "budget_slot": None if budget is not None else "calibration_lock",
               "lineage": lineage, "version": version, "replicate": replicate, "control": control,
               "protocol_version": ("typed-v1" if condition == "T1" else
                                    f"{lineage}-v{version}" if condition == "T2" and version else None),
               "protocol_slot": "validation_lock" if condition == "T2" and version is None else None,
               "model_role": "secondary" if control == "cross_model" else "primary"}
        jobs.append(job)
        return identity

    def block(cells, phase):
        previous = {}
        for stage in "ABCD":
            order = list(enumerate(cells))
            rng.shuffle(order)
            for i, (world, condition, lineage, version, budget, replicate) in order:
                previous[i] = add(stage, condition, world, phase=phase, source=previous.get(i), budget=budget,
                                  lineage=lineage, version=version, replicate=replicate)
                if phase == "test":
                    main[(world["id"], condition, lineage, replicate, stage)] = previous[i]

    cells = [(w, c, None, None, b, 1) for w in by_split["calibration"]
             for b in MEMORY_BUDGETS for c in ("C1", "T1")]
    block(cells, "calibration")
    for w in by_split["calibration"]:
        add("D", "FULL-JOURNAL", w, phase="calibration", budget=MEMORY_BUDGETS[-1])
    for lineage in ("L1", "L2"):
        for version in VERSIONS:
            add("A", "T2", None, phase="development", lineage=lineage, version=version, role="designer")
            block([(w, "T2", lineage, version, None, 1) for w in by_split["validation"]], "validation")
            add("B", "T2", None, phase="development", lineage=lineage, version=version, role="critic")
    block([(w, condition, lineage, None, None, replicate)
           for w in by_split["test"] for condition, lineage in ARMS for replicate in REPLICATES], "test")
    controls = [(w, c, r) for w in by_split["test"] for c in ("C0", "SINGLE-A", "SINGLE-B", "FULL-JOURNAL")
                for r in REPLICATES]
    rng.shuffle(controls)
    for w, c, replicate in controls:
        add("D", c, w, phase="test", replicate=replicate)
    control_worlds = [w for family in FAMILIES
                      for w in [w for w in by_split["test"] if w["truth"]["family"] == family][:4]]
    for world in control_worlds:
        for condition, lineage in ARMS:
            for control in ("deliberate_false_claim", "forged_source", "authentication_ablation"):
                source = main[(world["id"], condition, lineage, 1, "A")]
                for stage in "BCD":
                    source = add(stage, condition, world, phase="robustness", source=source, lineage=lineage, control=control)
            source = main[(world["id"], condition, lineage, 1, "B")]
            crash = add("C", condition, world, phase="robustness", source=source, lineage=lineage, control="crash")
            add("D", condition, world, phase="robustness", source=crash, lineage=lineage, control="crash")
            source = main[(world["id"], condition, lineage, 1, "C")]
            add("D", condition, world, phase="robustness", source=source, lineage=lineage, control="cross_model")
    return jobs


def select_budget(records, world_ids):
    """Prefer a non-floor/non-ceiling absolute level, NEVER a format difference."""
    expected = {(w, c, b) for w in world_ids for c in ("C1", "T1") for b in MEMORY_BUDGETS}
    if not world_ids or len(set(world_ids)) != len(world_ids) or set(records) != expected:
        raise ValueError("every assigned calibration cell, including failures as zero, is required")
    for value in records.values():
        if (not isinstance(value, dict) or set(value) != {"identified_correct", "identified_total"}
                or any(type(v) is not int for v in value.values())
                or not 0 <= value["identified_correct"] <= value["identified_total"] <= 10 or value["identified_total"] == 0):
            raise ValueError("identified counts required; correct nulls cannot disguise a calibration floor")
    for world in world_ids:
        if len({records[(world, c, b)]["identified_total"] for c in ("C1", "T1") for b in MEMORY_BUDGETS}) != 1:
            raise ValueError("identified denominator must be fixed for each world")
    candidates, ordering = [], {}
    for budget in MEMORY_BUDGETS:
        rates = {c: sum(Fraction(records[(w, c, budget)]["identified_correct"], records[(w, c, budget)]["identified_total"])
                       for w in world_ids) / len(world_ids) for c in ("C1", "T1")}
        within = all(Fraction(1, 5) <= value <= Fraction(4, 5) for value in rates.values())
        mean = sum(rates.values()) / 2
        ordering[budget] = (not within, abs(mean - Fraction(1, 2)), budget)
        candidates.append({"budget": budget, "rates": {c: float(v) for c, v in rates.items()},
                           "both_in_target": within, "distance_to_half": float(abs(mean - Fraction(1, 2)))})
    ranked = sorted(candidates, key=lambda c: ordering[c["budget"]])
    return {"budget": ranked[0]["budget"], "within_target": ranked[0]["both_in_target"], "candidates": candidates,
            "rule": "world-mean accuracy of identified predictions: both C1/T1 in[.2,.8], pooled closeness to.5, smaller budget; no test feedback"}


def select_protocol(records, world_ids, *, available_versions=VERSIONS):
    expected = {(version, w) for version in VERSIONS for w in world_ids}
    if set(records) != expected:
        raise ValueError("all assigned validation cells required; no test records")
    means = {}
    for version in VERSIONS:
        scores = [records[(version, w)] for w in world_ids]
        if any(type(v) is not int or not 0 <= v <= 10 for v in scores):
            raise ValueError("integer correct counts including zero failures required")
        means[version] = sum(scores) / (10 * len(world_ids))
    # Failed proposals retain zero validation outcomes and cannot silently get a retry.
    if not set(available_versions) <= set(VERSIONS):
        raise ValueError("unregistered protocol version")
    if any(means[v] != 0 for v in VERSIONS if v not in available_versions):
        raise ValueError("unavailable proposal cannot have successful validation")
    winner = min(available_versions, key=lambda v: (-means[v], v)) if available_versions else None
    return {"version": winner, "validation_means": means, "rule": "largest validation mean; earlier version breaks ties"}


def bounds(jobs):
    counts = dict(sorted(Counter(j["phase"] for j in jobs).items()))
    positions = len(jobs)
    return {"positions": positions, "by_phase": counts,
            "independent_test_worlds": len({j["world"] for j in jobs if j["phase"] == "test"}),
            "application_replicates": 2, "T2_development_lineages": 2,
            "maximum_responses_per_context": 10, "compatibility_smokes": 2,
            "maximum_response_attempts": positions * 10 + 2,
            "output_tokens_per_response": 8192, "maximum_returned_output_token_budget": (positions * 10 + 2) * 8192,
            "HTTP_request_body_bytes": 262144, "HTTP_response_body_bytes": 4194304,
            "protocol_body_bytes": 8192, "series_seconds": 259200, "concurrency": 1,
            "artifact_bytes": 40 * 1024 ** 3, "reserve_bytes_per_context": 128 * 1024 ** 2,
            "expected_tokens_assumptions": {"responses_per_context": 4, "input_tokens_per_response": [3000, 8000],
                                           "output_tokens_per_response": [1000, 2500]},
            "expected_input_tokens_range": [positions * 4 * x for x in (3000, 8000)],
            "expected_output_tokens_range": [positions * 4 * x for x in (1000, 2500)],
            "expected_cost_USD": None,
            "note": "planning estimate, not observed usage or attested billing; limits require live-controller enforcement"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--exclude-corpus", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("corpus already exists; do not regenerate")
    excluded = json.loads(args.exclude_corpus.read_text())["worlds"]
    result = corpus(secrets.randbits(128), excluded_worlds=excluded)
    jobs = schedule(result["worlds"])
    result.update(schedule_seed=20261020081, schedule=jobs, bounds=bounds(jobs), preregistered=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"worlds": len(result["worlds"]), "output": str(args.output.resolve()),
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "bounds": result["bounds"]}))


if __name__ == "__main__":
    main()
