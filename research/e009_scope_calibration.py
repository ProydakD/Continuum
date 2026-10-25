"""Controlled public-scope calibration; no private truth or natural-input gold imputation.

Synthetic framing changes what an author currently asserts, never causal truth.
Full public snapshots are retained and originals remain unscored controls.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import re

from .e009_adjudication_v2 import canonical, public_request

SCHEMA = "e009-scope-observation-v1"
STATUSES = {"supported", "refuted", "undetermined", "conflicted", "superseded"}
MODES = ("current_supported", "current_refuted", "quoted_refuted", "quoted_supported",
         "unresolved_conflict", "withdrawn")


def _sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _observation(state, value=None, alternatives=()):
    return {"state": state, "value": value, "alternatives": list(alternatives)}


def _note(identity, mode, family):
    name = json.dumps(identity)
    if family == 0:
        head = f"Current author entry for claim {name}: status {{status}}. This entry replaces all earlier statuses for this claim."
        quoted = " A discarded draft is quoted here, not adopted: 'status {status}'. The quoted draft does not change the current entry."
        conflict = f"For claim {name}, two coequal current entries remain: status supported and status refuted. Neither supersedes the other. The conflict is unresolved."
        withdrawn = f"For claim {name}, every earlier status entry is withdrawn. The author states no current status for this claim."
    else:
        head = f"The author's present position on claim {name} is status {{status}}; previous status entries have ceased to apply."
        quoted = " By contrast, the words 'status {status}' belong to a discarded account, not to the author's present position."
        conflict = f"Claim {name} has status supported alongside status refuted in the author's present account. Both entries have equal standing, with no selection or replacement between them."
        withdrawn = f"No status is now assigned to claim {name}. Its previous status entries have ceased to apply; none is carried forward."
    if mode == "unresolved_conflict":
        return conflict, _observation("conflicting", alternatives=["refuted", "supported"])
    if mode == "withdrawn":
        return withdrawn, _observation("absent")
    current = "supported" if mode in {"current_supported", "quoted_refuted"} else "refuted"
    note = head.format(status=current)
    if mode.startswith("quoted_"):
        note += quoted.format(status="refuted" if current == "supported" else "supported")
    return note, _observation("known", current)


def build_scope_cases(input_id, memory_view, target_id):
    """Return public requests separately from synthetic labels; never label an original."""
    public_request(memory_view)
    if not isinstance(input_id, str) or not input_id:
        raise ValueError("input identity required")
    if not isinstance(target_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", target_id):
        raise ValueError("unsupported target identity")
    snapshot = canonical(memory_view).decode("utf-8")
    delimiter = "SNAPSHOT_" + hashlib.sha256(snapshot.encode()).hexdigest()
    while delimiter in snapshot:
        delimiter += "_"
    quoted = f"<{delimiter}>\n{snapshot}\n</{delimiter}>"
    cases = []
    for mode in ("original", *MODES):
        family = int(_sha([input_id, mode])[-1], 16) % 2
        if mode == "original":
            context = "Public source snapshot (interpret its own scope and history):\n" + quoted
            expected, note = None, None
        else:
            note, expected = _note(target_id, mode, family)
            context = ("Earlier source snapshot, quoted as historical context rather than a current assertion:\n"
                       + quoted + "\n\n" + note)
        request = {"schema": SCHEMA, "target_id": target_id, "context": context}
        start = context.index(snapshot)
        cases.append({"id": _sha([input_id, mode])[:20], "input_id": input_id,
                      "public": request, "public_sha256": _sha(request),
                      "preserved_snapshot": {"start": start, "end": start + len(snapshot),
                                             "canonical_sha256": _sha(memory_view)},
                      "gold": {"controlled": mode != "original", "mode": mode, "language_family": family,
                               "expected": expected, "required_witnesses": [note] if note else []}})
    return cases


def verify_preserved_snapshot(case, memory_view):
    span = case["preserved_snapshot"]
    text = case["public"]["context"][span["start"]:span["end"]]
    return (json.loads(text) == memory_view and hashlib.sha256(text.encode()).hexdigest() ==
            span["canonical_sha256"] == _sha(memory_view) and _sha(case["public"]) == case["public_sha256"])


def validate_scope_answer(request, answer):
    """Check structure and exact quote existence only, not scope meaning."""
    if (not isinstance(request, dict) or set(request) != {"schema", "target_id", "context"}
            or request["schema"] != SCHEMA or not isinstance(request["context"], str)
            or not isinstance(request["target_id"], str)):
        raise ValueError("invalid public request or private fields")
    if (not isinstance(answer, dict) or set(answer) != {"schema", "target_id", "observation", "evidence"}
            or answer["schema"] != SCHEMA or answer["target_id"] != request["target_id"]):
        raise ValueError("invalid answer identity or schema")
    observed = answer["observation"]
    if not isinstance(observed, dict) or set(observed) != {"state", "value", "alternatives"}:
        raise ValueError("invalid observation fields")
    state, value, alternatives = observed["state"], observed["value"], observed["alternatives"]
    if not isinstance(alternatives, list) or any(not isinstance(v, str) or v not in STATUSES for v in alternatives):
        raise ValueError("invalid alternatives")
    if state == "known":
        valid = isinstance(value, str) and value in STATUSES and not alternatives
    elif state == "conflicting":
        valid = value is None and len(alternatives) >= 2 and len(alternatives) == len(set(alternatives))
    elif state in {"unknown", "absent"}:
        valid = value is None and not alternatives
    else:
        valid = False
    if not valid:
        raise ValueError("inconsistent observation state")
    evidence = answer["evidence"]
    if not isinstance(evidence, list) or (state != "unknown" and not evidence):
        raise ValueError("asserted observation requires evidence")
    for item in evidence:
        if (not isinstance(item, dict) or set(item) != {"quote"} or not isinstance(item["quote"], str)
                or not item["quote"] or request["context"].count(item["quote"]) != 1):
            raise ValueError("quote absent, ambiguous or malformed")
    return {"structurally_valid": True, "request_sha256": _sha(request),
            "answer_sha256": _sha(answer), "semantic_verification": False}


def compare_scope_answer(case, answer):
    checked = validate_scope_answer(case["public"], answer)
    gold = case["gold"]
    if not gold["controlled"]:
        return {**checked, "scored": False, "reason": "original natural scope has no imputed gold",
                "correct": None, "witness_covered": None, "exact": None}
    actual = deepcopy(answer["observation"])
    actual["alternatives"].sort()
    expected = deepcopy(gold["expected"])
    expected["alternatives"].sort()
    correct = canonical(actual) == canonical(expected)
    covered = all(any(witness in item["quote"] for item in answer["evidence"])
                  for witness in gold["required_witnesses"])
    return {**checked, "scored": True, "correct": correct, "witness_covered": covered,
            "exact": correct and covered}


def evaluate_scope_answers(cases, answers):
    """Missing, invalid and abstaining outputs stay in their assigned denominators."""
    identities = [case["id"] for case in cases]
    if len(identities) != len(set(identities)) or not isinstance(answers, dict) or set(answers) - set(identities):
        raise ValueError("duplicate cases or unknown answer identities")
    counts = Counter();by_mode = {};rows = []
    for case in cases:
        controlled = case["gold"]["controlled"]
        mode = case["gold"]["mode"]
        bucket = by_mode.setdefault(mode, Counter())
        bucket["assigned"] += 1
        counts["controlled_assigned" if controlled else "original_unscored_assigned"] += 1
        answer = answers.get(case["id"])
        if answer is None:
            row = {"outcome": "missing", "exact": False if controlled else None}
        else:
            try:
                row = compare_scope_answer(case, answer)
                state = answer["observation"]["state"]
                row["outcome"] = "abstained" if state == "unknown" else "asserted"
            except (ValueError, TypeError) as error:
                row = {"outcome": "invalid", "error": str(error), "exact": False if controlled else None}
        bucket[row["outcome"]] += 1
        if controlled:
            counts["controlled_" + row["outcome"]] += 1
            if row.get("correct"):
                counts["controlled_value_correct"] += 1
            if row.get("witness_covered"):
                counts["controlled_witness_covered"] += 1
            if row["exact"]:
                counts["controlled_exact"] += 1;bucket["exact"] += 1
            elif row["outcome"] == "asserted":
                counts["controlled_nonexact_assertions"] += 1
        rows.append({"id": case["id"], "input_id": case["input_id"], "mode": mode, **row})
    assigned = counts["controlled_assigned"]
    return {"summary": {**dict(counts), "controlled_exact": counts["controlled_exact"],
                         "controlled_exact_rate": counts["controlled_exact"] / assigned if assigned else None,
                         "controlled_complete_gate": bool(assigned) and counts["controlled_exact"] == assigned,
                         "natural_validity_established": False, "public_bri_recomputed": False},
            "by_mode": {k: dict(v) for k, v in by_mode.items()}, "rows": rows}
