"""World-cluster inference; no normal approximation or successful-only exclusions."""
from functools import lru_cache
import math
import random

CONTRASTS = ((1, 0, "F1-F0"), (3, 2, "S1-S0"), (3, 1, "S1-F1"))


@lru_cache(maxsize=16384)
def signflip_counts(ones, twos, observed):
    """Exact two-sided sign-flip tail for two-repeat world count differences."""
    if observed == 0:
        return 1.0
    # K1 and K2 count positive signs among absolute weights 1 and 2.
    prefix, total = [], 0
    for k in range(ones + 1):
        total += math.comb(ones, k)
        prefix.append(total)
    def cdf(k):
        return 0 if k < 0 else prefix[min(k, ones)]
    extreme = 0
    for k2 in range(twos + 1):
        offset = 4 * k2 - ones - 2 * twos
        low = math.floor((-observed - offset) / 2)
        high = math.ceil((observed - offset) / 2)
        extreme += math.comb(twos, k2) * (cdf(low) + total - cdf(high - 1))
    return extreme / (2 ** (ones + twos))


def exact_signflip(differences):
    if not differences or any(type(x) is not int or abs(x) > 2 for x in differences):
        raise ValueError("integer count differences from exactly two assigned repeats required")
    return signflip_counts(sum(abs(x) == 1 for x in differences), sum(abs(x) == 2 for x in differences), abs(sum(differences)))


def holm(pvalues):
    if not pvalues or any(not math.isfinite(p) or not 0 <= p <= 1 for p in pvalues):
        raise ValueError("invalid p values")
    adjusted, previous = [None] * len(pvalues), 0.0
    for rank, index in enumerate(sorted(range(len(pvalues)), key=pvalues.__getitem__)):
        previous = max(previous, min(1.0, (len(pvalues) - rank) * pvalues[index]))
        adjusted[index] = previous
    return adjusted


def quantile(values, probability):
    ordered = sorted(values)
    if not ordered or not 0 <= probability <= 1:
        raise ValueError("invalid quantile")
    position = (len(ordered) - 1) * probability
    lo = math.floor(position)
    return ordered[lo] + (position - lo) * (ordered[math.ceil(position)] - ordered[lo])


def bootstrap_means(rows, resamples, seed, backend="python"):
    """Resample whole paired world rows, never individual episodes or claims."""
    n = len(rows)
    if n < 2 or resamples < 1 or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("invalid bootstrap matrix")
    if backend == "numpy":
        import numpy as np
        rng = np.random.default_rng(seed)
        matrix = np.asarray(rows, dtype=np.float64)
        result = []
        for start in range(0, resamples, 256):
            indices = rng.integers(0, n, size=(min(256, resamples - start), n))
            result.extend(matrix[indices].mean(axis=1).tolist())
        return result
    if backend != "python":
        raise ValueError("unknown bootstrap backend")
    rng = random.Random(seed)
    return [[sum(rows[i][j] for i in indices) / n for j in range(len(rows[0]))]
            for indices in ([rng.randrange(n) for _ in range(n)] for _ in range(resamples))]


def bernoulli_kl(x, p):
    if x == p:
        return 0.0
    if p in (0.0, 1.0):
        return math.inf
    return (x * math.log(x / p) if x else 0.0) + ((1 - x) * math.log((1 - x) / (1 - p)) if x < 1 else 0.0)


def bounded_mean_upper(mean, n, alpha=0.05):
    """Invert Hoeffding's Bernoulli-envelope KL tail for independent [0,1] world values."""
    if not 0 <= mean <= 1 or n < 1 or not 0 < alpha < 1:
        raise ValueError("invalid bounded mean")
    if mean == 1:
        return 1.0
    if mean == 0:
        return -math.expm1(math.log(alpha) / n)
    lo, hi, threshold = mean, 1.0, -math.log(alpha) / n
    for _ in range(70):
        middle = (lo + hi) / 2
        if bernoulli_kl(mean, middle) > threshold:
            hi = middle
        else:
            lo = middle
    return hi


def bounded_difference_upper(differences, alpha=0.05):
    """D = D+ - D-; union-bound two one-sided bounds, without sign symmetry."""
    n = len(differences)
    if not n or any(not math.isfinite(d) or not -1 <= d <= 1 for d in differences):
        raise ValueError("invalid paired loss differences")
    positive = sum(max(d, 0) for d in differences) / n
    negative = sum(max(-d, 0) for d in differences) / n
    upper_positive = bounded_mean_upper(positive, n, alpha / 2)
    lower_negative = 1 - bounded_mean_upper(1 - negative, n, alpha / 2)
    return upper_positive - lower_negative


def analyze_worlds(worlds, *, resamples=10000, seed=2026102409, backend="python"):
    if len(worlds) < 2 or len({w["id"] for w in worlds}) != len(worlds):
        raise ValueError("at least two distinct worlds required")
    for w in worlds:
        if (len(w["successes"]) != 4 or any(type(v) is not int or not 0 <= v <= 2 for v in w["successes"])
                or len(w["worst_losses"]) != 4 or type(w["slots"]) is not int or w["slots"] <= 0
                or any(type(v) is not int or not 0 <= v <= w["slots"] for v in w["worst_losses"])):
            raise ValueError("complete assigned counts required; zero/unknown denominator is not safety")
    loss = [[v / w["slots"] for v in w["worst_losses"]] for w in worlds]
    differences = [[w["successes"][left] - w["successes"][right] for w in worlds] for left, right, _ in CONTRASTS]
    rows = [[differences[c][i] / 2 for c in range(3)] + loss[i] for i in range(len(worlds))]
    boot = bootstrap_means(rows, resamples, seed, backend)
    raw_p = [exact_signflip(d) for d in differences]
    adjusted = holm(raw_p)
    safety = []
    for left, right in ((1, 0), (3, 2)):
        d = [r[left] - r[right] for r in loss]
        u = bounded_difference_upper(d)
        absolute = bounded_mean_upper(sum(r[left] for r in loss) / len(loss), len(loss))
        safety.append({"difference": sum(d) / len(d), "upper_difference": u, "upper_absolute": absolute,
                       "bootstrap_upper_difference_descriptive": quantile([r[3 + left] - r[3 + right] for r in boot], .95),
                       "pass": u <= .02 and absolute <= .05})
    contrasts = []
    for i, (_, _, name) in enumerate(CONTRASTS):
        estimate = sum(differences[i]) / (2 * len(worlds))
        interval = [quantile([r[i] for r in boot], .025), quantile([r[i] for r in boot], .975)]
        test = adjusted[i] < .05 and estimate > 0
        guardrail = safety[i]["pass"] if i < 2 else all(s["pass"] for s in safety)
        contrasts.append({"name": name, "estimate": estimate, "p_exact": raw_p[i], "p_holm": adjusted[i],
                          "world_bootstrap_95": interval, "test_pass": test,
                          "decision_without_guardrail": test and estimate >= .10 and interval[0] > 0,
                          "decision": bool(test and estimate >= .10 and interval[0] > 0 and guardrail)})
    return {"worlds": len(worlds), "assigned_repeats": 2, "contrasts": contrasts, "safety": safety,
            "bootstrap_resamples": resamples, "bootstrap_backend": backend,
            "scope": "world-weighted paired inference; sign-flip exact under within-world exchangeable/symmetric sharp null"}
