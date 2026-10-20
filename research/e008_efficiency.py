"""Fixed H6 operational-resource comparisons, paired at the world level.

The primary inferential family remains the eight accuracy contrasts. Resource
intervals are descriptive, conditional on the two observed development lines;
they are not extra uncorrected hypothesis tests or estimates of model GPU cost.
"""
from collections import defaultdict
import math
import random

from .e008_analysis import CONDITIONS
from .e008_measurements import chain_ids, combine, correct_counts, measure


CONTRASTS = (("T1-C1", "T1", "C1"), ("T2-T1", "T2", "T1"), ("T2-C1", "T2", "C1"),
             ("C1-FULL-JOURNAL", "C1", "FULL-JOURNAL"),
             ("T1-FULL-JOURNAL", "T1", "FULL-JOURNAL"),
             ("T2-FULL-JOURNAL", "T2", "FULL-JOURNAL"))
METRICS = ("total_tokens", "api_plus_mcp_bytes", "context_seconds")
YIELDS = ("integrative_new", "identified_new", "correct_decisions")
REUSES = (1, 10, 100, 1000)
PLAN = {
    "primary_resource_contrast": "T1-C1", "primary_resource": "total_tokens",
    "primary_result": "integrative_new", "primary_reuses": 100,
    "bootstrap_seed": 20261020084, "bootstrap_draws": 10000,
    "favorable_descriptive_rule": "primary accuracy contrast positive AND primary resource ratio upper95 < 1",
    "multiplicity": "No additional resource p-values or confirmatory significance claims; all fixed contrasts/scenarios shown.",
    "scope": "Operational measured resources, not currency, energy or total economic cost. "
             "Input+output token counts have equal unit weight, not equal monetary price.",
}


def metric(row, name):
    return combine([row["input_tokens"], row["output_tokens"]]) if name == "total_tokens" else row[name]


def cells(worlds, jobs, outcomes, resources, *, fixture=False):
    """One equal-weight cell per world/condition; T2 lines never become extra n."""
    selected = [j for j in jobs if j["phase"] == "test" and j["stage"] == "D"]
    index = {j["id"]: j for j in jobs}
    test_worlds = {w["id"] for w in worlds if w["split"] == "test"}
    if len(index) != len(jobs) or set(resources["per_position"]) != set(index) or set(outcomes) != set(index):
        raise ValueError("all unique assigned positions required for resource comparison")
    if {j["world"] for j in selected} != test_worlds or not test_worlds:
        raise ValueError("all independent held-out worlds required")
    result = {}
    for world in sorted(test_worlds):
        result[world] = {}
        for condition in CONDITIONS:
            group = [j for j in selected if j["world"] == world and j["condition"] == condition]
            lineages = ("L1", "L2") if condition == "T2" else (None,)
            repeats = (1,) if fixture else (1, 2)
            expected = {(lineage, replicate) for lineage in lineages for replicate in repeats}
            if len(group) != len(expected) or {(j["lineage"], j["replicate"]) for j in group} != expected:
                raise ValueError("resource matrix missing/duplicated assigned repeat or lineage")
            values = []
            for job in group:
                row = outcomes[job["id"]]
                if row["status"] in ("pending", "running"):
                    raise ValueError("unfinished resource position")
                score = row.get("score") if row["status"] == "completed" and row["audit"].get("pass") else None
                counts = correct_counts(score)
                counts["correct_decisions"] = counts["identified_new"] + counts["correct_abstentions"]
                used = chain_ids(job, index)
                values.append({"cost": {name: combine(metric(resources["per_position"][i], name) for i in used)
                                        for name in METRICS}, "yields": counts})
            result[world][condition] = {
                "cost": {name: combine((v["cost"][name] for v in values), divisor=len(values)) for name in METRICS},
                "yields": {name: sum(v["yields"][name] for v in values) / len(values) for name in YIELDS},
            }
    setup_ids = [j["id"] for j in jobs if j["condition"] == "T2" and j["phase"] in ("development", "validation")]
    setup = {c: {name: (combine(metric(resources["per_position"][i], name) for i in setup_ids)
                        if c == "T2" else measure()) for name in METRICS} for c in CONDITIONS}
    return result, setup


def cost_per_result(setup, cost, produced, reuses):
    if not setup["complete"] or not cost["complete"] or produced <= 0:
        return None
    return (setup["observed"] + reuses * cost["observed"]) / (reuses * produced)


def comparison(left, right, setup_left, setup_right, resource, result, reuses):
    first = cost_per_result(setup_left[resource], left["cost"][resource], left["yields"][result], reuses)
    second = cost_per_result(setup_right[resource], right["cost"][resource], right["yields"][result], reuses)
    return {"first_cost_per_result": first, "second_cost_per_result": second,
            "ratio": first / second if first is not None and second is not None and second > 0 else None}


def breakeven(left, right, setup_left, setup_right, resource, result):
    """Analytic crossing for the observed mixture, not an extrapolation guarantee."""
    a, b = left["yields"][result], right["yields"][result]
    inputs = (left["cost"][resource], right["cost"][resource], setup_left[resource], setup_right[resource])
    if a <= 0 or b <= 0 or not all(v["complete"] for v in inputs):
        return {"first_reuse_not_more_expensive": None, "reason": "unknown_cost_or_zero_result_yield"}
    intercept = setup_left[resource]["observed"] / a - setup_right[resource]["observed"] / b
    slope = left["cost"][resource]["observed"] / a - right["cost"][resource]["observed"] / b
    if intercept + slope <= 0:
        return {"first_reuse_not_more_expensive": 1, "remains_not_more_expensive": slope <= 0}
    if slope >= 0:
        return {"first_reuse_not_more_expensive": None, "reason": "no_crossing_with_observed_costs"}
    crossing = max(1, math.ceil(intercept / -slope))
    return {"first_reuse_not_more_expensive": crossing, "remains_not_more_expensive": True,
            "scope": "point-estimate extrapolation; fixed development cost, stationary mixture"}


def mean_cell(sample, table, condition):
    return {"cost": {name: combine((table[w][condition]["cost"][name] for w in sample), divisor=len(sample))
                     for name in METRICS},
            "yields": {name: sum(table[w][condition]["yields"][name] for w in sample) / len(sample)
                       for name in YIELDS}}


def summarize(worlds, jobs, outcomes, resources, *, primary=None, fixture=False, draws=10000):
    if type(draws) is not int or draws < 100:
        raise ValueError("at least100 deterministic paired world bootstrap draws required")
    table, setup = cells(worlds, jobs, outcomes, resources, fixture=fixture)
    groups = defaultdict(list)
    for w in worlds:
        if w["id"] in table:
            groups[w["truth"]["family"]].append(w["id"])
    groups = [sorted(v) for _, v in sorted(groups.items())]
    identities = sorted(table)
    means = {c: mean_cell(identities, table, c) for c in CONDITIONS}
    comparisons = {}
    for name, first, second in CONTRASTS:
        comparisons[name] = {
            metric_name: {yield_name: {
                "reuses": {str(n): comparison(means[first], means[second], setup[first], setup[second],
                                               metric_name, yield_name, n) for n in REUSES},
                "breakeven": breakeven(means[first], means[second], setup[first], setup[second],
                                       metric_name, yield_name)}
                for yield_name in YIELDS} for metric_name in METRICS}
    # CIs cover the predeclared primary N/result only. Other N/results are
    # descriptive sensitivities, not searched for a more favorable interval.
    simulated = {(name, resource): [] for name, _, _ in CONTRASTS for resource in METRICS}
    rng = random.Random(PLAN["bootstrap_seed"])
    for _ in range(draws):
        sample = [rng.choice(group) for group in groups for _ in group]
        sampled = {c: mean_cell(sample, table, c) for c in CONDITIONS}
        for name, first, second in CONTRASTS:
            for resource in METRICS:
                value = comparison(sampled[first], sampled[second], setup[first], setup[second],
                                   resource, PLAN["primary_result"], PLAN["primary_reuses"])["ratio"]
                simulated[name, resource].append(value)
    for (name, resource), values in simulated.items():
        invalid = sum(v is None or not math.isfinite(v) for v in values)
        interval = None
        if not invalid:
            ordered = sorted(values)
            interval = [ordered[max(0, math.ceil(.025 * draws) - 1)], ordered[math.ceil(.975 * draws) - 1]]
        comparisons[name][resource][PLAN["primary_result"]]["paired_bootstrap_primary"] = {
            "ratio_95": interval, "undefined_draws": invalid, "draws": draws,
            "missing_draw_policy": "Any undefined draw makes interval unavailable; never drop failures or infinities."}
    main = comparisons["T1-C1"]["total_tokens"]["integrative_new"]["paired_bootstrap_primary"]["ratio_95"]
    favorable = bool(not fixture and primary and primary["contrasts"]["T1-C1"]["positive_evidence"]
                     and main is not None and main[1] < 1)
    return {"plan": PLAN, "n_independent_worlds": len(table), "fixture": fixture,
            "world_cells": table, "setup_both_lines_paid": setup, "comparisons": comparisons,
            "favorable_secondary_descriptive_evidence": favorable, "confirmatory_H6_claim": False,
            "bootstrap_scope": "Paired, stratified by SCM family; repeat/line averages within world. "
                               "Conditional on both observed development lines; their sampling uncertainty is not estimated.",
            "limitations": ["No conditional removal of failed or unknown-charge attempts.",
                            "Correct epistemic decisions here use common ABC target, including null; not private beliefs.",
                            "CPU/GPU, energy, monetary price, human T1 labor and full economic cost remain unmeasured."]}
