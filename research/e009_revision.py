"""Формальный V1 и отдельный private BRI evaluator. Не выполняет память как код."""
from copy import deepcopy
import hashlib
import json


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def check_references(claims, active_sources, changed_claims=()):
    """V1 получает только публичные IDs/status/bases. Не меняет ни одного статуса."""
    ids = [c["id"] for c in claims]
    notices = []
    if len(ids) != len(set(ids)):
        notices.append({"kind": "duplicate_claim_id"})
    by_id = {c["id"]: c for c in claims}
    changed = set(changed_claims)
    pending = list(changed)
    while pending:
        source = pending.pop()
        for claim in claims:
            if claim["id"] not in changed and any("c:" + source in b for b in claim["bases"]):
                changed.add(claim["id"])
                pending.append(claim["id"])
    for claim in claims:
        cid = claim["id"]
        if cid in changed - set(changed_claims):
            notices.append({"kind": "reevaluate_dependency", "claim": cid})
        for basis in claim["bases"]:
            for ref in basis:
                if ref.startswith("e:") and ref[2:] not in active_sources:
                    notices.append({"kind": "missing_source", "claim": cid, "reference": ref})
                elif ref.startswith("c:"):
                    parent = by_id.get(ref[2:])
                    if parent is None or parent["status"] != "supported":
                        notices.append({"kind": "inactive_premise", "claim": cid, "reference": ref})
                elif not ref.startswith("e:"):
                    notices.append({"kind": "invalid_reference", "claim": cid, "reference": ref})
    return notices


def public_input(world, stage, memory, condition):
    """Allowlist projection: hidden model, gold и measurement не сериализуются."""
    if stage not in "ABCDE" or len(stage) != 1:
        raise ValueError("invalid stage")
    if condition not in {"F0", "F1", "S0", "S1", "C0", "FULL-JOURNAL"}:
        raise ValueError("condition not implemented")
    number = min("ABCDE".index(stage), 3)
    value = {"world_id": world["id"], "stage": stage, "condition": condition,
             "evidence": deepcopy(world["evidence"][:number + 1] if condition == "FULL-JOURNAL"
                                  else [world["evidence"][number]]),
             "memory": None if condition == "C0" else deepcopy(memory)}
    if stage == "E":
        value["question"] = deepcopy(world["new_query"])
    return value


def memory_envelope(payload, representation, limit=8192):
    if representation not in {"F", "S"}:
        raise ValueError("unsupported representation")
    if representation == "F" and not isinstance(payload, str):
        raise ValueError("F must be free text")
    if representation == "S" and not isinstance(payload, list):
        raise ValueError("S must be a list of claims")
    result = {"format": representation, "payload": payload}
    if len(canonical(result)) > limit:
        raise ValueError("full serialized memory envelope exceeds limit")
    return result


def valid_bases(claim, claims, sources, oracle, visiting=frozenset()):
    if claim["id"] in visiting or not claim["bases"]:
        return False
    visiting = visiting | {claim["id"]}
    # Every declared active basis must be sound; a good alternative cannot launder a stale one.
    for basis in claim["bases"]:
        if not basis or len(basis) != len(set(basis)):
            return False
        records, parents = [], []
        for ref in basis:
            if ref.startswith("e:") and ref[2:] in sources:
                records.append(sources[ref[2:]])
            elif ref.startswith("c:") and ref[2:] in claims:
                parent = claims[ref[2:]]
                if parent["status"] != "supported" or not valid_bases(parent, claims, sources, oracle, visiting):
                    return False
                parents.append(parent["proposition"])
            else:
                return False
        candidates = oracle.compatible(records)
        for parent in parents:
            candidates = frozenset(i for i in candidates
                                  if oracle.status({i}, parent) == "supported")
        if not candidates or oracle.status(candidates, claim["proposition"]) != claim["status"]:
            return False
    return True


def score_revision(world, current, history, answer, oracle, completed=True):
    """Один зарегистрированный controlled checkpoint; не полный live evaluator."""
    valid = isinstance(current, list) and isinstance(history, list)
    for claim in current if isinstance(current, list) else []:
        valid = valid and isinstance(claim, dict)
        if not valid:
            break
        valid = (isinstance(claim.get("id"), str) and type(claim.get("version")) is int
                 and isinstance(claim.get("status"), str)
                 and claim["status"] in {"supported", "refuted", "undetermined", "conflicted"}
                 and isinstance(claim.get("bases"), list)
                 and all(isinstance(b, list) and all(isinstance(r, str) for r in b) for b in claim["bases"])
                 and isinstance(claim.get("proposition"), dict)
                 and isinstance(claim.get("reasons"), list)
                 and all(isinstance(r, str) for r in claim["reasons"]))
    if not valid:
        return {"bri": 0, "gates": {key: False for key in "TRDANPQ"}, "invalid_measurement": True}
    before = {c["id"]: c for c in world["claims"]}
    claims = {c["id"]: c for c in current}
    sources = {r["id"]: r for r in world["evidence"][:3]}
    compatible = oracle.compatible(list(sources.values()))
    expected = {cid: oracle.status(compatible, c["proposition"]) for cid, c in before.items()}
    schema = len(claims) == len(current) and set(claims) == set(before)
    statuses = {cid: claims.get(cid, {}).get("status") == status for cid, status in expected.items()}
    trace = schema
    for cid, old in before.items():
        new = claims.get(cid, {})
        trace = trace and (new.get("version") == old["version"] + 1
                          and new.get("previous_sha256") == sha(old)
                          and canonical(new.get("proposition")) == canonical(old["proposition"])
                          and new.get("origin") == old["origin"]
                          and any(canonical(old) == canonical(record) for record in history)
                          and bool(new.get("reasons"))
                          and set(new["reasons"]) <= set(sources))
    identities = schema and all(canonical(claims[cid]["proposition"]) == canonical(old["proposition"])
                                for cid, old in before.items())
    proofs = identities and all(valid_bases(c, claims, sources, oracle) for c in current)
    independent = schema and all(["e:EA"] in claims[cid]["bases"] for cid in ("K", "I"))
    gates = {"T": bool(completed and schema), "R": statuses["H"],
             "D": statuses["D1"] and statuses["D2"] and proofs,
             "A": statuses["K"] and statuses["I"] and proofs and independent,
             "N": all(statuses[cid] for cid, status in expected.items() if status == "supported"),
             "P": bool(trace and proofs),
             "Q": type(answer) in (int, type(None)) and answer == oracle.answer(compatible, world["new_query"])}
    return {"bri": int(all(gates.values())), "gates": gates, "expected": expected,
            "scope": "offline controlled checkpoint, not full A-E live chain"}


def reference_revision(world, oracle):
    """Private positive control; never available to V1 or model workers."""
    sources = world["evidence"][:3]
    candidates = oracle.compatible(sources)
    current = []
    for old in world["claims"]:
        new = deepcopy(old)
        new.update(version=old["version"] + 1, previous_sha256=sha(old),
                   status=oracle.status(candidates, old["proposition"]),
                   reasons=[r["id"] for r in sources], bases=[["e:" + r["id"] for r in sources]])
        if old["id"] in ("K", "I"):
            new["bases"] = [["e:EA"]]
        current.append(new)
    return current, deepcopy(world["claims"]), oracle.answer(candidates, world["new_query"])
