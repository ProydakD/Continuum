"""Scoped public assertion support, not causal truth or universal text entailment.

Rules cover current native lists and explicit current-prose grammars. Unparsed
scope/identity/history stays unknown. No sidecar, oracle, model call or rescoring.
"""
import json
import re
from copy import deepcopy

from .e009_adjudication_v2 import FIELDS, canonical, public_request, validate_reconstruction
from .e009_semantic_observables import normalize_proposition, normalize_bases

SCHEMA = "e009-public-support-v1"
STATUSES = r"supported|refuted|undetermined|conflicted|superseded"
IDENTITY = r"[A-Za-z][A-Za-z0-9_-]*"


def _value(state, value=None, witnesses=()):
    return {"state": state, "value": value, "witnesses": list(witnesses)}


def _quote(document, text):
    return {"document": document, "quote": text}


def _tokens(text):
    values = [v.strip().strip('"') for v in text.split(",")] if text.strip() else []
    if any(not re.fullmatch(r"[A-Za-z0-9_.:-]+", v) for v in values):
        raise ValueError("unsupported list tokens")
    return values


def _formula(text):
    if not re.fullmatch(r"\[(?:\s*\[[^\[\]]*\]\s*,?)*\]", text):
        raise ValueError("unsupported OR-of-AND syntax")
    return [_tokens(m.group(1)) for m in re.finditer(r"\[([^\[\]]*)\]", text)]


def _native(payload, witness):
    if not isinstance(payload, list) or any(not isinstance(r, dict) for r in payload):
        return None
    claims = []
    for index, record in enumerate(payload):
        if {"id", "proposition", "status"} <= set(record) <= {"id", *FIELDS}:
            if not isinstance(record["id"], str) or not record["id"]:
                return None
            claims.append((index, record))
        else:
            # An unparsed auxiliary record may qualify the whole list without IDs.
            return None
    if len({r["id"] for _, r in claims}) != len(claims):
        return None
    records = {}
    for index, record in claims:
        identity = witness(index, "id")
        records[record["id"]] = {name: _value("known" if name in record else "absent",
            deepcopy(record.get(name)), [identity, witness(index, name) if name in record else witness(index, None)])
            for name in FIELDS}
    return {"records": records, "closed_identity_set": True, "rule": "complete_current_native_list"}


def _prose(text, document, stage):
    markers = list(re.finditer(r"(?:^|(?<=\. )|(?<=\n))(Current retained claims: |Current propositions/status: )", text))
    if len(markers) != 1:
        return None
    marker = markers[0];prefix = text[:marker.start()];rest = text[marker.end():]
    records, clauses, pending = {}, {}, []
    inline = marker.group(1).startswith("Current retained")
    shared = re.search(r"All inherited claims retained at version (\d+), origin ([A-Za-z0-9_-]+)\.\s*$", prefix)
    if not inline and shared is None:
        return None
    framing = prefix[:shared.start()] if not inline else prefix
    if not re.fullmatch(r"\s*(?:Stage " + re.escape(stage) + r"\.\s*)?", framing):
        return None  # Unparsed framing cannot be assumed not to change the scope.
    position = 0;previous_basis = None
    while position < len(rest):
        remaining = rest[position:]
        if inline:
            match = re.match(r"\s*(" + IDENTITY + r") version(\d+) origin ([A-Za-z0-9_-]+): ([^;.]+?) (" +
                             STATUSES + r"), (basis \[[^\[\]]*\]|same basis)\.", remaining)
        else:
            match = re.match(r"\s*(" + IDENTITY + r") ([^;.]+?) (" + STATUSES + r")[;.]", remaining)
        if match:
            clause = match.group(0).strip()
            if inline:
                cid, version, origin, prop, status, basis = match.groups()
            else:
                cid, prop, status = match.groups();version, origin = shared.groups()
            if cid in records:
                return None
            own = _quote(document, clause);clauses[cid] = own
            fields = {name: _value("unknown") for name in FIELDS}
            fields["proposition"] = _value("known", prop, [own])
            fields["status"] = _value("known", status, [own])
            metadata = [own] if inline else [own, _quote(document, shared.group(0).strip())]
            fields["version"] = _value("known", int(version), metadata)
            fields["origin"] = _value("known", origin, metadata)
            if inline:
                if basis == "same basis":
                    if previous_basis is None:
                        return None
                    values, basis_witness = previous_basis
                    fields["bases"] = _value("known", values, [own, basis_witness])
                else:
                    values = _tokens(basis[len("basis ["):-1])
                    fields["bases"] = _value("known", values, [own])
                    previous_basis = (values, own)
            records[cid] = fields;pending.append(cid)
            position += match.end();continue
        if not inline:
            group = re.match(r"\s*These (one|two|three|four|five|six|seven|eight|nine|ten|\d+) (?:have|retain) bases (\[\[.*?\]\]), reasons \[([^\[\]]*)\]\.", remaining)
            if group:
                number, bases, reasons = group.groups()
                count = int(number) if number.isdigit() else ["one","two","three","four","five","six","seven","eight","nine","ten"].index(number)+1
                if len(pending) != count:
                    return None
                binding = _quote(document, group.group(0).strip())
                for cid in pending:
                    records[cid]["bases"] = _value("known", _formula(bases), [clauses[cid], binding])
                    records[cid]["reasons"] = _value("known", _tokens(reasons), [clauses[cid], binding])
                pending=[];position+=group.end();continue
        break
    if not records or (not inline and pending):
        return None
    tail = rest[position:]
    if inline:
        reasons = re.match(r"\s*All current reasons are \[([^\[\]]*)\]\.", tail)
        if reasons:
            binding = _quote(document, reasons.group(0).strip())
            for cid in records:
                records[cid]["reasons"] = _value("known", _tokens(reasons.group(1)), [binding])
            tail = tail[reasons.end():]
    else:
        hashes = re.match(r"\s*Previous_sha256 fields for version(\d+) in ID order: ([^.]+)\.", tail)
        if hashes:
            if int(hashes.group(1)) != int(shared.group(1)):
                return None
            found = set()
            for entry in hashes.group(2).split(";"):
                pair = re.fullmatch(r"\s*(" + IDENTITY + r")=([0-9a-fA-F]+)\s*", entry)
                if not pair or pair.group(1) not in records or pair.group(1) in found:
                    return None
                cid, value = pair.groups();found.add(cid)
                records[cid]["previous_sha256"] = _value("known", value, [_quote(document, pair.group(0).strip())])
            if found != set(records):
                return None
            tail = tail[hashes.end():]
    if tail.strip():
        return None
    return {"records": records, "closed_identity_set": False, "rule": "scoped_explicit_current_prose",
            "scope_limitation": "finite current-section grammar, not universal discourse interpretation"}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(token):
    raise ValueError("nonfinite JSON constant: " + token)


def current_public_assertions(memory_view):
    request = public_request(memory_view);document = len(request["documents"]) - 1
    current = request["documents"][document];payload = current["payload"]
    if current["format"] == "S":
        result = _native(payload, lambda index, key: {
            "document": document, "pointer": f"/{index}" + (f"/{key}" if key is not None else "")})
    else:
        match = re.fullmatch(r"(?:Current records|Current claims):\s*(\[.*\])\s*", payload, flags=re.S)
        result = None
        if match:
            try:
                value = json.loads(match.group(1), object_pairs_hook=_unique_keys, parse_constant=_invalid_constant)
                result = _native(value, lambda index, key: _quote(document, payload))
            except (ValueError, TypeError):
                result = None
        if result is None:
            try:
                result = _prose(payload, document, current["stage"])
            except ValueError:
                result = None
    if result is None:
        return {"records": {}, "closed_identity_set": False, "rule": "unknown_scope",
                "reason": "unsupported, incomplete, duplicate or ambiguous current source; history not silently carried"}
    return result


def _covered(witness, citations):
    for citation in citations:
        if citation["document"] != witness["document"]:
            continue
        if "quote" in witness and "quote" in citation and witness["quote"] in citation["quote"]:
            return True
        if "pointer" in witness and "pointer" in citation:
            pointer = citation["pointer"]
            if pointer == witness["pointer"] or witness["pointer"].startswith(pointer + "/"):
                return True
    return False


def _same_assertion(name, left, right):
    if canonical(left) == canonical(right):
        return True
    normalizer = normalize_proposition if name == "proposition" else normalize_bases if name == "bases" else None
    if normalizer:
        a, b = normalizer(left), normalizer(right)
        return a["state"] == b["state"] == "resolved" and canonical(a["value"]) == canonical(b["value"])
    return False


def assess_public_support(memory_view, reconstruction):
    """Source assertion/citation support is separate from world truth and general validity."""
    checked = validate_reconstruction(memory_view, reconstruction)
    catalog = current_public_assertions(memory_view);rows = []
    for claim in reconstruction["claims"]:
        source = catalog["records"].get(claim["id"]);fields = {}
        for name, proposed in claim["fields"].items():
            observed = source.get(name) if source is not None else None
            result = {"state": "unknown", "reason": "no sufficient current-source rule",
                      "source": deepcopy(observed), "assertion_match": None, "citation_support": None}
            if source is None and catalog["closed_identity_set"]:
                result.update(state="contradicted", reason="ID absent from complete current source")
            elif observed and observed["state"] != "unknown":
                if proposed["state"] == "unknown":
                    result.update(reason="candidate abstains; recoverability is not a false knowledge claim")
                else:
                    equal = proposed["state"] == observed["state"] and (
                        proposed["state"] == "absent" or
                        proposed["state"] == "known" and _same_assertion(name, proposed["value"], observed["value"]))
                    citations = [reconstruction["evidence"][identity] for identity in
                                 set(proposed["evidence"] + claim["identity_evidence"])]
                    covered = all(_covered(w, citations) for w in observed["witnesses"])
                    result.update(assertion_match=equal, citation_support=covered)
                    if not equal:
                        result.update(state="contradicted", reason="candidate field differs from unambiguous scoped public assertion")
                    elif not covered:
                        result.update(state="unsupported", reason="matching assertion but citations do not cover sufficient scoped witnesses")
                    else:
                        result.update(state="supported", reason="sufficient scoped public assertion and attached citations")
            fields[name] = result
        rows.append({"id": claim["id"], "fields": fields})
    return {"schema": SCHEMA, "claims": rows, "source_rule": catalog["rule"],
            "source_scope_limitation": catalog.get("scope_limitation"),
            "request_sha256": checked["request_sha256"], "reconstruction_sha256": checked["output_sha256"],
            "world_truth_verified": False, "universal_semantic_entailment_established": False,
            "registered_bri_rescored": False}
