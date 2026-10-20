"""Resource accounting from observed traces, never inferred from token ceilings.

HTTP measurements exclude headers/TLS. MCP sizes are canonical reserializations,
not wire framing. Unknown charges remain unknown, including failed API attempts.
"""
from collections import defaultdict
import base64
import json
import math

from .e008_audit import json_bytes, snapshot


def measure(observed=0, unknown=0):
    return {"observed": observed, "unknown_observations": unknown,
            "complete": unknown == 0}


def combine(values, *, divisor=1):
    if divisor <= 0:
        raise ValueError("positive measurement denominator required")
    values = list(values)
    return measure(sum(v["observed"] for v in values) / divisor,
                   sum(v["unknown_observations"] for v in values))


def number(value, *, integer=False):
    return (type(value) in ((int,) if integer else (int, float))
            and math.isfinite(value) and value >= 0)


def token_measure(response, key, detail=None):
    usage = (response or {}).get("usage")
    value = usage.get(key) if isinstance(usage, dict) else None
    if detail:
        value = value.get(detail) if isinstance(value, dict) else None
    return measure(value) if number(value, integer=True) else measure(unknown=1)


def usage_measures(response):
    return {"input_tokens": token_measure(response, "input_tokens"),
            "output_tokens": token_measure(response, "output_tokens"),
            "cached_input_tokens": token_measure(response, "input_tokens_details", "cached_tokens"),
            "reasoning_output_tokens": token_measure(response, "output_tokens_details", "reasoning_tokens")}


def api_measurements(events):
    """Single-pass serial transport reconciliation, including workerless errors.

    Transport events lack attempt IDs in the existing logger. The executor is
    strictly serial; a POST belongs to the currently active started attempt.
    Ambiguous, duplicated or unmatched events are errors, not free requests.
    """
    attempts, transports, metadata = {}, {}, []
    active = last_finished = None
    for event in events:
        kind = event.get("event")
        if kind == "request_started":
            identity = event["attempt"]
            if active is not None or identity in attempts:
                raise ValueError("overlapping or duplicate API attempts")
            if not isinstance(event.get("worker"), str):
                raise ValueError("request worker required")
            attempts[identity] = {"worker": event["worker"], "terminal": None, "usage": usage_measures(None)}
            active = identity
        elif kind == "transport_bytes":
            for key in ("request_body_bytes", "response_body_bytes"):
                if not number(event.get(key), integer=True):
                    raise ValueError("invalid measured transport size")
            for key in ("request_sent", "response_complete"):
                if type(event.get(key)) is not bool:
                    raise ValueError("transport completeness must be explicit")
            if event["method"] == "GET":
                if active is not None or event.get("worker") is not None:
                    raise ValueError("metadata overlaps a context request")
                metadata.append(event)
            elif (event["method"] == "POST" and active is not None
                  and active not in transports and event.get("worker") == attempts[active]["worker"]):
                transports[active] = event
            else:
                raise ValueError("unbound or duplicate transport")
        elif kind in ("response", "request_failed"):
            identity = event["attempt"]
            validation_failure = (kind == "request_failed" and active is None
                                  and last_finished == identity and identity in attempts
                                  and (attempts[identity]["terminal"] or {}).get("event") == "response")
            if (active != identity and not validation_failure) or identity not in attempts:
                raise ValueError("unbound or duplicate API terminal event")
            if kind == "response" and event.get("worker") != attempts[identity]["worker"]:
                raise ValueError("response worker differs from request")
            if kind == "response":
                attempts[identity]["usage"] = usage_measures(event["response"])
            # Do not retain whole model outputs for the entire series in RAM.
            attempts[identity]["terminal"] = {"event": kind, "seconds": event.get("seconds")}
            active = None
            last_finished = identity

    groups = defaultdict(list)
    for identity, attempt in attempts.items():
        terminal = attempt["terminal"] or {}
        transport = transports.get(identity)
        body = measure(unknown=1)
        if transport:
            # request_body_bytes is the serialized size even when socket write
            # did not complete. Do not call all of it observed transmitted data.
            body = measure((transport["request_body_bytes"] if transport["request_sent"] else 0)
                           + transport["response_body_bytes"],
                           int(not (transport["request_sent"] and transport["response_complete"])))
        seconds = terminal.get("seconds")
        groups[attempt["worker"]].append({
            "attempt": identity, "terminal": terminal.get("event", "orphan"),
            "api_body_bytes": body,
            "api_seconds": measure(seconds) if number(seconds) else measure(unknown=1),
            **attempt["usage"],
        })
    metrics = ("api_body_bytes", "api_seconds", "input_tokens", "output_tokens",
               "cached_input_tokens", "reasoning_output_tokens")
    workers = {worker: {"attempts": len(items),
                       "failed_or_unknown": sum(x["terminal"] != "response" for x in items),
                       **{key: combine(x[key] for x in items) for key in metrics}}
               for worker, items in groups.items()}
    return {"workers": workers, "attempts": len(attempts),
            "metadata_requests": len(metadata),
            "metadata_api_body_bytes": combine(
                measure((e["request_body_bytes"] if e["request_sent"] else 0) + e["response_body_bytes"],
                        int(not (e["request_sent"] and e["response_complete"]))) for e in metadata)}


def rows(path):
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)


def context_measurements(unit):
    """Physical storage and logical saved content are separate overlapping views."""
    mcp = raw_logs = proposed = malformed = development = development_unknown = 0
    read_costs = defaultdict(int)
    for path in sorted((unit / "supervisor").glob("*.jsonl")):
        raw_logs += path.stat().st_size
        for event in rows(path):
            if event.get("channel") == "mcp" or event.get("event") == "mcp_response":
                mcp += len(json_bytes(event["message"])) + 1
            if event.get("event") == "tool_result" and event.get("name") in (
                    "read_memory", "read_protocol", "read_development", "verify_evidence"):
                # Exact JSON serialization used in the recorded Responses input.
                read_costs[event["name"]] += len(json.dumps(event["value"]).encode("utf-8"))
            if event.get("event") == "tool_result" and event.get("name") in ("publish_protocol", "publish_review"):
                args = event["arguments"]
                try:
                    if event["name"] == "publish_review":
                        development += len(args["content"].encode("utf-8"))
                    elif args["encoding"] == "utf8":
                        development += len(args["body"].encode("utf-8"))
                    elif args["encoding"] == "base64":
                        development += len(base64.b64decode(args["body"], validate=True))
                    else:
                        raise ValueError("unknown protocol encoding")
                except (ValueError, KeyError, TypeError):
                    development_unknown += 1
            if event.get("event") == "tool_result" and event.get("name") == "save_memory":
                args = event["arguments"]
                try:
                    if args["encoding"] == "utf8":
                        proposed += len(args["content"].encode("utf-8"))
                    elif args["encoding"] == "base64":
                        proposed += len(base64.b64decode(args["content"], validate=True))
                    else:
                        raise ValueError("unknown memory encoding")
                except (ValueError, KeyError, TypeError):
                    malformed += 1
    saved = wrappers = protocol = object_metadata = indices = 0
    db_path = unit / "state/continuum.sqlite3"
    if db_path.exists():
        db, index, objects = snapshot(db_path)
        for sha in set(index.values()):
            obj = objects[sha]
            value = json.loads(obj["content"])
            slots = [k for k, v in index.items() if v == sha]
            if any(k.startswith("state:") for k in slots):
                payload = (len(value["content"].encode("utf-8")) if value["encoding"] == "utf8"
                           else len(base64.b64decode(value["content"], validate=True)))
                saved += payload
                wrappers += len(obj["content"]) - payload
            elif any(k == "protocol" or k.startswith(("protocol:", "review:")) for k in slots):
                protocol += len(obj["content"])
            object_metadata += len(json_bytes({k: v for k, v in obj.items() if k != "content"}))
        indices = sum(len(t["result"].encode("utf-8")) for t in db["tasks"])
    result_path = unit / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    seconds = result.get("seconds")
    elapsed = (measure(seconds) if number(seconds) else
               measure(unknown=int((unit / "context-manifest.json").exists())))
    return {"mcp_reencoded_bytes": measure(mcp), "raw_supervisor_log_bytes": raw_logs,
            "context_seconds": elapsed, "model_tool_result_bytes": dict(read_costs),
            "proposed_protocol_and_review_bytes": measure(development, development_unknown),
            "proposed_memory_bytes": measure(proposed, malformed),
            "archive_memory_payload_bytes": saved, "archive_memory_wrapper_bytes": wrappers,
            "archive_protocol_and_review_bytes": protocol, "archive_object_metadata_bytes": object_metadata,
            "archive_index_bytes": indices,
            "retained_file_bytes": sum(p.stat().st_size for p in unit.rglob("*") if p.is_file())}


def chain_ids(job, jobs):
    """Charge actual ancestors exactly once; a full-journal control is one context."""
    result, current = [], job
    while current:
        if current["id"] in result:
            raise ValueError("cyclic cost attribution")
        result.append(current["id"])
        source = current.get("source")
        if source is not None and source not in jobs:
            raise ValueError("missing cost ancestor")
        current = jobs.get(source)
    return result


def correct_counts(score):
    """An abstention is not a new identified causal result for cost-per-result."""
    result = {"identified_new": 0, "correct_abstentions": 0, "integrative_new": 0}
    for row in (score or {}).get("questions", []):
        if not row["id"].startswith("Q") or not row.get("valid") or not row.get("target_correct"):
            continue
        if row["target_expected"] is None:
            result["correct_abstentions"] += 1
        else:
            result["identified_new"] += 1
            result["integrative_new"] += int(row.get("integrative") is True)
    return result


def amortize(setup, per_use, correct_per_use, uses):
    if not number(correct_per_use) or type(uses) is not int or uses <= 0:
        raise ValueError("nonnegative result rate and positive reuse count required")
    total = measure(setup["observed"] + uses * per_use["observed"],
                    setup["unknown_observations"] + uses * per_use["unknown_observations"])
    expected = uses * correct_per_use
    return {"total": total, "expected_identified_results": expected,
            "per_identified_result": total["observed"] / expected if expected and total["complete"] else None}


RESOURCE_KEYS = ("api_body_bytes", "input_tokens", "output_tokens", "api_seconds",
                 "context_seconds", "mcp_reencoded_bytes", "proposed_memory_bytes",
                 "proposed_protocol_and_review_bytes", "api_plus_mcp_bytes")


def resource_report(study, registration, evaluated, network):
    """All actual positions are charged, even rejected designs and skipped jobs.

    Per-use means are equal-world/equal-line by the registered balanced schedule.
    Setup includes BOTH T2 development lines and every validation/critique version.
    Calibration, smoke, catalogue/recovery and robustness costs stay visible as
    experiment overhead; they are not silently attributed to one competitor.
    """
    jobs = {j["id"]: j for j in registration["schedule"]}
    if len(jobs) != len(registration["schedule"]) or set(evaluated) != set(jobs):
        raise ValueError("all assigned positions required for resource accounting")
    api = api_measurements(network)
    unknown_workers = set(api["workers"]) - set(jobs) - {"smoke-primary", "smoke-secondary"}
    if unknown_workers:
        raise ValueError("unassigned provider worker in resource accounting")
    measured = {}
    for identity in jobs:
        item = context_measurements(study / "units" / identity)
        observed = api["workers"].get(identity)
        for key in ("api_body_bytes", "input_tokens", "output_tokens", "api_seconds",
                    "cached_input_tokens", "reasoning_output_tokens"):
            item[key] = observed[key] if observed else measure()
        item["api_plus_mcp_bytes"] = combine([item["api_body_bytes"], item["mcp_reencoded_bytes"]])
        item["api_attempts"] = observed["attempts"] if observed else 0
        item["failed_or_unknown_attempts"] = observed["failed_or_unknown"] if observed else 0
        measured[identity] = item

    phase_totals = {}
    for phase in sorted({j["phase"] for j in jobs.values()}):
        group = [measured[j["id"]] for j in jobs.values() if j["phase"] == phase]
        phase_totals[phase] = {key: combine(r[key] for r in group) for key in RESOURCE_KEYS}
    setup = [j["id"] for j in jobs.values()
             if j["condition"] == "T2" and j["phase"] in ("development", "validation")]
    scenarios = {}
    for condition in sorted({j["condition"] for j in jobs.values() if j["phase"] == "test"}):
        finals = [j for j in jobs.values() if j["phase"] == "test"
                  and j["stage"] == "D" and j["condition"] == condition]
        if not finals:
            continue
        # Failed chains keep their scheduled denominator and their actual costs.
        group = [identity for j in finals for identity in chain_ids(j, jobs)]
        if len(group) != len(set(group)):
            raise ValueError("shared execution requires explicit cost allocation")
        counts = [correct_counts(evaluated[j["id"]].get("score"))
                  if evaluated[j["id"]]["status"] == "completed" and evaluated[j["id"]]["audit"].get("pass")
                  else correct_counts(None) for j in finals]
        yields = {key: sum(c[key] for c in counts) / len(finals) for key in counts[0]}
        costs = {}
        for key in RESOURCE_KEYS:
            initial = combine(measured[k][key] for k in setup) if condition == "T2" else measure()
            per_use = combine((measured[k][key] for k in group), divisor=len(finals))
            costs[key] = {"setup": initial, "per_use": per_use,
                          "amortization": {str(n): amortize(initial, per_use, yields["identified_new"], n)
                                           for n in (1, 10, 100, 1000)}}
        scenarios[condition] = {"assigned_uses": len(finals), "actual_contexts": len(group),
                               "results_per_use": yields, "costs": costs}
    return {
        "scope": "HTTP bodies, excluding headers/TLS; canonical MCP messages, not wire framing. "
                 "Logical proposals, saved payload/wrappers, archive metadata and retained storage are overlapping "
                 "views, NOT additive independent charges. Unknown tokens/costs are not zero. "
                 "T2 setup pays for both lines, all validation and critics; no best-line selection. "
                 "Amortization is an expectation, not observed repeated deployments.",
        "fixture": registration["fixture"], "model_efficiency_claim_permitted": False,
        "unmeasured": ["model GPU/CPU/energy", "currency price", "human protocol design labor",
                       "TLS/HTTP headers", "MCP exact wire framing"],
        "network": api, "per_position": measured, "phase_totals": phase_totals,
        "experiment_overhead": {"calibration": phase_totals.get("calibration"),
                                "robustness": phase_totals.get("robustness"),
                                "smoke": {k: v for k, v in api["workers"].items() if k.startswith("smoke-")},
                                "metadata_api_body_bytes": api["metadata_api_body_bytes"]},
        "scenarios": scenarios,
    }
