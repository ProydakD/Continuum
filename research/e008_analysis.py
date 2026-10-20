"""Fixed world-paired analysis; repeated questions, contexts and T2 lines are not n."""
from collections import Counter
from fractions import Fraction
import math
import random
from statistics import NormalDist

CONTRASTS = (
    ("T1-C1", "T1", "C1"),
    ("T2-T1", "T2", "T1"),
    ("C1-C0", "C1", "C0"),
    ("C1-SINGLE-A", "C1", "SINGLE-A"),
    ("C1-SINGLE-B", "C1", "SINGLE-B"),
    ("C1-FULL-JOURNAL", "C1", "FULL-JOURNAL"),
    ("T1-FULL-JOURNAL", "T1", "FULL-JOURNAL"),
    ("T2-FULL-JOURNAL", "T2", "FULL-JOURNAL"),
)
CONDITIONS = ("C0", "C1", "T1", "T2", "SINGLE-A", "SINGLE-B", "FULL-JOURNAL")
TERMINAL = {"completed", "budget_rejected", "failed", "skipped_dependency",
            "protocol_unavailable", "secondary_unavailable", "injected_crash_after_commit"}


def exact_sign_flip(values):
    if not values or any(type(v) is not int for v in values):
        raise ValueError("nonempty integer paired differences required")
    counts = Counter({0: 1})
    for value in values:
        updated = Counter()
        for total, multiplicity in counts.items():
            updated[total - value] += multiplicity
            updated[total + value] += multiplicity
        counts = updated
    observed = abs(sum(values))
    numerator = sum(count for total, count in counts.items() if abs(total) >= observed)
    return {"p": numerator / 2 ** len(values), "tail_assignments": numerator,
            "sign_assignments": 2 ** len(values)}


def holm(p_values):
    if not p_values or any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1
                           for p in p_values.values()):
        raise ValueError("finite probabilities required")
    result, previous = {}, 0.0
    for rank, (name, p) in enumerate(sorted(p_values.items(), key=lambda item: (item[1], item[0]))):
        previous = max(previous, min(1, (len(p_values) - rank) * p))
        result[name] = previous
    return result


def summarize(worlds, jobs, outcomes, *, bootstrap_samples=10000):
    selected = [j for j in jobs if j["phase"] == "test" and j["stage"] == "D"]
    expected = {j["id"] for j in selected}
    if len(expected) != len(selected) or set(outcomes) != expected:
        raise ValueError("one recorded outcome per assigned held-out successor required")
    test = [w for w in worlds if w["split"] == "test"]
    if len({w["id"] for w in test}) != len(test) or not test:
        raise ValueError("unique independent test worlds required")
    if {j["world"] for j in selected} != {w["id"] for w in test}:
        raise ValueError("world assignment mismatch")
    world_scores, epistemic_scores, integration_scores, invalid = {}, {}, {}, 0
    for world in test:
        values, epistemic, integrated = {}, {}, {}
        integrative_total = len(world["design_audit"]["integrative_question_ids"])
        if not 2 <= integrative_total <= 10:
            raise ValueError("registered integrative question set required")
        for condition in CONDITIONS:
            group = [j for j in selected if j["world"] == world["id"] and j["condition"] == condition]
            assignments = {(j["lineage"], j["replicate"]) for j in group}
            wanted = {(lineage, replicate) for lineage in (("L1", "L2") if condition == "T2" else (None,))
                      for replicate in (1, 2)}
            if assignments != wanted or len(group) != len(wanted):
                raise ValueError("registered repeats or T2 lineages missing/duplicated")
            total = epistemic_count = integrated_count = 0
            for job in group:
                row = outcomes[job["id"]]
                if row.get("status") not in TERMINAL:
                    raise ValueError("unfinished position is not a zero-scored failure")
                if row["status"] != "completed" or not row.get("audit", {}).get("pass"):
                    invalid += 1
                    continue
                score = row["score"]
                count = score["new_target_correct"]
                if type(count) is not int or not 0 <= count <= 10 or score["new_total"] != 10:
                    raise ValueError("expected ten newly assigned questions")
                epistemic_current = score["new_epistemic_correct"]
                if type(epistemic_current) is not int or not 0 <= epistemic_current <= 10:
                    raise ValueError("separate assigned-information correctness count required")
                current = score["target_integrative_correct"]
                if (type(current) is not int or not 0 <= current <= min(count, integrative_total)
                        or score["integrative_total"] != integrative_total):
                    raise ValueError("integrative denominator/count differs from registered world")
                total += count
                epistemic_count += epistemic_current
                integrated_count += current
            values[condition] = Fraction(total, 10 * len(group))
            epistemic[condition] = Fraction(epistemic_count, 10 * len(group))
            integrated[condition] = Fraction(integrated_count, integrative_total * len(group))
        world_scores[world["id"]] = values
        epistemic_scores[world["id"]] = epistemic
        integration_scores[world["id"]] = integrated
    n = len(test)
    groups = [[i for i, w in enumerate(test) if w["truth"]["family"] == family]
              for family in sorted({w["truth"]["family"] for w in test})]
    integer_differences = {}
    for name, first, second in CONTRASTS:
        scaled = [40 * (world_scores[w["id"]][first] - world_scores[w["id"]][second]) for w in test]
        if any(value.denominator != 1 for value in scaled):
            raise ValueError("score denominator changed")
        integer_differences[name] = [int(v) for v in scaled]
    if type(bootstrap_samples) is not int or bootstrap_samples < 100:
        raise ValueError("at least100 deterministic bootstrap draws")
    rng = random.Random(20261020082)
    draws = {name: [] for name, _, _ in CONTRASTS}
    integration_draws = []
    c1_integrated = [float(integration_scores[w["id"]]["C1"]) for w in test]
    for _ in range(bootstrap_samples):
        sample = [rng.choice(group) for group in groups for _ in group]
        for name, values in integer_differences.items():
            draws[name].append(sum(values[i] for i in sample) / (40 * n))
        integration_draws.append(sum(c1_integrated[i] for i in sample) / n)
    tests = {name: exact_sign_flip(values) for name, values in integer_differences.items()}
    adjusted = holm({name: result["p"] for name, result in tests.items()})
    results = {}
    for name, values in integer_differences.items():
        ordered = sorted(draws[name])
        estimate = sum(values) / (40 * n)
        results[name] = {"estimate": estimate, **tests[name], "holm_p": adjusted[name],
                         "bootstrap_95": [ordered[max(0, math.ceil(.025 * bootstrap_samples) - 1)],
                                          ordered[math.ceil(.975 * bootstrap_samples) - 1]],
                         "positive_evidence": estimate >= .10 and adjusted[name] < .05}
    ordered = sorted(integration_draws)
    integration = {"C1_mean": sum(c1_integrated) / n,
                   "C1_bootstrap_95": [ordered[max(0, math.ceil(.025 * bootstrap_samples) - 1)],
                                      ordered[math.ceil(.975 * bootstrap_samples) - 1]],
                   "world_scores": {w: {c: float(v) for c, v in cell.items()} for w, cell in integration_scores.items()}}
    return {"n_independent_worlds": n, "assigned_successors": len(selected), "failed_or_unverified": invalid,
            "primary_contrast": "T1-C1", "contrasts": results,
            "prediction_metric": "Same ABC-identifiability target in every condition; a lucky single-source prediction can score here, not as verified knowledge.",
            "world_scores": {w: {c: float(v) for c, v in cell.items()} for w, cell in world_scores.items()},
            "epistemic_world_scores": {w: {c: float(v) for c, v in cell.items()} for w, cell in epistemic_scores.items()},
            "world_scaled_differences": integer_differences,
            "primary_positive": results["T1-C1"]["positive_evidence"],
            "integration": integration,
            "integration_positive": (all(results[name]["positive_evidence"]
                                          for name in ("C1-C0", "C1-SINGLE-A", "C1-SINGLE-B"))
                                     and integration["C1_mean"] >= .5 and integration["C1_bootstrap_95"][0] > .25),
            "model_protocol_positive": results["T2-T1"]["positive_evidence"],
            "method": "exact two-sided paired sign-flips; Holm over8;10000 stratified world bootstrap draws in final analysis",
            "assumption": "sign-flip inference assumes symmetric paired differences under the null; not a randomized-label causal proof"}


def precision_plan(n=60):
    normal = NormalDist()
    critical = normal.inv_cdf(1 - .05 / (2 * len(CONTRASTS)))
    multiplier = (critical + normal.inv_cdf(.8)) / math.sqrt(n)
    return {"n_independent_worlds": n, "familywise_tests": len(CONTRASTS),
            "alpha": .05, "power_approximation": .8,
            "approximate_detectable_difference_by_paired_sd": {str(sd): sd * multiplier for sd in (.2, .35, .5, 1.0)},
            "unadjusted_mean_95_half_width_by_paired_sd": {str(sd): 1.96 * sd / math.sqrt(n) for sd in (.2, .35, .5, 1.0)},
            "limitations": "Normal approximation with Bonferroni worst-case critical value for Holm, not guaranteed power of exact sign-flips. SD assumptions are not pilot observations; questions and repeats do not increase n."}
