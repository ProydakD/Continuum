"""Read-only public evidence extraction; not a semantic judge or registered scorer.

No private sidecar enters observation. F prose, historical reconstruction and
contradictions require separate adjudication even when embedded objects match.
"""
from collections import Counter
import hashlib
import json
import re


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _claims(value, pointer=""):
    if isinstance(value, dict):
        if isinstance(value.get("id"), str) and isinstance(value.get("proposition"), dict):
            yield pointer, value
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _claims(child, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _claims(child, pointer + "/" + str(index))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _text_objects(text):
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    permissive = json.JSONDecoder()
    index = 0
    while index < len(text):
        if text[index] not in "[{":
            index += 1
            continue
        try:
            value, end = decoder.raw_decode(text, index)
            _canonical(value)  # Also catches overflow such as 1e999.
        except json.JSONDecodeError as error:
            if re.match(r'\{\s*"|\[\s*(?:[\[{"\d-]|true\b|false\b|null\b)', text[index:]):
                # A JSON-like malformed root has no reliable end. Avoid reporting
                # a valid nested fragment as an unambiguous complete object.
                yield None, index, len(text), "malformed JSON-like root: " + error.msg
                break
            index += 1  # Ordinary prose may contain non-JSON punctuation.
            continue
        except ValueError as error:
            # Do not salvage an inner object from a duplicate-key/nonfinite root.
            try:
                _, end = permissive.raw_decode(text, index)
            except json.JSONDecodeError:
                end = len(text)  # Unknown boundary: retain, but do not salvage the tail.
            yield None, index, end, str(error)
        else:
            yield value, index, end, None
        index = end


def _documents(view):
    envelope_keys = {"memory", "origin", "sha256", "stage", "trust"}
    if not isinstance(view, dict):
        raise ValueError("memory view must be an object")
    if "journal" in view:
        if set(view) != {"journal", "memory", "trust"} or view["memory"] is not None:
            raise ValueError("unexpected journal fields")
        documents = view["journal"]
        if not isinstance(documents, list):
            raise ValueError("journal must be a list")
    else:
        documents = [view]
    if not documents:
        raise ValueError("no public document")
    stages = []
    for document in documents:
        if not isinstance(document, dict) or set(document) != envelope_keys:
            raise ValueError("unexpected public envelope fields")
        memory = document["memory"]
        if (not isinstance(memory, dict) or set(memory) != {"format", "payload"}
                or not isinstance(memory["format"], str) or memory["format"] not in {"F", "S"}):
            raise ValueError("invalid memory envelope")
        if memory["format"] == "F" and not isinstance(memory["payload"], str):
            raise ValueError("F payload must remain free text")
        if memory["format"] == "S" and not isinstance(memory["payload"], (list, dict)):
            raise ValueError("S payload must be structured")
        stage = document["stage"]
        if stage is None:
            if stages or document is not documents[0]:
                raise ValueError("seed must precede published history")
        elif not isinstance(stage, str) or len(stage) != 1 or stage not in "ABCD":
            raise ValueError("invalid published stage")
        else:
            stages.append(stage)
    if "journal" in view and stages != list("ABCD"[:len(stages)]):
        raise ValueError("journal stages must be consecutive and ordered")
    if documents[-1]["stage"] is None:
        raise ValueError("no current publication")
    return documents


def observe_public_memory(memory_view):
    """Extract explicit objects and witnesses using ONLY the actual public view.

    FULL history stays in the input and is fingerprinted, but current objects are
    never filled from old versions or a private label. Missing extraction is unknown.
    """
    memory_view = json.loads(_canonical(memory_view))  # Validate and detach returned objects.
    documents = _documents(memory_view)
    current = documents[-1]
    memory = current["memory"]
    payload = memory["payload"]
    occurrences, rejected = [], []
    if memory["format"] == "S":
        for pointer, claim in _claims(payload):
            occurrences.append({"claim": claim, "witness": {"json_pointer": pointer}})
    else:
        for value, start, end, error in _text_objects(payload):
            witness = {"start_utf8": len(payload[:start].encode("utf-8")),
                       "end_utf8": len(payload[:end].encode("utf-8")),
                       "json_value_sha256": _sha(value) if error is None else None}
            if error:
                rejected.append({**witness, "reason": error})
                continue
            for pointer, claim in _claims(value):
                occurrences.append({"claim": claim, "witness": {**witness, "json_pointer": pointer}})
    counts = Counter(item["claim"]["id"] for item in occurrences)
    return {"memory_view_sha256": _sha(memory_view), "target_stage": current["stage"],
            "format": memory["format"], "payload_sha256": _sha(payload),
            "history": [{"stage": item["stage"], "envelope_sha256": _sha(item)} for item in documents],
            "occurrences": occurrences, "duplicate_ids": sorted(cid for cid, count in counts.items() if count > 1),
            "rejected_json_values": rejected,
            "semantic_status": "unadjudicated", "public_state_verified": False}


def _differences(left, right, path=""):
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        def child_path(key):
            return path + "/" + key.replace("~", "~0").replace("/", "~1")
        result = [child_path(key) for key in sorted(set(left) ^ set(right))]
        for key in sorted(set(left) & set(right)):
            result.extend(_differences(left[key], right[key], child_path(key)))
        return result
    if isinstance(left, list):
        result = [path + "/length"] if len(left) != len(right) else []
        for index, (a, b) in enumerate(zip(left, right)):
            result.extend(_differences(a, b, path + "/" + str(index)))
        return result
    return [] if left == right else [path]


def compare_public_measurement(memory_view, measured_claims):
    """Compare AFTER public extraction; exact objects do not establish prose meaning."""
    observation = observe_public_memory(memory_view)
    if (not isinstance(measured_claims, list) or any(not isinstance(c, dict)
            or not isinstance(c.get("id"), str) for c in measured_claims)):
        raise ValueError("measurement must contain named claim objects")
    _canonical(measured_claims)
    private_ids = [c["id"] for c in measured_claims]
    if len(private_ids) != len(set(private_ids)):
        raise ValueError("duplicate measurement claim ID")
    public = {item["claim"]["id"]: item["claim"] for item in observation["occurrences"]}
    private = {c["id"]: c for c in measured_claims}
    differences = [{"id": cid, "paths": _differences(public[cid], private[cid])}
                   for cid in sorted(set(public) & set(private))
                   if _canonical(public[cid]) != _canonical(private[cid])]
    missing, extra = sorted(set(private) - set(public)), sorted(set(public) - set(private))
    if observation["duplicate_ids"] or observation["rejected_json_values"]:
        comparison = "ambiguous_explicit_objects"
    elif not public:
        comparison = "no_explicit_claim_objects"
    elif differences or missing or extra:
        comparison = "different_explicit_objects"
    else:
        comparison = "equal_explicit_objects"
    return {"observation": observation, "comparison": comparison,
            "not_extracted_private_ids": missing, "extra_public_ids": extra,
            "claim_differences": differences, "semantic_status": "unadjudicated",
            "public_state_verified": False}
