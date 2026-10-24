"""Shared observable provenance and conservative preservation accounting, not an oracle for workers."""
import json

from .e009_revision import canonical, memory_envelope, sha, valid_bases


def provenance_valid(previous, current, introduced, changed):
    before = {c["id"]: c for c in previous}
    after = {c["id"]: c for c in current}
    if not set(before) <= set(after):
        return False
    for claim in current:
        old = before.get(claim["id"])
        if not isinstance(claim.get("origin"), str) or not claim["origin"]:
            return False
        if not claim["reasons"] or not set(claim["reasons"]) <= introduced:
            return False
        if old is None:
            if claim["version"] != 1 or claim.get("previous_sha256") is not None:
                return False
        else:
            if (claim["version"] != old["version"] + 1 or claim.get("previous_sha256") != sha(old)
                    or claim["origin"] != old.get("origin")
                    or canonical(claim["proposition"]) != canonical(old["proposition"])):
                return False
            if claim["status"] != old["status"] and not set(claim["reasons"]) & changed:
                return False
    return True


def sound_claims(claims, sources, oracle):
    by_id = {c["id"]: c for c in claims}
    candidates = oracle.compatible(list(sources.values()))
    try:
        return all(oracle.status(candidates, c["proposition"]) == c["status"]
                   and valid_bases(c, by_id, sources, oracle) for c in claims)
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        return False


def publication_valid(record, condition):
    representation = "S" if condition.startswith("S") else "F"
    memory = record.get("published_memory")
    try:
        json.dumps(memory, allow_nan=False)
        return (isinstance(memory, dict) and set(memory) == {"format", "payload"}
                and memory["format"] == representation and bool(memory["payload"])
                and memory_envelope(memory["payload"], representation) == memory)
    except (KeyError, TypeError, ValueError):
        return False


def preservation_slots(registered, current, expected):
    """Denominator depends on assigned propositions/oracle, never on current output success."""
    after = {c["id"]: c for c in current} if current is not None else {}
    slots = []
    for old in registered:
        if expected[old["id"]] != "supported":
            continue
        claim = after.get(old["id"])
        identity = claim is not None and canonical(claim["proposition"]) == canonical(old["proposition"])
        retained = identity and claim["status"] == "supported"
        slots.append({"id": old["id"], "retained": bool(retained),
                      "explicit_refutation": bool(identity and claim["status"] == "refuted"),
                      "missing_or_redefined": not identity})
    return {"false_retractions": sum(not s["retained"] for s in slots),
            "explicit_false_refutations": sum(s["explicit_refutation"] for s in slots),
            "missing_or_redefined_supported": sum(s["missing_or_redefined"] for s in slots),
            "preservation_denominator": len(slots), "preservation_slots": slots}


def preservation_summary(reports, technical):
    known = [r.get("preservation_denominator") is not None for r in reports]
    denominator = sum(r["preservation_denominator"] for r, k in zip(reports, known) if k)
    losses = sum(r["false_retractions"] for r, k in zip(reports, known) if k)
    worst = sum(r["false_retractions"] if ok and r.get("valid_measurement") else r["preservation_denominator"]
                for r, ok, k in zip(reports, technical, known) if k)
    observed = [(r, ok) for r, ok, k in zip(reports, technical, known) if k and ok and r.get("valid_measurement")]
    conditional_n = sum(r["preservation_denominator"] for r, _ in observed)
    conditional_losses = sum(r["false_retractions"] for r, _ in observed)
    complete = all(known)
    return {"denominator": denominator if complete else None, "known_denominator": denominator,
            "losses": losses, "worst_case_losses": worst, "unassessable_transitions": sum(not k for k in known),
            "worst_case_rate": worst / denominator if complete and denominator else None,
            "conditional_denominator": conditional_n,
            "conditional_rate": conditional_losses / conditional_n if conditional_n else None}
