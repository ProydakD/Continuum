"""Private full-chain evaluator and transparent natural-opportunity accounting."""
from copy import deepcopy

from .e009_episode import active_evidence, truth_set
from .e009_revision import canonical, memory_envelope, sha, valid_bases

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
                "valid_measurement": False}
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
            "false_retractions": sum(claims.get(cid, {}).get("status") == "refuted"
                                     for cid, status in expected.items() if status == "supported"),
            "preservation_denominator": sum(status == "supported" for status in expected.values()),
            "missing_claims": sorted(set(initial) - set(claims))}


def score_chain(episode, trace, oracle, condition="S1"):
    if condition == "C0":
        return {"bri": None, "reason": "no inherited claims available to C0"}
    if condition not in {"F0", "F1", "S0", "S1", "FULL-JOURNAL"}:
        raise ValueError("condition not implemented")
    gates = {g: True for g in "TRDANPQ"}
    if not isinstance(trace, list) or [r.get("stage") for r in trace if isinstance(r, dict)] != list("ABCDE"):
        return {"bri": 0, "gates": {g: False for g in gates}, "reason": "missing/misordered stage"}
    instances = [r.get("instance_id") for r in trace]
    gates["T"] = (all(isinstance(i, str) and i for i in instances) and len(set(instances)) == 5
                  and all(r.get("terminal_status") == "completed" for r in trace))
    memory_failures = []
    if condition != "FULL-JOURNAL":
        representation = "S" if condition.startswith("S") else "F"
        for record in trace[:-1]:
            memory = record.get("published_memory")
            try:
                valid_memory = (isinstance(memory, dict) and set(memory) == {"format", "payload"}
                                and memory["format"] == representation and bool(memory["payload"])
                                and memory_envelope(memory["payload"], representation) == memory)
            except (KeyError, TypeError, ValueError):
                valid_memory = False
            if not valid_memory:
                memory_failures.append(record["stage"])
        gates["T"] = gates["T"] and not memory_failures
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
            "memory_publication_failures": memory_failures}


def natural_opportunities(previous, current, previous_evidence, new_evidence, oracle):
    """Descriptive denominators. An absent/error-free root is never a successful repair."""
    if not valid_claims(previous) or not valid_claims(current):
        return {"valid_measurement": False, "revision_rate": None, "opportunities": None}
    before = {c["id"]: c for c in previous}
    after = {c["id"]: c for c in current}
    old_models, new_models = oracle.compatible(previous_evidence), oracle.compatible(new_evidence)
    roots = [c for c in previous if c["proposition"].get("query", {}).get("kind") in {"model", "edge", "path"}
             and not any(ref.startswith("c:") for b in c["bases"] for ref in b)]
    opportunities, preexisting_errors = [], []
    falsifiable, with_dependents = 0, 0
    for root in roots:
        truths = truth_set(oracle, root["proposition"])
        falsifiable += bool(truths and len(truths) < len(oracle.models))
        descendants, frontier = set(), [root["id"]]
        while frontier:
            parent = frontier.pop()
            for claim in previous:
                if claim["id"] != root["id"] and claim["id"] not in descendants and any(
                        "c:" + parent in basis for basis in claim["bases"]):
                    descendants.add(claim["id"]); frontier.append(claim["id"])
        with_dependents += bool(descendants)
        old_status = oracle.status(old_models, root["proposition"])
        new_status = oracle.status(new_models, root["proposition"])
        if descendants and root["status"] != old_status:
            preexisting_errors.append(root["id"])
        if descendants and old_status != new_status:
            ids = [root["id"], *sorted(descendants)]
            sources = {e["id"]: e for e in new_evidence}
            correct = all(cid in after and canonical(after[cid]["proposition"]) == canonical(before[cid]["proposition"])
                          and after[cid]["status"] == oracle.status(new_models, before[cid]["proposition"])
                          and valid_bases(after[cid], after, sources, oracle) for cid in ids)
            opportunities.append({"root": root["id"], "descendants": sorted(descendants),
                                  "erroneous_supported_root": root["status"] == "supported" and new_status != "supported",
                                  "epistemic_status_changed": old_status != new_status, "correct": correct})
    return {"valid_measurement": True, "formed_roots": len(roots), "falsifiable_roots": falsifiable,
            "roots_with_dependents": with_dependents, "opportunities": len(opportunities),
            "revision_rate": sum(o["correct"] for o in opportunities) / len(opportunities) if opportunities else None,
            "items": opportunities, "preexisting_error_roots": preexisting_errors,
            "scope": "descriptive observed opportunities, not controlled primary BRI"}


def score_natural_chain(episode, trace, oracle):
    if not isinstance(trace, list) or [r.get("stage") for r in trace] != list("ABCDE"):
        return {"bri": None, "technical_complete": False, "revision_rate": None, "invalid_measurement": True}
    stages, total, successes = [], 0, 0
    for index, stage in enumerate("BCD", 1):
        try:
            report = natural_opportunities(trace[index - 1].get("claims"), trace[index].get("claims"),
                                           active_evidence(episode, "ABCD"[index - 1]),
                                           active_evidence(episode, stage), oracle)
        except (KeyError, TypeError, ValueError, IndexError, RecursionError):
            report = {"valid_measurement": False, "revision_rate": None, "opportunities": None}
        stages.append({"stage": stage, **report})
        if report["valid_measurement"]:
            total += report["opportunities"]
            successes += sum(item["correct"] for item in report["items"])
    answer = trace[-1].get("answer")
    instances = [r.get("instance_id") for r in trace]
    return {"bri": None, "track": "natural", "opportunities": total,
            "revision_rate": successes / total if total else None, "transitions": stages,
            "technical_complete": all(r.get("terminal_status") == "completed" for r in trace)
                                  and all(isinstance(i, str) and i for i in instances) and len(set(instances)) == 5,
            "new_answer_correct": type(answer) in (int, type(None)) and "answer" in trace[-1]
                                  and answer == oracle.answer(oracle.compatible(active_evidence(episode, "E")), episode["new_query"]),
            "invalid_measurements": sum(not s["valid_measurement"] for s in stages)}
