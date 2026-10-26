"""Inspect native citation context, without promoting identity or currentness.

A matching native ID is a literal observation, not proof that a record is a
current claim. Shared prose, records using other key names and historical or
negated records require a separate semantic observer. No search repairs a pointer.
"""
from research.e009_adjudication_v2 import public_request
from .source_binding import _pointer_value, resolve_source_value


def _descendant_ids(value):
    found = []
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            found.append(value["id"])
        for child in value.values():
            found.extend(_descendant_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_descendant_ids(child))
    return found


def inspect_native_identity_context(memory_view, selector, claim_id):
    """Classify the actual selection/ancestors; preserve unsupported cases.

    Only the literal string key `id` is inspected. Duplicate occurrences remain
    in descendant_ids. A missing native binding does not mean a false assertion.
    F text is rejected, not guessed from substring occurrence or a schema default.
    """
    if not isinstance(claim_id, str) or not claim_id:
        raise ValueError("nonempty claim ID required")
    selected = resolve_source_value(memory_view, selector)
    document = public_request(memory_view)["documents"][selector["document"]]
    if document["format"] != "S":
        raise ValueError("native identity inspection requires an S document")
    pointer = selector["pointer"]
    prefixes = [""]
    for raw in pointer.split("/")[1:]:
        prefixes.append(prefixes[-1] + "/" + raw)
    nearest = None
    for prefix in prefixes:
        value = _pointer_value(document["payload"], prefix)
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            nearest = {"pointer": prefix, "id": value["id"], "type": value.get("type")}
    descendants = _descendant_ids(selected["value"])
    if nearest and nearest["id"] == claim_id:
        category = "native_context_same_id"
    elif claim_id in descendants:
        category = "selected_container_includes_id"
    elif nearest:
        category = "native_context_other_id"
    else:
        category = "no_native_identity_binding"
    return {"claim_id": claim_id, "category": category,
            "nearest_native_record": nearest, "descendant_ids": descendants,
            "selected_value_sha256": selected["value_sha256"],
            "source": selected["source"], "request_sha256": selected["request_sha256"],
            "semantic_identity_verified": False, "currentness_verified": False}
