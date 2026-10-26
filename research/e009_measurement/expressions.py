"""Source-backed construction and explicitly unverified semantic proposals.

These operations transport/construct candidate values. They do not establish
identity, scope, currentness, semantic entailment or eligibility for BRI scoring.
"""
import hashlib
import json
import re

from research.e009_adjudication_v2 import canonical
from .source_binding import resolve_source_value

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]*")
_RESERVED = {"true", "false", "null", "NaN", "Infinity"}


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("unexpected expression fields")


def _symbolic_list(text):
    """Decode explicit bare-identifier lists; preserve order, duplicates and depth."""
    def whitespace(index):
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def parse(index, depth):
        if depth > 32 or index >= len(text) or text[index] != "[":
            raise ValueError("expected bounded symbolic list")
        index = whitespace(index + 1)
        values = []
        if index < len(text) and text[index] == "]":
            return values, index + 1
        while index < len(text):
            if text[index] == "[":
                value, index = parse(index, depth + 1)
            else:
                match = _IDENTIFIER.match(text, index)
                if not match or match.group() in _RESERVED:
                    raise ValueError("unsupported symbolic-list token")
                value, index = match.group(), match.end()
            values.append(value)
            index = whitespace(index)
            if index < len(text) and text[index] == "]":
                return values, index + 1
            if index >= len(text) or text[index] != ",":
                raise ValueError("expected comma or closing bracket")
            index = whitespace(index + 1)
        raise ValueError("unterminated symbolic list")

    parsed, end = parse(whitespace(0), 0)
    if whitespace(end) != len(text):
        raise ValueError("trailing symbolic-list content")
    return parsed


def resolve_expression(memory_view, expression):
    """Resolve a bounded tree, retaining every construction/proposal and witness.

    literal: {op, selector}; symbolic_list: {op, selector} (F text only).
    object: {op, members: {key: expression}}; keys are proposed, not source proof.
    interpret: {op, proposal: JSON, witnesses: [selector]}; NEVER source-literal.
    There is no default, search, array repair, evaluation or last-write-wins op.
    """
    remaining = 1024

    def evaluate(node, depth):
        nonlocal remaining
        remaining -= 1
        if depth > 32 or remaining < 0:
            raise ValueError("expression size/depth limit exceeded")
        if not isinstance(node, dict) or not isinstance(node.get("op"), str):
            raise ValueError("expression operation required")
        op = node["op"]
        children = {}
        if op in {"literal", "symbolic_list"}:
            _keys(node, {"op", "selector"})
            selected = resolve_source_value(memory_view, node["selector"])
            value = selected["value"]
            if op == "symbolic_list":
                if selected["source"].get("decode") != "text" or not isinstance(value, str):
                    raise ValueError("symbolic list requires an F text selection")
                value = _symbolic_list(value)
            sources = [{**selected["source"], "selected_value_sha256": selected["value_sha256"]}]
            semantic_proposal_count = 0
        elif op == "object":
            _keys(node, {"op", "members"})
            members = node["members"]
            if not isinstance(members, dict) or not members or any(not isinstance(key, str) for key in members):
                raise ValueError("nonempty object members required; use a literal for empty objects")
            children = {key: evaluate(child, depth + 1) for key, child in members.items()}
            value = {key: child["value"] for key, child in children.items()}
            sources = [source for child in children.values() for source in child["sources"]]
            semantic_proposal_count = sum(child["semantic_proposal_count"] for child in children.values())
        elif op == "interpret":
            _keys(node, {"op", "proposal", "witnesses"})
            witnesses = node["witnesses"]
            if not isinstance(witnesses, list) or not 1 <= len(witnesses) <= 64:
                raise ValueError("semantic proposal requires 1..64 source witnesses")
            selected = [resolve_source_value(memory_view, selector) for selector in witnesses]
            sources = [{**item["source"], "selected_value_sha256": item["value_sha256"]} for item in selected]
            value = json.loads(canonical(node["proposal"]))
            semantic_proposal_count = 1
        else:
            raise ValueError("unsupported expression operation")
        return {"value": value, "value_sha256": hashlib.sha256(canonical(value)).hexdigest(),
                "operation": op, "children": children, "sources": sources,
                "literal_copy": op == "literal", "contains_semantic_proposal": semantic_proposal_count > 0,
                "semantic_proposal_count": semantic_proposal_count,
                "semantic_entailment_verified": False, "currentness_verified": False}

    return evaluate(expression, 0)
