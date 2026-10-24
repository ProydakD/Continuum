"""Private full-chain evaluator and transparent natural-opportunity accounting."""
from copy import deepcopy

from .e009_episode import active_evidence, truth_set
from .e009_revision import canonical, memory_envelope, sha, valid_bases
from .e009_guardrails import (preservation_slots, preservation_summary, provenance_valid,
                              publication_valid, sound_claims)

STATES = {"supported", "refuted", "undetermined", "conflicted"}


def valid_claims(claims):
    if not isinstance(claims, list) or len(claims) > 128:
        return False
    ids = []
    for claim in claims:
        if not isinstance(claim, dict):
            return False
        if not (isinstance(claim.get("id"), str) and 0 < len(claim["id"]) <= 64
                and isinstance(claim.get("status"), str) and claim["status"] in STATES
                and isinstance(claim.get("proposition"), dict)
                and isinstance(claim["proposition"].get("query"), dict)
                and isinstance(claim["proposition"]["query"].get("kind"), str)
                and type(claim["proposition"].get("value")) is int
                and isinstance(claim.get("bases"), list)
                and all(isinstance(b, list) and all(isinstance(r, str) for r in b) for b in claim["bases"])
                and isinstance(claim.get("reasons"), list)
                and all(isinstance(r, str) for r in claim["reasons"])
                and type(claim.get("version")) is int and claim["version"] > 0):
            return False
        ids.append(claim["id"])
    return len(ids) == len(set(ids))


def reference_snapshot(episode, stage, previous, oracle):
    """Positive-control writer, private. Not V1; not available to model workers."""
    evidence = active_evidence(episode, stage)
    candidates = oracle.compatible(evidence)
    update = next(u for u in episode["updates"] if u["stage"] == stage)
    reasons = update["add"] + update["revoke"]
    by_id = {c["id"]: c for c in previous}
    current = []
    for initial in episode["claims"]:
        old = by_id[initial["id"]]
        claim = deepcopy(initial)
        claim.update(status=oracle.status(candidates, initial["proposition"]), version=old["version"] + 1,
                     previous_sha256=sha(old), reasons=reasons or [r["id"] for r in evidence],
                     bases=[["e:" + r["id"] for r in evidence]])
        if claim["id"] in episode["registered"]["independent"]:
            claim["bases"] = [["e:EA"]]
        current.append(claim)
    return current


def reference_chain(episode, oracle, representation="S"):
    previous = deepcopy(episode["claims"])
    trace = []
    for stage in "ABCD":
        current = reference_snapshot(episode, stage, previous, oracle)
        trace.append({"stage": stage, "instance_id": "fixture-instance-" + stage,
                      "terminal_status": "completed", "claims": current,
                      "published_memory": memory_envelope(deepcopy(current) if representation == "S"
                                                          else canonical(current).decode("utf-8"), representation)})
        previous = current
    evidence = active_evidence(episode, "E")
    answer = oracle.answer(oracle.compatible(evidence), episode["new_query"])
    trace.append({"stage": "E", "instance_id": "fixture-instance-E", "terminal_status": "completed",
                  "answer": answer, "basis": ["e:" + e["id"] for e in evidence]})
    return trace


def assess_snapshot(episode, stage, previous, current, oracle):
    evidence = active_evidence(episode, stage)
    sources = {e["id"]: e for e in evidence}
    candidates = oracle.compatible(evidence)
    initial = {c["id"]: c for c in episode["claims"]}
    before = {c["id"]: c for c in previous}
    expected = {cid: oracle.status(candidates, c["proposition"]) for cid, c in initial.items()}
    if not valid_claims(current):
        return {"stage": stage, "gates": {g: False for g in "RDANP"}, "expected": expected,
                "valid_measurement": False, **preservation_slots(episode["claims"], None, expected)}
    claims = {c["id"]: c for c in current}
    update = next(u for u in episode["updates"] if u["stage"] == stage)
    changed = set(update["add"] + update["revoke"])
    introduced = set()
    for u in episode["updates"]:
        introduced.update(u["add"])
        if u["stage"] == stage:
            break
    identity = set(initial) <= set(claims) and all(
        canonical(claims[cid]["proposition"]) == canonical(c["proposition"]) for cid, c in initial.items())
    correct = {cid: claims.get(cid, {}).get("status") == status for cid, status in expected.items()}
    trace = identity
    sound = identity
    for cid, claim in claims.items():
        old = before.get(cid)
        if old:
            trace = trace and (claim["version"] == old["version"] + 1
                              and claim.get("previous_sha256") == sha(old)
                              and claim.get("origin") == old["origin"]
                              and canonical(claim["proposition"]) == canonical(old["proposition"]))
            if claim["status"] != old["status"]:
                trace = trace and bool(set(claim["reasons"]) & changed)
        else:
            trace = trace and claim["version"] == 1 and claim.get("previous_sha256") is None
        trace = trace and bool(claim["reasons"]) and set(claim["reasons"]) <= introduced
        try:
            sound = sound and (oracle.status(candidates, claim["proposition"]) == claim["status"]
                               and valid_bases(claim, claims, sources, oracle))
        except (KeyError, TypeError, ValueError, IndexError, RecursionError):
            sound = False
    independent = all(correct[cid] and ["e:EA"] in claims.get(cid, {}).get("bases", [])
                      for cid in episode["registered"]["independent"])
    gates = {"R": all(correct[cid] for cid in episode["registered"]["roots"]),
             "D": all(correct[cid] for cid in episode["registered"]["descendants"]) and bool(sound),
             "A": independent and bool(sound),
             "N": all(correct[cid] for cid, status in expected.items() if status == "supported"),
             "P": bool(trace and sound)}
    return {"stage": stage, "gates": gates, "expected": expected, "valid_measurement": True,
            **preservation_slots(episode["claims"], current, expected),
            "missing_claims": sorted(set(initial) - set(claims))}


def score_chain(episode, trace, oracle, condition="S1"):
    if condition == "C0":
        return {"bri": None, "reason": "no inherited claims available to C0"}
    if condition not in {"F0", "F1", "S0", "S1", "FULL-JOURNAL"}:
        raise ValueError("condition not implemented")
    gates = {g: True for g in "TRDANPQ"}
    ordered = (isinstance(trace, list) and len(trace) == 5 and all(isinstance(r, dict) for r in trace)
               and [r.get("stage") for r in trace] == list("ABCDE"))
    if not ordered:
        trace = [{"stage": stage} for stage in "ABCDE"]
    instances = [r.get("instance_id") for r in trace]
    gates["T"] = (all(isinstance(i, str) and i for i in instances) and len(set(instances)) == 5
                  and all(r.get("terminal_status") == "completed" for r in trace))
    memory_failures = [r["stage"] for r in trace[:-1] if not publication_valid(r, condition)]
    technical = [r.get("terminal_status") == "completed" and isinstance(r.get("instance_id"), str)
                 and bool(r["instance_id"]) and instances.count(r["instance_id"]) == 1
                 and publication_valid(r, condition) and valid_claims(r.get("claims")) for r in trace[:-1]]
    gates["T"] = gates["T"] and all(technical)
    previous = episode["claims"]
    snapshots = []
    for stage, record in zip("ABCD", trace):
        report = assess_snapshot(episode, stage, previous, record.get("claims"), oracle)
        snapshots.append(report)
        for key, value in report["gates"].items():
            gates[key] = gates[key] and value
        if valid_claims(record.get("claims")):
            previous = record["claims"]
        else:
            gates["T"] = False
    final = trace[-1]
    evidence = active_evidence(episode, "E")
    sources = {e["id"]: e for e in evidence}
    candidates = oracle.compatible(evidence)
    expected_answer = oracle.answer(candidates, episode["new_query"])
    answer = final.get("answer")
    gates["Q"] = type(answer) in (int, type(None)) and "answer" in final and answer == expected_answer
    if gates["Q"]:
        answer_claim = {"id": "final-answer", "proposition": {"query": episode["new_query"], "value": answer},
                        "status": "supported" if answer is not None else "undetermined",
                        "bases": [final.get("basis", [])]}
        try:
            # For an unidentifiable numeric answer, use a concrete possible value to test ambiguity.
            if answer is None:
                answer_claim["proposition"]["value"] = oracle.quantity(min(candidates), episode["new_query"])
            gates["Q"] = valid_bases(answer_claim, {c["id"]: c for c in previous}, sources, oracle)
        except (KeyError, TypeError, ValueError, IndexError, RecursionError):
            gates["Q"] = False
    return {"bri": int(all(gates.values())), "gates": gates, "snapshots": snapshots,
            "new_answer_correct": answer == expected_answer and type(answer) in (int, type(None)),
             "technical_complete": gates["T"], "registered_checkpoints": 4,
            "memory_publication_failures": memory_failures,
            "preservation": preservation_summary(snapshots, technical)}


def natural_opportunities(previous, current, previous_evidence, new_evidence, oracle,
                          *, introduced_sources=None, changed_sources=None):
    """Fix denominators from pre-update state even when the successor fails."""
    unknown = {"valid_measurement": False, "revision_rate": None, "opportunities": None,
               "preservation_denominator": None, "items": [], "provenance_valid": False}
    if not valid_claims(previous):
        return {**unknown, "reason": "unreadable predecessor; denominator unknown"}
    before = {c["id"]: c for c in previous}
    current_valid = valid_claims(current)
    after = {c["id"]: c for c in current} if current_valid else {}
    old_sources = {e["id"]: e for e in previous_evidence}
    sources = {e["id"]: e for e in new_evidence}
    introduced = set(old_sources) | set(sources) if introduced_sources is None else set(introduced_sources)
    changed = set(old_sources) ^ set(sources) if changed_sources is None else set(changed_sources)
    try:
        old_models, new_models = oracle.compatible(previous_evidence), oracle.compatible(new_evidence)
        expected = {cid: oracle.status(new_models, c["proposition"]) for cid, c in before.items()}
        roots = [c for c in previous if c["proposition"].get("query", {}).get("kind") in {"model", "edge", "path"}
                 and not any(ref.startswith("c:") for b in c["bases"] for ref in b)]
        truths = {c["id"]: truth_set(oracle, c["proposition"]) for c in roots}
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        return {**unknown, "reason": "uninterpretable predecessor propositions"}
    provenance = current_valid and provenance_valid(previous, current, introduced, changed)
    evidence_valid = current_valid and sound_claims(current, sources, oracle)
    opportunities, preexisting_errors = [], []
    with_dependents = 0
    for root in roots:
        descendants, frontier = set(), [root["id"]]
        while frontier:
            parent = frontier.pop()
            for claim in previous:
                if claim["id"] != root["id"] and claim["id"] not in descendants and any(
                        "c:" + parent in basis for basis in claim["bases"]):
                    descendants.add(claim["id"]); frontier.append(claim["id"])
        with_dependents += bool(descendants)
        old_status = oracle.status(old_models, root["proposition"])
        new_status = expected[root["id"]]
        if descendants and root["status"] != old_status:
            preexisting_errors.append(root["id"])
        if descendants and old_status != new_status:
            ids = [root["id"], *sorted(descendants)]
            statuses = all(cid in after and canonical(after[cid]["proposition"]) == canonical(before[cid]["proposition"])
                           and after[cid]["status"] == expected[cid] for cid in ids)
            opportunities.append({"root": root["id"], "descendants": sorted(descendants),
                                  "erroneous_supported_root": root["status"] == "supported" and new_status != "supported",
                                  "epistemic_status_changed": True, "statuses_correct": statuses,
                                  "correct": bool(statuses and provenance and evidence_valid)})
    return {"valid_measurement": current_valid, "formed_roots": len(roots),
            "falsifiable_roots": sum(bool(t and len(t) < len(oracle.models)) for t in truths.values()),
            "roots_with_dependents": with_dependents, "opportunities": len(opportunities),
            "revision_rate": sum(o["correct"] for o in opportunities) / len(opportunities) if opportunities else None,
            "items": opportunities, "preexisting_error_roots": preexisting_errors,
            "provenance_valid": bool(provenance), "evidence_valid": bool(evidence_valid),
            **preservation_slots(previous, current if current_valid else None, expected),
            "scope": "descriptive observed opportunities, not controlled primary BRI"}


def natural_answer(episode, record, claims, oracle):
    evidence = active_evidence(episode, "E")
    candidates = oracle.compatible(evidence)
    answer = record.get("answer")
    correct = (type(answer) in (int, type(None)) and "answer" in record
               and answer == oracle.answer(candidates, episode["new_query"]))
    basis_valid = False
    if correct:
        claim = {"id": "final-answer", "proposition": {"query": episode["new_query"], "value": answer},
                 "status": "supported" if answer is not None else "undetermined", "bases": [record.get("basis", [])]}
        try:
            if answer is None:
                claim["proposition"]["value"] = oracle.quantity(min(candidates), episode["new_query"])
            basis_valid = valid_bases(claim, {c["id"]: c for c in claims}, {e["id"]: e for e in evidence}, oracle)
        except (KeyError, TypeError, ValueError, IndexError, RecursionError):
            pass
    return correct, basis_valid


def score_natural_chain(episode, trace, oracle, condition="S1"):
    if condition not in {"F0", "F1", "S0", "S1", "FULL-JOURNAL", "C0"}:
        raise ValueError("condition not implemented")
    ordered = (isinstance(trace, list) and len(trace) == 5 and all(isinstance(r, dict) for r in trace)
               and [r.get("stage") for r in trace] == list("ABCDE"))
    if not ordered:
        return {"bri": None, "track": "natural", "technical_complete": False, "revision_rate": None,
                "opportunities": None, "invalid_measurement": True, "reason": "missing/misordered stage"}
    instances = [r.get("instance_id") for r in trace]
    technical = [r.get("terminal_status") == "completed" and isinstance(r.get("instance_id"), str)
                 and bool(r["instance_id"]) and instances.count(r["instance_id"]) == 1 for r in trace]
    publications = [publication_valid(r, condition) for r in trace[:-1]]
    technical[:4] = [ok and pub and valid_claims(r.get("claims"))
                     for r, ok, pub in zip(trace[:-1], technical[:4], publications)]
    introduced, history_valid, snapshots = set(), True, []
    for index, stage in enumerate("ABCD"):
        update = next(u for u in episode["updates"] if u["stage"] == stage)
        introduced.update(update["add"])
        previous = [] if index == 0 or condition == "C0" else trace[index - 1].get("claims")
        current = trace[index].get("claims")
        schema = valid_claims(previous) and valid_claims(current)
        provenance = schema and provenance_valid(previous, current, introduced, set(update["add"] + update["revoke"]))
        history_valid = bool(provenance) and (history_valid or condition == "C0")
        snapshots.append({"stage": stage, "provenance_valid": bool(provenance), "history_valid": history_valid,
                          "valid_measurement": valid_claims(current),
                          "evidence_valid": valid_claims(current) and sound_claims(
                              current, {e["id"]: e for e in active_evidence(episode, stage)}, oracle)})
    final_claims = trace[3].get("claims")
    correct_answer, answer_basis = natural_answer(episode, trace[-1],
                                                 final_claims if valid_claims(final_claims) else [], oracle)
    base = {"bri": None, "track": "natural", "condition": condition, "snapshots": snapshots,
            "technical_complete": all(technical), "new_answer_correct": correct_answer,
            "new_answer_basis_valid": answer_basis, "memory_publication_failures":
                [stage for stage, valid in zip("ABCD", publications) if not valid]}
    if condition == "C0":
        return {**base, "opportunities": None, "revision_rate": None, "preservation": None,
                "reason": "no inherited claims available to C0", "transitions": []}
    transitions, introduced = [], set(episode["updates"][0]["add"])
    for index, stage in enumerate("BCD", 1):
        update = next(u for u in episode["updates"] if u["stage"] == stage)
        introduced.update(update["add"])
        report = natural_opportunities(trace[index - 1].get("claims"), trace[index].get("claims"),
                                       active_evidence(episode, "ABCD"[index - 1]),
                                       active_evidence(episode, stage), oracle,
                                       introduced_sources=introduced, changed_sources=update["add"] + update["revoke"])
        qualified = technical[index - 1] and technical[index] and snapshots[index]["history_valid"]
        for item in report["items"]:
            item["correct"] = bool(item["correct"] and qualified)
        report["revision_rate"] = (sum(i["correct"] for i in report["items"]) / report["opportunities"]
                                   if report["opportunities"] else None)
        transitions.append({"stage": stage, "technical_valid": bool(qualified), **report})
    known = all(r["opportunities"] is not None for r in transitions)
    total = sum(r["opportunities"] or 0 for r in transitions)
    successes = sum(item["correct"] for r in transitions for item in r["items"])
    return {**base, "opportunities": total if known else None, "known_opportunities": total,
            "successful_revisions": successes, "revision_rate": successes / total if known and total else None,
            "post_update_integrity": bool(all(technical) and correct_answer and answer_basis
                                          and all(s["history_valid"] and s["evidence_valid"] for s in snapshots[1:])) if total else None,
            "observed_known_revision_rate": successes / total if total else None, "transitions": transitions,
            "invalid_measurements": sum(not r["valid_measurement"] for r in transitions),
            "preservation": preservation_summary(transitions, [technical[i - 1] and technical[i] for i in (1, 2, 3)])}
