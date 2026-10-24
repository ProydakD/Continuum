"""Offline power/cost sensitivity, not power estimated from held-out outcomes."""
import math
import random


def power_cell(n, conditional_effect, stage_failure, repetitions=1000, seed=2026102409):
    if n < 2 or repetitions < 1 or not 0 <= conditional_effect <= 0.4 or not 0 <= stage_failure < 1:
        raise ValueError("invalid planning parameters")
    rng = random.Random(seed)
    significant, decision, mean_effect = 0, 0, 0.0
    for _ in range(repetitions):
        differences = []
        for _ in range(n):
            # Shared world difficulty; 2 repeats x 2 scenarios remain one cluster.
            p0 = rng.betavariate(4.5, 5.5)
            p1 = min(1.0, p0 + conditional_effect)
            difference = 0
            for _ in range(2):
                complete0 = rng.random() < (1 - stage_failure) ** 5
                complete1 = rng.random() < (1 - stage_failure) ** 5
                for _ in range(2):
                    u0 = rng.random()
                    u1 = u0 if rng.random() < 0.5 else rng.random()
                    difference += int(complete1 and u1 < p1) - int(complete0 and u0 < p0)
            differences.append(difference / 4)
        estimate = sum(differences) / n
        variance = sum((d - estimate) ** 2 for d in differences) / (n - 1)
        se = math.sqrt(variance / n)
        p = math.erfc(abs(estimate / se) / math.sqrt(2)) if se else (0.0 if estimate else 1.0)
        passed = estimate > 0 and p < 0.05 / 3
        significant += passed
        decision += passed and estimate >= 0.10
        mean_effect += estimate
    power = significant / repetitions
    return {"worlds": n, "conditional_effect": conditional_effect, "per_stage_failure": stage_failure,
            "chain_survival": (1 - stage_failure) ** 5, "simulations": repetitions,
            "mean_operational_effect": mean_effect / repetitions,
            "test_power_normal_bonferroni": power,
            "decision_power_without_guardrail": decision / repetitions,
            "test_power_mc_se": math.sqrt(power * (1 - power) / repetitions)}


def planning_report(repetitions=1000):
    cells = [power_cell(n, effect, loss, repetitions) for n in (60, 120, 240)
             for effect in (0.10, 0.15, 0.20) for loss in (0.0, 0.03, 0.08)]
    contexts = 240 * 8 * 2 * 2 * 5
    return {"scope": "planning assumptions only; no empirical model outcomes",
            "method": "cluster simulation; paired normal approximation, conservative Bonferroni not final Holm/randomization",
            "guardrail_simulated": False, "sample_size_selected": False, "seed": 2026102409,
            "cells": cells, "upper_main_contexts": contexts,
            "assumed_input_tokens": contexts * 12000, "assumed_output_tokens": contexts * 4000,
            "serial_hours_60_to_180_seconds": [contexts / 60, contexts / 20],
            "price": None, "excluded": ["pilot", "T2 development", "robustness", "retries", "V1 compute"]}
