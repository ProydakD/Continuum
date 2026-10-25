"""Offline public-observable amendment, not a replacement BRI scorer.

The public vocabulary is protocol v3 (e009_protocol.py), not a hidden SCM.
Normalization describes an assertion; it never decides whether it is true.
V1/v2 outputs, literal states, citations and failed gates remain unchanged.
"""
from copy import deepcopy
import json
import re

from .e009_adjudication_v2 import canonical, validate_reconstruction

SCHEMA = "e009-semantic-observables-v1"
VARIABLES = frozenset(("X", "Y", "Z", "W", "V", "Q"))
BRI_COMPONENTS = ("root_revision", "dependent_revision", "independent_support",
                  "no_false_retraction", "traceability", "new_prediction")


def _result(state, value=None, reason=None):
    return {"state": state, "value": value, "reason": reason}


def _query_shape(proposition):
    if not isinstance(proposition, dict) or set(proposition) != {"query", "value"}:
        raise ValueError("proposition requires query and value")
    if type(proposition["value"]) is not int:
        raise ValueError("asserted value must be an integer, not bool/null")
    query = proposition["query"]
    if not isinstance(query, dict):
        raise ValueError("query must be an object")
    kind = query.get("kind")
    shapes = {"model": {"kind", "index"}, "edge": {"kind", "source", "target"},
              "path": {"kind", "source", "target"},
              "probability": {"kind", "target", "do"},
              "census_match": {"kind", "do", "counts"}}
    if not isinstance(kind, str) or kind not in shapes or set(query) != shapes[kind]:
        raise ValueError("unsupported query kind/keys; no alias imputation")
    if kind == "model" and (type(query["index"]) is not int or not 0 <= query["index"] < 576):
        raise ValueError("model index outside public domain")
    for key in ("source", "target"):
        if key in query and (not isinstance(query[key], str) or query[key] not in VARIABLES):
            raise ValueError("unknown public variable")
    if kind in ("edge", "path") and query["source"] == query["target"]:
        raise ValueError("source and target must differ")
    if "do" in query:
        items = query["do"]
        if not isinstance(items, list) or any(
                not isinstance(p, list) or len(p) != 2 or
                not isinstance(p[0], str) or p[0] not in VARIABLES or
                type(p[1]) is not int or p[1] not in (0, 1) for p in items):
            raise ValueError("invalid intervention")
        if len({p[0] for p in items}) != len(items):
            raise ValueError("duplicate intervention variable; never last-write-wins")
        query["do"] = sorted(items)
    if kind == "census_match":
        counts = query["counts"]
        if not isinstance(counts, list) or len(counts) != 64 or any(
                type(n) is not int or n < 0 for n in counts):
            raise ValueError("malformed census array; never resize or repair")
        # A wrong total is still an intelligible asserted equality, not repaired truth.
    return proposition


def _prose_proposition(text):
    match = re.fullmatch(r"model index(\d+) value(-?\d+)", text)
    if match:
        index, value = map(int, match.groups())
        return {"query": {"kind": "model", "index": index}, "value": value}
    match = re.fullmatch(r"(edge|path) ([XYZWVQ])->([XYZWVQ]) value(-?\d+)", text)
    if match:
        kind, source, target, value = match.groups()
        return {"query": {"kind": kind, "source": source, "target": target}, "value": int(value)}
    match = re.fullmatch(r"probability(?: target)? ([XYZWVQ]) do=(.+) value(-?\d+)", text)
    if match:
        target, intervention, value = match.groups()
        # Only JSON data, never eval. The public prose shorthand leaves variable names unquoted.
        intervention = re.sub(r'(?<=[\[,])\s*([XYZWVQ])(?=\s*,)', r'"\1"', intervention)
        return {"query": {"kind": "probability", "target": target,
                          "do": json.loads(intervention)}, "value": int(value)}
    match = re.fullmatch(r"probability ([XYZWVQ])=1 under do ([XYZWVQ])=([01]) equals numerator(-?\d+)", text)
    if match:
        target, source, bit, value = match.groups()
        return {"query": {"kind": "probability", "target": target, "do": [[source, int(bit)]]},
                "value": int(value)}
    match = re.fullmatch(r"observational probability ([XYZWVQ])=1 equals numerator(-?\d+)", text)
    if match:
        target, value = match.groups()
        return {"query": {"kind": "probability", "target": target, "do": []}, "value": int(value)}
    return None


def normalize_proposition(surface):
    """Bounded syntax interpretation. Unrecognized prose is not a false proposition."""
    value = deepcopy(surface)
    if isinstance(value, str):
        try:
            value = _prose_proposition(value)
        except (ValueError, TypeError) as error:
            return _result("malformed", reason=str(error))
        if value is None:
            return _result("uninterpreted", reason="no registered surface grammar; no guessed meaning")
    try:
        return _result("resolved", _query_shape(value))
    except ValueError as error:
        return _result("malformed", reason=str(error))


def normalize_bases(surface):
    """Normalize explicit OR-of-AND; a flat membership list leaves connectives unknown."""
    if not isinstance(surface, list):
        return _result("uninterpreted", reason="no explicit OR-of-AND representation")
    if surface and all(isinstance(ref, str) for ref in surface):
        return _result("uninterpreted", reason="membership does not specify conjunction/disjunction")
    if any(not isinstance(clause, list) or any(
            not isinstance(ref, str) or not re.fullmatch(r"[ec]:[A-Za-z0-9_.:-]+", ref)
            for ref in clause) for clause in surface):
        return _result("malformed", reason="invalid explicit dependency formula")
    clauses = {tuple(sorted(set(clause))) for clause in surface}
    # No absorption: retain distinct observed alternative justifications/provenance.
    return _result("resolved", [list(clause) for clause in sorted(clauses)])


def _normalize_field(name, value):
    if name == "proposition":
        return normalize_proposition(value)
    if name == "bases":
        return normalize_bases(value)
    return _result("literal", deepcopy(value))


def project_components(memory_view, reconstruction):
    """Keep every identifiable record and raw field; this does not verify entailment."""
    checked = validate_reconstruction(memory_view, reconstruction)
    output = json.loads(canonical(reconstruction))
    claims = []
    for claim in output["claims"]:
        fields = {}
        for name, surface in claim["fields"].items():
            state = surface["state"]
            if state == "known":
                semantic = _normalize_field(name, surface["value"])
            elif state == "conflicting":
                semantic = {"state": "conflicting", "alternatives": [
                    _normalize_field(name, v) for v in surface["alternatives"]],
                    "reason": "normalization never chooses a historical candidate"}
            else:
                semantic = _result(state, reason="no imputation")
            fields[name] = {"surface": surface, "semantic": semantic}
        claims.append({"id": claim["id"], "identity_evidence": claim["identity_evidence"], "fields": fields})
    return {"schema": SCHEMA, "claims": claims, "evidence": output["evidence"],
            "coverage": output["coverage"], "coverage_gaps": output["coverage_gaps"],
            "input_sha256": checked["request_sha256"], "reconstruction_sha256": checked["output_sha256"],
            "citation_existence_verified": True, "semantic_entailment_verified": False,
            "causal_truth_verified": False, "registered_bri_rescored": False}


def current_candidates(observations):
    """Formal explicit-supersession annotations, not inferred chronology or verified evidence.

    Each annotation has id, value, supersedes and witnesses. Witnesses are retained,
    not automatically deemed semantically sufficient. Publication order alone cannot
    select a value. A superseded assertion can still have superseded an older one.
    """
    if not isinstance(observations, list):
        raise ValueError("assertion annotations must be a list")
    seen, removed, records = set(), set(), []
    for item in observations:
        if not isinstance(item, dict) or set(item) != {"id", "value", "supersedes", "witnesses"}:
            raise ValueError("invalid assertion annotation")
        identity, prior, witnesses = item["id"], item["supersedes"], item["witnesses"]
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("invalid/duplicate assertion ID")
        if not isinstance(prior, list) or any(not isinstance(p, str) or p not in seen for p in prior):
            raise ValueError("supersession must explicitly reference earlier observed IDs")
        if not isinstance(witnesses, list) or not witnesses or any(not isinstance(w, str) or not w for w in witnesses):
            raise ValueError("explicit annotation witnesses required")
        canonical(item)  # Reject non-JSON/NaN; never evaluate the text.
        seen.add(identity); removed.update(prior); records.append(deepcopy(item))
    active = [item for item in records if item["id"] not in removed]
    values = {canonical(item["value"]): item["value"] for item in active}
    return {"state": "unknown" if not values else "resolved" if len(values) == 1 else "conflicting",
            "candidates": list(values.values()), "active_ids": [item["id"] for item in active],
            "history": records, "supersession_entailment_verified": False}


def integrity_bounds(components):
    """Conjunction bounds on supplied component assessments, NOT an implemented BRI evaluator."""
    if not isinstance(components, dict) or set(components) != set(BRI_COMPONENTS):
        raise ValueError("all six BRI components required; unknown must be explicit")
    if any(value is not None and type(value) is not bool for value in components.values()):
        raise ValueError("component assessment must be true, false or unknown")
    return {"lower": int(all(value is True for value in components.values())),
            "upper": int(not any(value is False for value in components.values())),
            "unknown_components": [name for name in BRI_COMPONENTS if components[name] is None],
            "components": deepcopy(components)}


def aggregate_bounds(episodes):
    """Keep every supplied assignment, including entirely unobserved episodes."""
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("nonempty assigned episodes required")
    bounds = [integrity_bounds(episode) for episode in episodes]
    return {"assigned": len(bounds), "lower": sum(b["lower"] for b in bounds) / len(bounds),
            "upper": sum(b["upper"] for b in bounds) / len(bounds), "episodes": bounds,
            "component_assessments_verified": False}
