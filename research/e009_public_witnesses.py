"""Compose exact source spans for supplied obligations, not infer their semantics.

Frozen evaluators are unchanged. Coverage proves only that citations jointly
contain the supplied identity/assertion/scope obligations in the bound documents.
"""
from copy import deepcopy
import hashlib

from .e009_adjudication_v2 import canonical
from .e009_semantic_observables import BRI_COMPONENTS, integrity_bounds

SCHEMA = "e009-public-witnesses-v1"
REQUIRED_ROLES = {"identity", "assertion", "scope"}
ROLES = REQUIRED_ROLES | {"qualification", "lineage"}
IGNORABLE_GAPS = " \t\r\n"


def _binding(value):
    if (not isinstance(value, dict) or set(value) != {"claim_id", "field", "as_of"}
            or any(not isinstance(v, str) or not v for v in value.values())):
        raise ValueError("explicit claim/field/time binding required")


def _span(documents, item):
    document, quote = item["document"], item["quote"]
    if type(document) is not int or not 0 <= document < len(documents):
        raise ValueError("invalid document index")
    if not isinstance(quote, str) or not quote:
        raise ValueError("nonempty exact quote required")
    text = documents[document]["text"]
    if "start" in item:
        start = item["start"]
        if type(start) is not int or start < 0 or text[start:start + len(quote)] != quote:
            raise ValueError("quote does not match explicit codepoint offset")
    else:
        start = text.find(quote)
        if start < 0 or text.find(quote, start + 1) >= 0:
            raise ValueError("quote missing or ambiguous; explicit occurrence required")
    return {"document": document, "start": start, "end": start + len(quote)}


def _intervals(points):
    intervals = []
    for point in points:
        if intervals and intervals[-1][1] == point:
            intervals[-1][1] += 1
        else:
            intervals.append([point, point + 1])
    return intervals


def compose_witnesses(documents, binding, obligations, citations):
    """Document/codepoint coverage conditional on explicit, unverified semantic obligations."""
    _binding(binding)
    if not isinstance(documents, list) or not documents:
        raise ValueError("source documents required")
    for document in documents:
        if (not isinstance(document, dict) or set(document) != {"stage", "text"}
                or not isinstance(document["stage"], str) or not document["stage"]
                or not isinstance(document["text"], str)):
            raise ValueError("invalid source document")
    if not isinstance(obligations, list) or not isinstance(citations, list):
        raise ValueError("obligations and citations must be lists")
    resolved = []
    for citation in citations:
        if (not isinstance(citation, dict) or not {"document", "quote"} <= set(citation)
                or set(citation) - {"document", "quote", "start"}):
            raise ValueError("invalid citation fields")
        resolved.append(_span(documents, citation))
    rows, roles = [], set()
    for obligation in obligations:
        if (not isinstance(obligation, dict) or not {"binding", "document", "quote", "roles"} <= set(obligation)
                or set(obligation) - {"binding", "document", "quote", "roles", "start"}):
            raise ValueError("invalid obligation fields")
        _binding(obligation["binding"])
        if obligation["binding"] != binding:
            raise ValueError("obligation belongs to another claim, field or time")
        required_roles = obligation["roles"]
        if (not isinstance(required_roles, list) or not required_roles
                or any(not isinstance(r, str) or r not in ROLES for r in required_roles)
                or len(required_roles) != len(set(required_roles))):
            raise ValueError("invalid obligation roles")
        span = _span(documents, obligation)
        if not any(char not in IGNORABLE_GAPS for char in obligation["quote"]):
            raise ValueError("obligation cannot consist only of ignorable whitespace")
        if "scope" in required_roles and documents[span["document"]]["stage"] != binding["as_of"]:
            raise ValueError("current scope witness belongs to another stage")
        roles.update(required_roles)
        covered = set()
        for citation in resolved:
            if citation["document"] == span["document"]:
                covered.update(range(max(span["start"], citation["start"]), min(span["end"], citation["end"])))
        text = documents[span["document"]]["text"]
        missing = [i for i in range(span["start"], span["end"])
                   if i not in covered and text[i] not in IGNORABLE_GAPS]
        rows.append({"span": span, "roles": list(required_roles), "covered": not missing,
                     "missing_ranges": _intervals(missing)})
    missing_roles = sorted(REQUIRED_ROLES - roles)
    state = "unknown" if missing_roles else "covered" if all(r["covered"] for r in rows) else "uncovered"
    return {"schema": SCHEMA, "binding": deepcopy(binding), "coverage_state": state,
            "covered": state == "covered", "missing_roles": missing_roles, "obligations": rows,
            "citation_spans": resolved, "coordinate_system": "Unicode codepoint offsets, half-open intervals",
            "source_sha256": [hashlib.sha256(canonical(d)).hexdigest() for d in documents],
            "obligation_semantics_verified": False, "causal_truth_verified": False,
            "registered_bri_rescored": False}


def trace_public_statuses(observations):
    """Expose covered, annotated status transitions without calling them correct revisions."""
    if not isinstance(observations, list):
        raise ValueError("public observations must be a list")
    prior_rank = -1
    identity = None
    for observation in observations:
        if (not isinstance(observation, dict) or set(observation) != {"binding", "status", "scope", "coverage"}):
            raise ValueError("invalid status observation")
        binding = observation["binding"]
        _binding(binding)
        if binding["field"] != "status" or binding["as_of"] not in ["seed", "A", "B", "C", "D", "E"]:
            raise ValueError("status observation needs an explicit study stage")
        rank = ["seed", "A", "B", "C", "D", "E"].index(binding["as_of"])
        if rank <= prior_rank or (identity is not None and identity != binding["claim_id"]):
            raise ValueError("unordered stages or unrelated claim identities")
        prior_rank, identity = rank, binding["claim_id"]
        if not isinstance(observation["scope"], str) or observation["scope"] not in {"current", "historical"}:
            raise ValueError("explicit historical/current scope required")
        if (binding["as_of"] == "seed") != (observation["scope"] == "historical"):
            raise ValueError("study seed is a historical assertion, not an agent endorsement")
        status = observation["status"]
        if (not isinstance(status, dict) or set(status) != {"state", "value"}
                or not isinstance(status["state"], str) or status["state"] not in {"known", "unknown"}
                or (status["state"] == "known" and (not isinstance(status["value"], str) or status["value"] not in
                    {"supported", "refuted", "undetermined", "conflicted", "superseded"}))
                or (status["state"] == "unknown" and status["value"] is not None)):
            raise ValueError("invalid status annotation")
        coverage = observation["coverage"]
        if (not isinstance(coverage, dict) or coverage.get("schema") != SCHEMA
                or coverage.get("binding") != binding or type(coverage.get("covered")) is not bool
                or coverage.get("coverage_state") not in {"covered", "uncovered", "unknown"}
                or coverage["covered"] != (coverage["coverage_state"] == "covered")):
            raise ValueError("coverage belongs to another observation")
    transitions = []
    for before, after in zip(observations, observations[1:]):
        comparable = all(o["status"]["state"] == "known" and o["coverage"]["covered"] for o in [before, after])
        changed = before["status"]["value"] != after["status"]["value"] if comparable else None
        kind = "unresolved" if not comparable else "historical_to_current" if before["scope"] == "historical" else "current_status_transition"
        transitions.append({"from": before["binding"]["as_of"], "to": after["binding"]["as_of"],
                            "before": deepcopy(before["status"]), "after": deepcopy(after["status"]),
                            "kind": kind, "changed": changed, "root_revision": None})
    return {"observations": deepcopy(observations), "transitions": transitions,
            "missing_before": len(observations) < 2,
            "bri_bounds": integrity_bounds(dict.fromkeys(BRI_COMPONENTS)),
            "missing_component_inputs": ["validated root identity and revision opportunity", "public proposition identity",
                                         "admissible evidence and causal expected status", "dependent and independent claims",
                                         "traceability and new prediction"],
            "annotation_semantics_verified": False, "causal_truth_verified": False,
            "registered_bri_rescored": False}
