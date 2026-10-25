"""Development component assessments: public observations never filled by causal gold."""
from copy import deepcopy

from .e009_episode import active_evidence
from .e009_revision import canonical, sha
from .e009_semantic_observables import (BRI_COMPONENTS, integrity_bounds,
                                       normalize_bases, normalize_proposition)

SCHEMA = "e009-component-assessment-v1"


def tri_all(values):
    """A witnessed failure survives unknowns; an empty panel is not a success."""
    values = list(values)
    if any(value is not None and type(value) is not bool for value in values):
        raise ValueError("boolean or unknown component required")
    return False if False in values else None if not values or None in values else True


def compare_public_status(observed, proposition, expected_status):
    """Compare a separately supplied reference with an explicit public observation.

    The caller must establish public extraction provenance separately. This
    function does not certify entailment, and reference values cannot fill gaps.
    """
    if expected_status not in {"supported", "refuted", "undetermined"}:
        raise ValueError("reference status outside causal vocabulary")
    if observed is None:
        return {"correct": None, "reason": "public claim unobserved"}
    identity = observed.get("proposition", {})
    status = observed.get("status", {})
    if identity.get("state") == "absent" or status.get("state") == "absent":
        return {"correct": False, "reason": "required public field explicitly absent"}
    if identity.get("state") != "known":
        return {"correct": None, "reason": "public proposition not resolved"}
    if canonical(identity["value"]) != canonical(proposition):
        return {"correct": False, "reason": "public proposition differs from registered identity"}
    if status.get("state") != "known":
        return {"correct": None, "reason": "public status not resolved"}
    return {"correct": status["value"] == expected_status,
            "observed_status": deepcopy(status["value"]), "expected_status": expected_status,
            "reason": "explicit public status compared with separate reference"}


def explicit_record(record):
    """Adapter for a literal public object, not a recovered private measurement."""
    return {**{name: {"state": "known", "value": deepcopy(value)} for name, value in record.items()},
            "record_sha256": {"state": "known", "value": sha(record)}}


def candidate_fields(record):
    """Literal candidate object with framing unresolved: omission is not absence."""
    fields = explicit_record(record)
    required = ("proposition", "status", "bases", "version", "origin", "reasons", "previous_sha256")
    missing = [name for name in required if name not in record]
    for name in missing:
        fields[name] = {"state": "unknown", "value": None}
    if missing:
        fields["record_sha256"] = {"state": "unknown", "value": None,
                                    "reason": "partial object may inherit fields from surrounding prose"}
    for name, normalizer in (("proposition", normalize_proposition), ("bases", normalize_bases)):
        if fields[name]["state"] == "known":
            normalized = normalizer(fields[name]["value"])
            fields[name] = ({"state": "known", "value": normalized["value"]}
                            if normalized["state"] == "resolved" else
                            {"state": normalized["state"], "value": None, "surface": fields[name]["value"]})
    return fields


def _known(claim, field):
    value = (claim or {}).get(field, {})
    return value.get("state") == "known", value.get("value")


def basis_sound(identity, claims, sources, oracle, visiting=frozenset()):
    """Three-valued proof check; every active alternative must be sound.

    Unknown parents are not false premises, and a sound alternative cannot hide
    a definitely revoked source or a cycle in another declared active basis.
    """
    if identity in visiting:
        return False
    claim = claims.get(identity)
    if any((claim or {}).get(name, {}).get("state") == "absent" for name in ("proposition", "status", "bases")):
        return False
    fields = [_known(claim, name) for name in ("proposition", "status", "bases")]
    if not all(known for known, _ in fields):
        return None
    proposition, status, bases = [value for _, value in fields]
    if not isinstance(bases, list) or not bases:
        return False
    results = []
    for basis in bases:
        if not isinstance(basis, list) or not basis or any(not isinstance(r, str) for r in basis):
            results.append(False)
            continue
        records, parents, checks = [], [], []
        for ref in basis:
            if ref.startswith("e:"):
                checks.append(ref[2:] in sources)
                if ref[2:] in sources:
                    records.append(sources[ref[2:]])
            elif ref.startswith("c:"):
                parent = claims.get(ref[2:])
                known, parent_status = _known(parent, "status")
                checks.append(parent_status == "supported" if known else None)
                checks.append(basis_sound(ref[2:], claims, sources, oracle, visiting | {identity}))
                known, predicate = _known(parent, "proposition")
                checks.append(True if known else None)
                if known:
                    parents.append(predicate)
            else:
                checks.append(False)
        ready = tri_all(checks)
        if ready is not True:
            results.append(ready)
            continue
        try:
            candidates = oracle.compatible(list({r["id"]: r for r in records}.values()))
            for parent in parents:
                candidates = frozenset(i for i in candidates if oracle.status({i}, parent) == "supported")
            results.append(bool(candidates) and oracle.status(candidates, proposition) == status)
        except (KeyError, TypeError, ValueError, IndexError, RecursionError):
            results.append(None)  # Uninterpretable public predicate, not gold-repaired data.
    return tri_all(results)


def _field_test(claim, field, predicate):
    if (claim or {}).get(field, {}).get("state") == "absent":
        return False
    known, value = _known(claim, field)
    if not known:
        return None
    try:
        return bool(predicate(value))
    except (TypeError, ValueError):
        return False


def provenance_check(before, after, introduced, changed):
    """Exact predecessor identity is evaluated only when publicly observed."""
    checks = [_field_test(after, "reasons", lambda v: isinstance(v, list) and bool(v)
                          and all(isinstance(x, str) for x in v) and set(v) <= set(introduced))]
    for field in ("origin", "proposition"):
        known, value = _known(before, field)
        checks.append(_field_test(after, field, lambda v: canonical(v) == canonical(value)) if known else None)
    known, version = _known(before, "version")
    checks.append(_field_test(after, "version", lambda v: type(v) is int and type(version) is int
                              and v == version + 1) if known else None)
    known, predecessor = _known(before, "record_sha256")
    checks.append(_field_test(after, "previous_sha256", lambda v: v == predecessor) if known else None)
    old_known, old_status = _known(before, "status")
    new_known, new_status = _known(after, "status")
    if not old_known or not new_known:
        checks.append(None)
    elif old_status != new_status:
        checks.append(_field_test(after, "reasons", lambda v: bool(set(v) & set(changed))))
    return tri_all(checks)


def assess_controlled_checkpoint(episode, stage, before, current, oracle):
    """Conditional on supplied public annotations; controlled panel fixed by design."""
    sources = {e["id"]: e for e in active_evidence(episode, stage)}
    candidates = oracle.compatible(list(sources.values()))
    expected = {c["id"]: oracle.status(candidates, c["proposition"]) for c in episode["claims"]}
    checks = {c["id"]: compare_public_status(current.get(c["id"]), c["proposition"], expected[c["id"]])
              for c in episode["claims"]}
    proofs = {cid: basis_sound(cid, current, sources, oracle) for cid in expected}
    introduced, changed = set(), None
    for update in episode["updates"]:
        introduced.update(update["add"])
        if update["stage"] == stage:
            changed = set(update["add"] + update["revoke"])
            break
    if changed is None:
        raise ValueError("stage missing from registered source timeline")
    trace = {cid: provenance_check(before.get(cid), current.get(cid), introduced, changed) for cid in expected}
    independent = {}
    for cid in episode["registered"]["independent"]:
        independent[cid] = _field_test(current.get(cid), "bases", lambda v: ["e:EA"] in v)
    components = {
        "root_revision": tri_all(checks[cid]["correct"] for cid in episode["registered"]["roots"]),
        "dependent_revision": tri_all(v for cid in episode["registered"]["descendants"]
                                       for v in (checks[cid]["correct"], proofs[cid])),
        "independent_support": tri_all(v for cid in episode["registered"]["independent"]
                                        for v in (checks[cid]["correct"], proofs[cid], independent[cid])),
        "no_false_retraction": tri_all(checks[cid]["correct"] for cid, status in expected.items()
                                        if status == "supported"),
        "traceability": tri_all(list(trace.values()) + list(proofs.values())),
        "new_prediction": None,
    }
    return {"schema": SCHEMA, "stage": stage, "components": components, "status_checks": checks,
            "proof_checks": proofs, "trace_checks": trace, "independent_checks": independent,
            "reference_expected": expected, "active_sources": sorted(sources),
            "annotation_semantics_verified": False, "registered_bri_rescored": False}


def assess_prediction(episode, final, current, oracle):
    sources = {e["id"]: e for e in active_evidence(episode, "E")}
    candidates = oracle.compatible(list(sources.values()))
    expected = oracle.answer(candidates, episode["new_query"])
    known, answer = _known(final, "answer")
    if not known:
        return {"correct": None, "reason": "public answer unobserved"}
    if type(answer) not in (int, type(None)) or answer != expected:
        return {"correct": False, "reason": "public answer differs from causal reference"}
    known, basis = _known(final, "basis")
    if not known:
        return {"correct": None, "reason": "public answer basis unobserved"}
    value = oracle.quantity(min(candidates), episode["new_query"]) if answer is None else answer
    identity = "__public_prediction__"
    if identity in current:
        raise ValueError("reserved prediction ID collision")
    claim = explicit_record({"proposition": {"query": episode["new_query"], "value": value},
                             "status": "undetermined" if answer is None else "supported", "bases": [basis]})
    return {"correct": basis_sound(identity, {**current, identity: claim}, sources, oracle),
            "expected": expected, "reason": "public answer and basis checked separately from memory"}


def controlled_chain_bounds(checkpoints, prediction, technical):
    if len(checkpoints) != 4 or [r["stage"] for r in checkpoints] != list("ABCD"):
        raise ValueError("all four assigned checkpoints required")
    if type(technical) is not bool:
        raise ValueError("observed technical completion must be explicit")
    components = {name: tri_all(r["components"][name] for r in checkpoints) for name in BRI_COMPONENTS}
    components["new_prediction"] = prediction["correct"]
    bounds = integrity_bounds(components)
    return {"conditional_component_bounds": bounds, "technical_complete": technical,
            "assigned_outcome_bounds": {"lower": bounds["lower"] if technical else 0,
                                         "upper": bounds["upper"] if technical else 0},
            "annotation_semantics_verified": False, "registered_bri_rescored": False}


def public_opportunities(before, previous_evidence, new_evidence, oracle):
    """Pre-update observable denominator; no successor output can select it away."""
    old_models, new_models = oracle.compatible(previous_evidence), oracle.compatible(new_evidence)
    roots, unknown, rows = [], [], []
    for cid, claim in before.items():
        kp, proposition = _known(claim, "proposition"); kb, bases = _known(claim, "bases")
        if not kp or not kb:
            unknown.append(cid)
            continue
        try:
            if proposition["query"]["kind"] not in {"model", "edge", "path"}:
                continue
            if any(ref.startswith("c:") for b in bases for ref in b):
                continue
            old = oracle.status(old_models, proposition); new = oracle.status(new_models, proposition)
        except (KeyError, TypeError, ValueError, IndexError):
            unknown.append(cid)
            continue
        roots.append(cid); descendants, frontier, dependency_unknown = set(), [cid], set()
        while frontier:
            parent = frontier.pop()
            for child, item in before.items():
                known, child_bases = _known(item, "bases")
                if not known:
                    dependency_unknown.add(child)
                    continue
                if child != cid and child not in descendants and any("c:" + parent in b for b in child_bases):
                    descendants.add(child); frontier.append(child)
        ks, asserted = _known(claim, "status")
        rows.append({"root": cid, "descendants": sorted(descendants), "dependency_unknown": sorted(dependency_unknown),
                     "falsifiable": oracle.status(range(len(oracle.models)), proposition) == "undetermined",
                     "reference_before": old, "reference_after": new, "evidence_status_changed": old != new,
                     "observed_before": asserted if ks else None,
                     "supported_no_longer_justified": asserted == "supported" and new != "supported" if ks else None,
                     "supported_now_refuted": asserted == "supported" and new == "refuted" if ks else None,
                     "preexisting_status_error": asserted != old if ks else None,
                     "opportunity": old != new and bool(descendants) if descendants or not dependency_unknown else None})
    return {"formed_roots": len(roots), "unresolved_root_candidates": unknown, "items": rows,
            "observed_opportunities": sum(r["opportunity"] is True for r in rows),
            "enumeration_verified": False, "annotation_semantics_verified": False}
