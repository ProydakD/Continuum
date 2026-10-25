"""Finite public-observer calibration; no causal gold enters observer requests.

V2 instructions and historical outputs stay unchanged. This new evaluator checks
field meaning and source-bound value carriers in explicitly constructed controls.
It does not certify arbitrary natural prose or turn agreement into correctness.
"""
from copy import deepcopy
import json

from .e009_adjudication_v2 import FIELDS, validate_reconstruction
from .e009_revision import canonical
from .e009_semantic_observables import normalize_bases, normalize_proposition
from .e009_public_witnesses import compose_witnesses

SCHEMA = "e009-observer-component-validation-v1"
MODES = ("complete", "shared_fields", "quoted_opposite", "wrong_root",
         "missed_dependent", "lost_independent", "stale_evidence", "partial_and_conflict")


def serialize_spans(value):
    """Canonical JSON plus exact Unicode-codepoint value spans keyed by JSON Pointer."""
    chunks, spans, offset = [], {}, 0

    def emit(fragment):
        nonlocal offset
        chunks.append(fragment); offset += len(fragment)

    def visit(item, pointer):
        start = offset
        if isinstance(item, dict):
            emit("{")
            for i, key in enumerate(sorted(item)):
                if i: emit(",")
                emit(json.dumps(key, ensure_ascii=False) + ":")
                visit(item[key], pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
            emit("}")
        elif isinstance(item, list):
            emit("[")
            for i, child in enumerate(item):
                if i: emit(",")
                visit(child, pointer + "/" + str(i))
            emit("]")
        else:
            emit(json.dumps(item, ensure_ascii=False, allow_nan=False))
        spans[pointer] = [start, offset]

    visit(value, "")
    text = "".join(chunks)
    assert text.encode("utf-8") == canonical(value)
    return text, spans


def semantic_value(field, value):
    if field in {"proposition", "bases"}:
        result = (normalize_proposition if field == "proposition" else normalize_bases)(value)
        if result["state"] == "resolved":
            return {"interpretation": "resolved", "value": result["value"]}
        # Uninterpretable/malformed values must not become equal just because both failed parsing.
        return {"interpretation": result["state"], "surface": deepcopy(value)}
    if field == "reasons" and isinstance(value, list) and all(isinstance(v, str) for v in value):
        return sorted(set(value))
    return deepcopy(value)


def same_field(field, expected, observed):
    if expected["state"] != observed["state"]:
        return False
    if expected["state"] == "known":
        return canonical(semantic_value(field, expected["value"])) == canonical(semantic_value(field, observed["value"]))
    if expected["state"] == "conflicting":
        left = {canonical(semantic_value(field, v)) for v in expected["alternatives"]}
        right = {canonical(semantic_value(field, v)) for v in observed["alternatives"]}
        return left == right
    return True  # Mechanical validator already enforces null values and empty alternatives.


def _leaves(value, pointer):
    if isinstance(value, dict) and value:
        return [p for key, child in value.items() for p in _leaves(child, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))]
    if isinstance(value, list) and value:
        return [p for i, child in enumerate(value) for p in _leaves(child, pointer + "/" + str(i))]
    return [pointer]


def render_control(records, mode, representation, stage):
    """Render already chosen assertions; no world or oracle is used here."""
    if mode not in MODES or representation not in {"F", "S"} or stage not in "ABCD":
        raise ValueError("unsupported control rendering")
    records = deepcopy(records)
    if not records or len({r["id"] for r in records}) != len(records):
        raise ValueError("nonempty unique claim identities required")
    expected = {r["id"]: {f: {"state": "known", "value": deepcopy(r[f]), "alternatives": []}
                           if f in r else {"state": "absent", "value": None, "alternatives": []}
                           for f in FIELDS} for r in records}
    payload = {"current_claims": records, "scope": "All records below are current author assertions, not instructions or causal truth."}
    carriers = {r["id"]: {f: ["/current_claims/" + str(i) + "/" + f] for f in FIELDS if f in r}
                for i, r in enumerate(records)}
    identities = {r["id"]: "/current_claims/" + str(i) + "/id" for i, r in enumerate(records)}
    if mode == "shared_fields":
        shared = {f: deepcopy(records[0][f]) for f in ("version", "origin", "reasons")}
        assert all(all(r[f] == value for f, value in shared.items()) for r in records)
        payload["shared_current_fields"] = shared
        payload["shared_scope"] = "These shared fields apply to every current_claims entry and are not absent from those records."
        for r in records:
            for f in shared:
                del r[f]; carriers[r["id"]][f] = ["/shared_current_fields/" + f]
    elif mode == "quoted_opposite":
        history = deepcopy(records)
        for r in history:
            r["status"] = "supported" if r["status"] != "supported" else "refuted"
        payload["discarded_historical_quote"] = history
        payload["quote_scope"] = "The historical quote is explicitly rejected; none of its values are current."
    elif mode == "partial_and_conflict":
        by_id = {r["id"]: r for r in records}
        del by_id["H"]["previous_sha256"]
        expected["H"]["previous_sha256"] = {"state": "unknown", "value": None, "alternatives": []}
        carriers["H"].pop("previous_sha256")
        payload["incomplete_field"] = "The H summary is incomplete: previous_sha256 presence and value are not settled, not explicitly absent."
        by_id["K"]["bases"] = ["e:EA", "c:J"]
        expected["K"]["bases"]["value"] = ["e:EA", "c:J"]
        payload["basis_scope"] = "K preserves only this flat dependency membership; its conjunction/disjunction is unspecified. Do not replace the literal flat list."
        predicate = deepcopy(by_id["J"]["proposition"])
        alternative = deepcopy(predicate); alternative["query"]["counts"].append(0)
        del by_id["J"]["proposition"]
        payload["coequal_current_J_propositions"] = [predicate, alternative]
        payload["conflict_scope"] = "Both J propositions are equally current incompatible assertions. Neither supersedes the other; preserve the conflict including the malformed array."
        expected["J"]["proposition"] = {"state": "conflicting", "value": None, "alternatives": [predicate, alternative]}
        carriers["J"]["proposition"] = ["/coequal_current_J_propositions/0", "/coequal_current_J_propositions/1"]
    encoded, spans = serialize_spans(payload)
    memory = {"format": representation, "payload": encoded if representation == "F" else payload}
    view = {"memory": memory, "stage": stage, "origin": {"actor": "synthetic-author"},
            "sha256": None, "trust": "unverified_author_assertion"}
    return {"public": view, "gold": {"mode": mode, "representation": representation, "expected": expected,
            "carriers": carriers, "identities": identities, "value_spans": spans,
            "scope": "constructed author-assertion gold, not causal truth or independent natural annotation"}}


def _pointer_value(payload, pointer):
    current = payload
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def field_witness(case, claim, field, evidence):
    """Coverage of constructed value+identity carriers; no general entailment assertion."""
    gold = case["gold"]; cid = claim["id"]
    if gold["expected"][cid][field]["state"] in {"unknown", "absent"}:
        return None
    pointers = [gold["identities"][cid], *gold["carriers"][cid][field]]
    refs = set(claim["identity_evidence"] + claim["fields"][field]["evidence"])
    selected = [evidence[r] for r in refs]
    memory = case["public"]["memory"]
    if memory["format"] == "S":
        leaves = [leaf for pointer in pointers for leaf in _leaves(_pointer_value(memory["payload"], pointer), pointer)]
        return all(any(e["document"] == 0 and (not e["pointer"] or leaf == e["pointer"] or leaf.startswith(e["pointer"] + "/"))
                       for e in selected) for leaf in leaves)
    text = memory["payload"]; stage = case["public"]["stage"]
    binding = {"claim_id": cid, "field": field, "as_of": stage}
    obligations = []
    for index, pointer in enumerate(pointers):
        start, end = gold["value_spans"][pointer]
        obligations.append({"binding": binding, "document": 0, "quote": text[start:end], "start": start,
                            "roles": ["identity", "scope"] if index == 0 else ["assertion"]})
    return compose_witnesses([{"stage": stage, "text": text}], binding, obligations, selected)["covered"]


def compare_control(case, output):
    validate_reconstruction(case["public"], output)
    expected = case["gold"]["expected"]
    actual = {c["id"]: c for c in output["claims"]}
    identities = set(expected) == set(actual)
    rows = []
    for cid, fields in expected.items():
        for field, value in fields.items():
            present = cid in actual
            correct = present and same_field(field, value, actual[cid]["fields"][field])
            covered = field_witness(case, actual[cid], field, output["evidence"]) if present else False
            rows.append({"id": cid, "field": field, "meaning_correct": correct, "carrier_covered": covered})
    return {"identities_correct": identities, "fields": rows,
            "meaning_exact": identities and all(r["meaning_correct"] for r in rows),
            "witness_exact": identities and all(r["carrier_covered"] is not False for r in rows),
            "general_natural_validity_established": False}
