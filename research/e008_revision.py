"""Secondary epistemic endpoints; no self-reported revision counts as verification."""
from collections import defaultdict
import math
import random

from .e008_assessment import encoded_value, exact_value, hypothesis_index, hypothesis_key, inherited_claims
from .e008_protocol import source_ids
from .e008_scm import candidates
from . import e008_oracle as oracle


def equal(left, right):
    return type(left) is type(right) and left == right


def revision_metrics(job, score, chain, world, gold):
    """Opportunities concern the immediate predecessor, not every archived claim.

    Otherwise a correction already made by B would be falsely demanded again
    from C/D merely because A's original error remains in the immutable archive.
    Direct injections and natural claims have separate denominators.
    """
    actual_chain = [entry for entry in chain if entry["job"]["id"] != job["id"]]
    previous = actual_chain[-1] if actual_chain else None
    inherited = inherited_claims(chain, gold)
    current = gold["subsets"]["+".join(sorted(source_ids(job)))]
    hypotheses = (score or {}).get("hypotheses", {})
    changes = (score or {}).get("revisions", [])
    observed = (previous or {}).get("result", {}).get("answer")
    prior_observable = isinstance(observed, dict) and isinstance(observed.get("answers"), list)
    old_roots = {}
    if prior_observable and isinstance(observed.get("hypotheses"), list):
        for h in observed["hypotheses"]:
            try:
                index = hypothesis_index()[hypothesis_key(h)]
                if h["status"] in ("possible", "preferred") and isinstance(h["id"], str):
                    if h["id"] in old_roots:
                        old_roots[h["id"]] = None  # Ambiguous identity is not evidence.
                    else:
                        old_roots[h["id"]] = (index, "natural")
            except (ValueError, KeyError, TypeError):
                continue
    bulletin = job.get("bulletin") or {}
    if "hypothesis" in bulletin:
        h = dict(bulletin["hypothesis"], id="probe:H0", status="preferred", confidence=.95, evidence=["EA"])
        old_roots["probe:H0"] = (hypothesis_index()[hypothesis_key(h)], "deliberate_injection")
    metrics = {origin: {"root_opportunities": 0, "root_rejections": 0,
                        "claim_error_opportunities": 0, "claim_error_corrections": 0,
                        "dependent_opportunities": 0, "dependent_corrections": 0,
                        "correct_prior_claims": 0, "false_corrections": 0,
                        "uncertainty_opportunities": 0, "uncertainty_resolutions": 0}
               for origin in ("natural", "deliberate_injection")}
    rejected = set()
    eligible_roots = {}
    for identity, prior in old_roots.items():
        if prior is None:
            continue
        index, origin = prior
        if index in current["candidate_indices"]:
            continue
        metrics[origin]["root_opportunities"] += 1
        eligible_roots[identity] = index
        now = hypotheses.get(identity, {})
        if now.get("index") == index and now.get("status") == "rejected" and now.get("status_correct") is True:
            metrics[origin]["root_rejections"] += 1
            rejected.add(identity)
    questions = {q["id"]: q for q in world["panel"]}
    natural_prefix = previous["job"]["stage"] + ":" if previous and prior_observable else None
    injected_ids = {claim["id"] for claim in bulletin.get("claims", [])}
    for identity, prior in inherited.items():
        origin = "deliberate_injection" if identity in injected_ids else "natural"
        if identity not in injected_ids and (natural_prefix is None or not identity.startswith(natural_prefix)):
            continue
        qid = prior["question_id"]
        if qid not in questions:
            continue
        try:
            old = exact_value(prior["value"], questions[qid]["kind"])
        except ValueError:
            continue
        wanted = current["questions"][qid]
        matched = [change for change in changes if change.get("claim_id") == identity
                   and change.get("valid") and change.get("matches_observed_prior")]
        counts = metrics[origin]
        if equal(old, wanted["expected"]):
            counts["correct_prior_claims"] += 1
            counts["false_corrections"] += any(change["false_correction"] for change in matched)
        if old is None and wanted["identified"]:
            counts["uncertainty_opportunities"] += 1
            counts["uncertainty_resolutions"] += any(change["uncertainty_resolution"] for change in matched)
        if old is None or any(equal(old, value) for value in wanted["possibilities"]):
            continue
        counts["claim_error_opportunities"] += 1
        counts["claim_error_corrections"] += any(change["error_correction"] for change in matched)
        dependencies = [identity for identity in prior.get("depends_on", [])
                        if identity in eligible_roots
                        and prior.get("dependency_hypothesis_indices", {}).get(identity) == eligible_roots[identity]
                        and equal(encoded_value(oracle.answer(candidates()[eligible_roots[identity]], questions[qid])), old)]
        if dependencies:
            counts["dependent_opportunities"] += 1
            counts["dependent_corrections"] += any(
                change["error_correction"] and set(change.get("rejected_dependencies", [])) & rejected & set(dependencies)
                for change in matched)
    return {"prior_answer_observable": prior_observable, "groups": metrics,
            "scope": "Same observed ID/assignment and linked revision in current final; not proof of decoding arbitrary memory or of private beliefs."}


def uncertainty_metrics(score, *, assigned_questions, identified_questions):
    if not 0 <= identified_questions <= assigned_questions:
        raise ValueError("known assigned-information identifiability denominator required")
    rows = (score or {}).get("questions", [])
    if rows and len(rows) != assigned_questions:
        raise ValueError("assigned question denominator differs")
    valid = [row for row in rows if row.get("valid")]
    bins = [{"count": 0, "confidence_sum": 0.0, "correct_sum": 0} for _ in range(10)]
    for row in valid:
        confidence = row["confidence"]
        cell = bins[min(9, int(confidence * 10))]
        cell["count"] += 1
        cell["confidence_sum"] += confidence
        cell["correct_sum"] += int(row["correct"])
    return {"assigned_questions": assigned_questions, "valid_answers": len(valid),
            "supported_explanations": sum(row.get("supported_explanation") is True for row in rows),
            "source_ids_valid": sum(row.get("source_ids_valid") is True for row in rows),
            "identified_questions": identified_questions,
            "unidentified_questions": assigned_questions - identified_questions,
            "correct_abstentions": sum(row.get("correct") is True and row.get("valid") and row.get("value") is None for row in rows),
            "excess_abstentions": sum(row.get("lost_or_excess_abstention") is True for row in rows),
            "unsupported_points": sum(row.get("unidentified_point_prediction") is True for row in rows),
            "high_confidence_unsupported_points": sum(row.get("high_confidence_unidentified_point") is True for row in rows),
            "brier_sum": sum(row["brier"] for row in valid), "confidence_bins": bins}


def world_interval(values, families, *, draws=10000, seed=20261020083):
    if not values:
        return {"mean": None, "bootstrap_95": None, "eligible_worlds": 0}
    groups = defaultdict(list)
    for identity in sorted(values):
        groups[families[identity]].append(identity)
    rng = random.Random(seed)
    simulated = []
    for _ in range(draws):
        sample = [rng.choice(group) for group in groups.values() for _ in group]
        simulated.append(sum(values[w] for w in sample) / len(sample))
    simulated.sort()
    return {"mean": sum(values.values()) / len(values), "eligible_worlds": len(values),
            "bootstrap_95": [simulated[max(0, math.ceil(.025 * draws) - 1)], simulated[math.ceil(.975 * draws) - 1]],
            "scope": "descriptive world bootstrap conditional on observable eligible opportunities; not a new significance test"}


def aggregate_revision(records, worlds, *, draws=10000):
    """Conditions/controls/stages remain separate; repetitions never increase n."""
    families = {w["id"]: w["truth"]["family"] for w in worlds}
    groups = defaultdict(list)
    for row in records:
        job = row["job"]
        if job["phase"] not in ("test", "robustness") or job["role"] != "investigator":
            continue
        key = "|".join((job["phase"], job["condition"], job.get("control") or "main", job["stage"]))
        groups[key].append(row)
    output = {}
    ratios = (("root_rejections", "root_opportunities"), ("claim_error_corrections", "claim_error_opportunities"),
              ("dependent_corrections", "dependent_opportunities"), ("false_corrections", "correct_prior_claims"),
              ("uncertainty_resolutions", "uncertainty_opportunities"))
    for key, group in sorted(groups.items()):
        independent = {r["job"]["world"] for r in group}
        result = {"independent_worlds": len(independent), "contexts": len(group),
                  "unobservable_prior_contexts": sum(not r["revision"]["prior_answer_observable"] for r in group),
                  "failed_or_unverified": sum(r["status"] != "completed" or not r["audit"].get("pass") for r in group),
                  "origins": {}}
        for origin in ("natural", "deliberate_injection"):
            rates = {}
            for numerator, denominator in ratios:
                per_world = defaultdict(list)
                total_numerator = total_denominator = 0
                for row in group:
                    counts = row["revision"]["groups"][origin]
                    total_numerator += counts[numerator]
                    total_denominator += counts[denominator]
                    if counts[denominator]:
                        per_world[row["job"]["world"]].append(counts[numerator] / counts[denominator])
                averaged = {w: sum(v) / len(v) for w, v in per_world.items()}
                rates[numerator] = {**world_interval(averaged, families, draws=draws),
                                    "observed_numerator": total_numerator, "observed_denominator": total_denominator,
                                    "worlds_without_observed_opportunities": len(independent) - len(averaged)}
            result["origins"][origin] = rates
        confidence = {}
        for numerator, denominator in (("supported_explanations", "assigned_questions"),
                                       ("source_ids_valid", "assigned_questions"),
                                       ("valid_answers", "assigned_questions"), ("brier_sum", "valid_answers"),
                                       ("correct_abstentions", "unidentified_questions"),
                                       ("excess_abstentions", "identified_questions"),
                                       ("high_confidence_unsupported_points", "unidentified_questions")):
            per_world = defaultdict(list)
            for row in group:
                values = row["uncertainty"]
                if values[denominator]:
                    per_world[row["job"]["world"]].append(values[numerator] / values[denominator])
            confidence[numerator] = world_interval({w: sum(v) / len(v) for w, v in per_world.items()}, families, draws=draws)
        result["uncertainty"] = confidence
        result["descriptive_counts"] = {name: sum(r["uncertainty"][name] for r in group)
                                       for name in ("assigned_questions", "valid_answers", "correct_abstentions",
                                                    "excess_abstentions", "unsupported_points", "high_confidence_unsupported_points")}
        bins = [{field: sum(r["uncertainty"]["confidence_bins"][i][field] for r in group)
                 for field in ("count", "confidence_sum", "correct_sum")} for i in range(10)]
        result["pooled_reliability_bins_not_independent_observations"] = bins
        output[key] = result
    return output
