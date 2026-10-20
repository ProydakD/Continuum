"""Independent task/provenance/revision scores, never used inside a worker."""
from fractions import Fraction
from functools import lru_cache
import itertools
import json
import math

from . import e008_oracle as oracle
from .e008_scm import candidates

ANSWER_FIELDS = {"id", "value", "confidence", "evidence", "depends_on", "explanation", "witnesses"}
HYPOTHESIS_FIELDS = {"id", "family", "order", "gate", "flips", "status", "confidence", "evidence"}
REVISION_FIELDS = {"claim_id", "previous_value", "new_value", "evidence", "reason"}


def exact_value(value, kind):
    if value is None:
        return None
    if kind in ("edge", "path"):
        if type(value) is not bool:
            raise ValueError("structural answer must be Boolean or null")
        return value
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError("probability must be an exact rational string or null")
    try:
        number = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("invalid exact probability") from exc
    if not 0 <= number <= 1:
        raise ValueError("probability outside [0,1]")
    return str(number)


def encoded_value(value):
    return value if value is None or type(value) is bool else str(value)


def confidence_valid(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def source_list(value, permitted):
    return isinstance(value, list) and all(isinstance(x, str) for x in value) and len(value) == len(set(value)) and set(value) <= set(permitted)


def hypothesis_key(value):
    if not isinstance(value, dict) or set(value) != HYPOTHESIS_FIELDS:
        raise ValueError("hypothesis fields")
    if not isinstance(value["order"], list) or not isinstance(value["flips"], list):
        raise ValueError("hypothesis arrays")
    if not all(type(x) is int and x in (0, 1) for x in value["flips"]):
        raise ValueError("hypothesis Boolean polarities")
    if not isinstance(value["family"], str) or not isinstance(value["gate"], str) or any(not isinstance(x, str) for x in value["order"]):
        raise ValueError("hypothesis assignment types")
    return value["family"], tuple(value["order"]), value["gate"], tuple(value["flips"])


@lru_cache(maxsize=1)
def hypothesis_index():
    return {(m["family"], tuple(m["order"]), m["gate"], tuple(m["flips"])): i for i, m in enumerate(candidates())}


@lru_cache(maxsize=4096)
def possibilities(indices, question_json):
    query = json.loads(question_json)
    values = {oracle.answer(candidates()[i], query) for i in indices}
    if not values:
        raise ValueError("inconsistent evidence, not ordinary abstention")
    return tuple(sorted((encoded_value(v) for v in values), key=lambda v: json.dumps(v)))


def build_gold(world):
    """All seven nonempty primary-evidence subsets, independently evaluated."""
    records = {r["id"]: r for r in world["evidence"]}
    questions = world["panel"] + world["successor"]
    subsets = {}
    for count in range(4):
        for names in itertools.combinations(sorted(records), count):
            indices = oracle.compatible_models(candidates(), [records[n] for n in names]) if names else list(range(len(candidates())))
            by_question = {}
            for q in questions:
                signature = json.dumps({k: v for k, v in q.items() if k != "id"}, sort_keys=True)
                possible = list(possibilities(tuple(indices), signature))
                by_question[q["id"]] = {"possibilities": possible,
                    "identified": len(possible) == 1 and possible[0] is not None,
                    "expected": possible[0] if len(possible) == 1 else None}
            subsets["+".join(names)] = {"candidate_indices": indices, "questions": by_question}
    return {"world": world["id"], "subsets": subsets,
            "integrative_question_ids": world["design_audit"]["integrative_question_ids"],
            "unidentifiable_question_ids": world["design_audit"]["unidentifiable_question_ids"]}


def inherited_claims(chain, gold):
    """Audit-only reconstruction from verified ancestor outputs and injections.

    The caller supplies ancestors in chronological order after lineage checks.
    These outputs are never provided to the next model outside its saved memory.
    """
    inherited, hypothesis_history = {}, {}
    for entry in chain:
        job, result = entry["job"], entry["result"]
        origin_key = {"A": "EA", "B": "EA+EB", "C": "EA+EB+EC"}[job["stage"]]
        origin = gold["subsets"][origin_key]["questions"]
        output = result.get("answer")
        if isinstance(output, dict) and isinstance(output.get("hypotheses"), list):
            for hypothesis in output["hypotheses"]:
                try:
                    index = hypothesis_index()[hypothesis_key(hypothesis)]
                    identity = hypothesis["id"]
                    if not isinstance(identity, str):
                        continue
                    hypothesis_history[identity] = index if identity not in hypothesis_history or hypothesis_history[identity] == index else None
                except (ValueError, TypeError, KeyError):
                    continue
        if isinstance(output, dict) and isinstance(output.get("answers"), list):
            for claim in output["answers"]:
                if isinstance(claim, dict) and isinstance(claim.get("id"), str) and claim["id"] in origin and "value" in claim:
                    dependencies = claim.get("depends_on")
                    if not isinstance(dependencies, list) or any(not isinstance(k, str) for k in dependencies):
                        dependencies = []
                    inherited[job["stage"] + ":" + claim["id"]] = {
                        "question_id": claim["id"], "value": claim["value"], "depends_on": dependencies,
                        "expected_at_origin": origin[claim["id"]]["expected"],
                        "identified_at_origin": origin[claim["id"]]["identified"], "origin_kind": "natural",
                        "dependency_hypothesis_indices": {k: hypothesis_history[k] for k in dependencies
                                                         if k in hypothesis_history}}
        bulletin = job.get("bulletin") or {}
        if "hypothesis" in bulletin:
            h = {"id": "probe:H0", **bulletin["hypothesis"], "status": "preferred", "confidence": .95, "evidence": ["EA"]}
            hypothesis_history["probe:H0"] = hypothesis_index()[hypothesis_key(h)]
        for claim in bulletin.get("claims", []):
            qid = claim["question_id"]
            initial = gold["subsets"]["EA"]["questions"][qid]
            inherited[claim["id"]] = {"question_id": qid, "value": claim["value"],
                "depends_on": claim.get("depends_on", []), "expected_at_origin": initial["expected"],
                "identified_at_origin": initial["identified"], "origin_kind": "deliberate_injection",
                "dependency_hypothesis_indices": {k: hypothesis_history[k] for k in claim.get("depends_on", [])
                                                 if k in hypothesis_history}}
    return inherited


def assess(answer, questions, gold, permitted, *, inherited_answers=None):
    """Task score is against assigned evidence, not a claim to know private beliefs.

    Abstention after information loss can be rational yet fail the handoff task.
    Unsupported point predictions when even all assigned evidence is ambiguous
    are reported separately; no hidden true value is used to reward lucky guesses.
    """
    inherited_answers = inherited_answers or {}
    subset = gold["subsets"]["+".join(sorted(permitted))]
    ids = [q["id"] for q in questions]
    schema = isinstance(answer, dict) and set(answer) == {"answers", "hypotheses", "revisions", "save_status"}
    if schema:
        schema = (isinstance(answer["answers"], list) and len(answer["answers"]) == len(ids)
                  and all(isinstance(a, dict) and set(a) == ANSWER_FIELDS for a in answer["answers"])
                  and [a["id"] for a in answer["answers"]] == ids
                  and isinstance(answer["hypotheses"], list) and len(answer["hypotheses"]) <= 3
                  and isinstance(answer["revisions"], list) and len(answer["revisions"]) <= 24)
    hypotheses, malformed_hypotheses = {}, 0
    if schema:
        for h in answer["hypotheses"]:
            try:
                index = hypothesis_index()[hypothesis_key(h)]
                if not isinstance(h["id"], str) or len(h["id"]) > 64 or h["id"] in hypotheses:
                    raise ValueError("invalid hypothesis identity")
                if h["status"] not in ("possible", "preferred", "rejected") or not confidence_valid(h["confidence"]) or not source_list(h["evidence"], permitted):
                    raise ValueError("invalid hypothesis status/confidence/provenance")
                consistent = index in subset["candidate_indices"]
                hypotheses[h["id"]] = {"index": index, "status": h["status"], "consistent": consistent,
                                        "status_correct": consistent != (h["status"] == "rejected")}
            except (ValueError, KeyError, TypeError):
                malformed_hypotheses += 1
    results = []
    for position, q in enumerate(questions):
        wanted = subset["questions"][q["id"]]
        target = gold["subsets"]["EA+EB+EC"]["questions"][q["id"]]
        row = {"id": q["id"], "identified": wanted["identified"], "expected": wanted["expected"],
               "integrative": q["id"] in gold["integrative_question_ids"], "valid": False, "correct": False,
               "target_correct": False, "target_expected": target["expected"],
               "supported_explanation": False, "source_ids_valid": False}
        if schema:
            entry = answer["answers"][position]
            try:
                value = exact_value(entry["value"], q["kind"])
                if (not confidence_valid(entry["confidence"]) or not isinstance(entry["explanation"], str)
                    or not isinstance(entry["depends_on"], list) or any(not isinstance(x, str) for x in entry["depends_on"])
                    or not isinstance(entry["witnesses"], list) or any(not isinstance(x, str) for x in entry["witnesses"])):
                    raise ValueError("invalid answer metadata")
                correct = type(value) is type(wanted["expected"]) and value == wanted["expected"]
                target_correct = type(value) is type(target["expected"]) and value == target["expected"]
                valid_sources = source_list(entry["evidence"], permitted)
                proof = False
                if valid_sources:
                    cited = gold["subsets"]["+".join(sorted(entry["evidence"]))]["questions"][q["id"]]
                    if value is not None:
                        proof = cited["identified"] and type(value) is type(cited["expected"]) and value == cited["expected"]
                    else:
                        witnesses = [hypotheses[k] for k in entry["witnesses"] if k in hypotheses and hypotheses[k]["consistent"]]
                        witness_values = {oracle.answer(candidates()[h["index"]], q) for h in witnesses}
                        proof = len(witness_values) >= 2
                row.update(valid=True, value=value, correct=correct, target_correct=target_correct, confidence=entry["confidence"],
                    brier=(entry["confidence"] - int(correct)) ** 2,
                    source_ids_valid=valid_sources, supported_explanation=bool(correct and proof and entry["explanation"].strip()),
                    unidentified_point_prediction=not wanted["identified"] and value is not None,
                    high_confidence_unidentified_point=not wanted["identified"] and value is not None and entry["confidence"] >= .8,
                    lost_or_excess_abstention=wanted["identified"] and value is None,
                    dependencies=entry["depends_on"])
            except (ValueError, KeyError, TypeError):
                pass
        results.append(row)
    revisions = []
    if schema:
        for change in answer["revisions"]:
            checked = {"valid": False, "matches_observed_prior": False, "correct_update": False,
                       "error_correction": False, "false_correction": False, "uncertainty_resolution": False,
                       "unsupported_claim_retraction": False, "new_evidence_confirmation": False}
            if isinstance(change, dict) and set(change) == REVISION_FIELDS and isinstance(change["claim_id"], str):
                prior = inherited_answers.get(change["claim_id"])
                qid = prior["question_id"] if prior else None
                q = next((q for q in questions if q["id"] == qid), None)
                if q:
                    try:
                        old, new = (exact_value(change[k], q["kind"]) for k in ("previous_value", "new_value"))
                        observed_old = exact_value(prior["value"], q["kind"])
                        expected = subset["questions"][qid]["expected"]
                        matched = type(old) is type(observed_old) and old == observed_old
                        new_correct = type(new) is type(expected) and new == expected
                        old_correct_now = type(old) is type(expected) and old == expected
                        now = next(r for r in results if r["id"] == qid)
                        original_expected = prior.get("expected_at_origin")
                        original_correct = type(observed_old) is type(original_expected) and observed_old == original_expected
                        old_still_possible = any(type(old) is type(v) and old == v for v in subset["questions"][qid]["possibilities"])
                        valid = (source_list(change["evidence"], permitted) and isinstance(change["reason"], str)
                                 and bool(change["reason"].strip()) and now["valid"]
                                 and type(new) is type(now["value"]) and new == now["value"])
                        checked.update(valid=valid, claim_id=change["claim_id"], matches_observed_prior=matched,
                            correct_update=bool(valid and matched and not old_correct_now and new_correct),
                            error_correction=bool(valid and matched and old is not None and not old_still_possible and new_correct),
                            false_correction=bool(valid and matched and old_correct_now and not new_correct),
                            uncertainty_resolution=bool(valid and matched and original_correct and old is None and new is not None and new_correct),
                            unsupported_claim_retraction=bool(valid and matched and not original_correct and old is not None and old_still_possible and new is None and new_correct),
                            new_evidence_confirmation=bool(valid and matched and not original_correct and old_correct_now and new_correct),
                            origin_kind=prior.get("origin_kind", "unclassified"),
                            rejected_dependencies=[identity for identity in prior.get("depends_on", [])
                                                   if identity in hypotheses and hypotheses[identity]["status"] == "rejected"
                                                   and hypotheses[identity]["status_correct"]
                                                   and prior.get("dependency_hypothesis_indices", {}).get(identity) == hypotheses[identity]["index"]
                                                   and encoded_value(oracle.answer(candidates()[hypotheses[identity]["index"]], q)) == old],
                            prior_was_identified=prior.get("identified_at_origin"),
                            distinction="later evidence can legitimately resolve an earlier null; not every revision corrects an original error")
                    except (ValueError, TypeError, KeyError):
                        pass
            revisions.append(checked)
    new_rows = [r for r in results if r["id"].startswith("Q")]
    return {"schema_valid": bool(schema), "questions": results,
            "new_correct": sum(r["correct"] and r["target_correct"] for r in new_rows), "new_total": len(new_rows),
            "new_target_correct": sum(r["target_correct"] for r in new_rows),
            "new_epistemic_correct": sum(r["correct"] for r in new_rows),
            "integrative_correct": sum(r["correct"] and r["target_correct"] and r["integrative"] for r in new_rows),
            "target_integrative_correct": sum(r["target_correct"] and r["integrative"] for r in new_rows),
            "integrative_total": sum(r["integrative"] for r in new_rows),
            "supported_explanations": sum(r["supported_explanation"] for r in results),
            "hypotheses": hypotheses, "malformed_hypotheses": malformed_hypotheses, "revisions": revisions}
