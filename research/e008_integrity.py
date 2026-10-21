"""Independent, read-only completion bindings; no execution or state repair."""
from collections import Counter
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from .common import PROJECT, digest, source_hashes
from .e008_execute import ledger_key
from .e008_live import REGISTRATION, git_bytes, load
from .e008_locks import TERMINAL, read
from .e008_reference import audit_reference


def table(path, name):
    if name not in {"jobs", "attempts", "metadata_attempts", "runtime_policy", "policy"}:
        raise ValueError("unregistered ledger table")
    with closing(sqlite3.connect(Path(path).resolve(strict=True).as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM " + name)]


def timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def job_timeline(study, jobs):
    rows = table(study / "jobs.sqlite3", "jobs")
    index = {r["id"]: r for r in rows}
    if set(index) != {ledger_key(j) for j in jobs}:
        raise PermissionError("job timeline has missing or foreign assignments")
    previous = 0
    result = {}
    for ordinal, job in enumerate(jobs):
        row = index[ledger_key(job)]
        if (row["ordinal"] != ordinal or not timestamp(row["started"]) or not timestamp(row["finished"])
                or row["started"] < previous or row["finished"] < row["started"]
                or row["status"] not in TERMINAL):
            raise PermissionError("unfinished, overlapping or reversed job timeline")
        previous = row["finished"]
        result[job["id"]] = row
    for name, phases, subsequent in (
            ("calibration", {"calibration"}, {"development", "validation", "test", "robustness"}),
            ("protocol", {"calibration", "development", "validation"}, {"test", "robustness"})):
        lock = read(study / "locks" / (name + ".json"))
        earlier = [result[j["id"]]["finished"] for j in jobs if j["phase"] in phases]
        later = [result[j["id"]]["started"] for j in jobs if j["phase"] in subsequent]
        if not earlier or not later or not timestamp(lock["created_at"]) or not max(earlier) <= lock["created_at"] <= min(later):
            raise PermissionError("decision lock not between its assigned source and future phases")
    return result


def network_ledger(study, registration, network, *, job_times=None):
    """Cross-check independent SQLite reservations with logged terminal events."""
    attempts = table(study / "provider-ledger.sqlite3", "attempts")
    metadata = table(study / "provider-ledger.sqlite3", "metadata_attempts")
    events, get_events = {}, []
    for event in network.all():
        kind = event.get("event")
        if kind == "request_started":
            identity = event["attempt"]
            if identity in events:
                raise PermissionError("duplicate network attempt")
            events[identity] = {"worker": event["worker"], "terminal": None, "usage": None}
        elif kind in ("response", "request_failed"):
            identity = event["attempt"]
            if identity not in events:
                raise PermissionError("network result without reservation start")
            row = events[identity]
            if kind == "response":
                if row["terminal"] is not None or event["worker"] != row["worker"]:
                    raise PermissionError("duplicate or foreign response")
                row["usage"] = event["response"].get("usage")
                row["terminal"] = "completed"
            elif row["terminal"] in (None, "completed"):
                row["terminal"] = "failed_or_unknown"
            else:
                raise PermissionError("duplicate failure")
        elif kind == "transport_bytes" and event["method"] == "GET":
            get_events.append(event)
    if len({r["id"] for r in attempts}) != len(attempts) or {r["id"] for r in attempts} != set(events):
        raise PermissionError("spend ledger and trace attempt sets differ")
    allowed = {j["id"] for j in registration["schedule"]} | {"smoke-primary", "smoke-secondary"}
    maximum = registration["resources"]
    by_worker = Counter()
    for row in attempts:
        logged = events[row["id"]]
        if (row["worker"] not in allowed or row["worker"] != logged["worker"]
                or row["outcome"] not in ("completed", "failed_or_unknown")
                or row["outcome"] != logged["terminal"] or not timestamp(row["started"])):
            raise PermissionError("terminal spend outcome/worker/time differs from trace")
        if row["outcome"] == "completed" and json.loads(row["usage"]) != logged["usage"]:
            raise PermissionError("reported usage differs from successful spend record")
        if row["outcome"] == "failed_or_unknown" and json.loads(row["usage"]) is not None:
            raise PermissionError("failed spend reservation unexpectedly claims known usage")
        if job_times is not None and row["worker"] in job_times:
            timing = job_times[row["worker"]]
            if not timing["started"] <= row["started"] <= timing["finished"]:
                raise PermissionError("request outside its assigned context lifetime")
        by_worker[row["worker"]] += 1
    if (len(attempts) > maximum["maximum_response_attempts"]
            or any(count > maximum["workers"][worker] for worker, count in by_worker.items())
            or len(metadata) > maximum["maximum_metadata_attempts"]):
        raise PermissionError("registered network ceilings exceeded")
    if len(metadata) != len(get_events):
        raise PermissionError("unmeasured metadata reservation; cannot claim complete overhead")
    for row, observed in zip(sorted(metadata, key=lambda r: r["id"]), get_events):
        if not timestamp(row["started"]) or row["outcome"] not in ("completed", "failed_or_unknown"):
            raise PermissionError("pending or invalid metadata reservation")
        if row["outcome"] == "completed" and (
                not observed["request_sent"] or not observed["response_complete"] or observed["http_status"] != 200):
            raise PermissionError("successful metadata reservation lacks complete HTTP200 trace")
    policies = table(study / "provider-ledger.sqlite3", "runtime_policy")
    if len(policies) != 1 or json.loads(policies[0]["value"]) != maximum:
        raise PermissionError("resource policy differs from frozen registration")
    if (not timestamp(policies[0]["started"]) or not timestamp(policies[0]["last_wall"])
            or policies[0]["last_wall"] < policies[0]["started"]
            or any(r["started"] < policies[0]["started"] for r in attempts + metadata)):
        raise PermissionError("network reservations outside observed resource-clock lifetime")
    authorization = table(study / "provider-ledger.sqlite3", "policy")
    if (len(authorization) != 1 or json.loads(authorization[0]["value"]) !=
            {"unbounded": True, "budget": "None", "upper": "None"} or any(r["reserved"] != "0" for r in attempts)):
        raise PermissionError("spend authorization/reservations differ from explicit unbounded policy")
    return {"response_attempts": len(attempts), "metadata_attempts": len(metadata),
            "responses_by_worker": dict(by_worker),
            "failed_or_unknown": sum(r["outcome"] == "failed_or_unknown" for r in attempts),
            "first_reservation": min((r["started"] for r in attempts + metadata), default=None),
            "runtime_policy_started": policies[0]["started"],
            "ledger_sha256": digest(study / "provider-ledger.sqlite3")}


def admission(study, registration, network, timeline, *, amendment_path=None, resumption_path=None):
    """Actual Git blob binding plus observed local admission order, not attestation."""
    if registration["fixture"]:
        return {"pass": False, "not_applicable": "scripted fixture is not a preregistered model study"}
    loaded, _, _ = load(study, amendment_path=amendment_path, resumption_path=resumption_path)
    if loaded != registration:
        raise PermissionError("live registration changed")
    gate = read(study / "live-gate.json")
    for name, expected in {**registration["implementation_hashes"],
                           REGISTRATION: digest(study / "registration.json")}.items():
        if hashlib.sha256(git_bytes(PROJECT, "show", gate["commit"] + ":" + name)).hexdigest() != expected:
            raise PermissionError("prepared commit did not contain frozen source/registration")
    proof = network_ledger(study, registration, network, job_times=timeline)
    started = read(study / "network-start.json")["at"]
    if (not all(timestamp(v) for v in (gate["prepared_at"], started, proof["first_reservation"]))
            or not gate["prepared_at"] <= started <= proof["first_reservation"]
            or any(r["started"] < started for r in timeline.values())):
        raise PermissionError("network/context preceded committed admission")
    transition = None
    if amendment_path:
        from .e008_transition import audit_transition
        transition = audit_transition(study, registration, read(amendment_path), timeline,
                                      resumption=read(resumption_path) if resumption_path else None)
    operational = None
    if resumption_path:
        from .e008_resumption import audit_resumption
        operational = audit_resumption(study, read(resumption_path), timeline)
    return {"pass": True, **proof, "model_transition": transition, "operational_resumption": operational,
            "prepared_commit": gate["commit"], "prepared_at": gate["prepared_at"],
            "network_started": started, "limitation": "Local ledger chronology, not trusted timestamp or provider attestation."}


def reference_binding(study, corpus_path, gold_manifest, worlds, gold):
    """Re-audit only already completed cold REF records; never run a solver."""
    study = Path(study).resolve(strict=True)
    before = source_hashes(study)
    reg, saved = read(study / "registration.json"), read(study / "report.json")
    if (reg["kind"] != "cold-algorithmic-reference" or reg["corpus_sha256"] != digest(corpus_path)
            or reg["gold_manifest_sha256"] != digest(gold_manifest)
            or reg["worlds"] != [w["id"] for w in worlds] or set(gold) != set(reg["worlds"])
            or saved["registration_sha256"] != digest(study / "registration.json")
            or not saved["complete"] or not saved["pass"]):
        raise PermissionError("REF registration/corpus/gold/report binding differs")
    for name, sha in reg["program_hashes"].items():
        if digest(PROJECT / name) != sha:
            raise PermissionError("REF program source differs")
    outcomes = {}
    for world in worlds:
        run = study / "references" / world["id"]
        checked = audit_reference(run, reg["image"], world, gold[world["id"]])
        if checked != read(run / "audit.json") or digest(run / "audit.json") != saved["outcome_hashes"][world["id"]]:
            raise PermissionError("cold REF raw result differs from report")
        outcomes[world["id"]] = checked
    by_split = {}
    for split in sorted({w["split"] for w in worlds}):
        group = [outcomes[w["id"]] for w in worlds if w["split"] == split]
        by_split[split] = {"worlds": len(group), "pass": sum(r["pass"] for r in group),
                          "new_correct": sum(r["new_correct"] for r in group), "new_total": sum(r["new_total"] for r in group)}
    if by_split != saved["by_split"] or before != source_hashes(study):
        raise PermissionError("REF aggregate or raw files changed")
    return {"pass": all(r["pass"] for r in outcomes.values()), "worlds": len(worlds), "by_split": by_split,
            "report_sha256": digest(study / "report.json"), "raw_manifest": before,
            "cold_worker_executions_started": 0, "scope": reg["scope"], "outcomes": outcomes}
