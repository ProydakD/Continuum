"""Copy selected public literals, never a model-supplied replacement value.

This candidate does not verify claim identity, currentness, entailment or coverage.
Historical and malformed source values remain historical and malformed. A future
observer contract and independent calibration are required before BRI use.
"""
from copy import deepcopy
import hashlib
import json

from research.e009_adjudication_v2 import canonical, public_request


def _sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pointer_value(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("invalid JSON pointer")
    for raw in pointer.split("/")[1:]:
        if "~" in raw.replace("~0", "").replace("~1", ""):
            raise ValueError("invalid JSON pointer escape")
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if (not token.isascii() or not token.isdigit()
                    or (len(token) > 1 and token.startswith("0"))):
                raise ValueError("invalid array pointer index")
            index = int(token)
            if index >= len(value):
                raise ValueError("array pointer out of range")
            value = value[index]
        elif isinstance(value, dict) and token in value:
            value = value[token]
        else:
            raise ValueError("JSON pointer not found")
    return deepcopy(value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key; no last-write-wins")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite JSON constant: " + value)


def resolve_source_value(memory_view, selector):
    """Resolve one exact selection; return provenance and explicit semantic limits.

    S: {document, pointer}. F: {document, start, end, decode}, with Unicode
    codepoint offsets and decode=text|json. No supplied value, default, search,
    normalization or inferred choice of the newest document is accepted.
    """
    request = public_request(memory_view)
    if not isinstance(selector, dict) or type(selector.get("document")) is not int:
        raise ValueError("integer document selection required")
    index = selector["document"]
    if not 0 <= index < len(request["documents"]):
        raise ValueError("document selection out of range")
    document = request["documents"][index]
    payload = document["payload"]
    source = {"document": index, "stage": document["stage"],
              "payload_sha256": _sha(payload)}
    if document["format"] == "S":
        if set(selector) != {"document", "pointer"}:
            raise ValueError("structured selection requires only document and pointer")
        value = _pointer_value(payload, selector["pointer"])
        source["pointer"] = selector["pointer"]
    else:
        if set(selector) != {"document", "start", "end", "decode"}:
            raise ValueError("text selection requires document, start, end and decode")
        start, end = selector["start"], selector["end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(payload):
            raise ValueError("invalid Unicode codepoint span")
        selected = payload[start:end]
        if selector["decode"] == "text":
            value = selected
        elif selector["decode"] == "json":
            value = json.loads(selected, object_pairs_hook=_unique_object,
                               parse_constant=_reject_constant)
            canonical(value)  # Also rejects overflow such as JSON 1e999.
        else:
            raise ValueError("unsupported literal decoding")
        source.update(start=start, end=end, start_utf8=len(payload[:start].encode("utf-8")),
                      end_utf8=len(payload[:end].encode("utf-8")),
                      selected_text=selected, decode=selector["decode"])
    return {"value": value, "value_sha256": _sha(value), "source": source,
            "request_sha256": _sha(request), "currentness_verified": False,
            "semantic_entailment_verified": False}
