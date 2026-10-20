"""Tamper only disposable copies; original fixture evidence is left byte-identical."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sqlite3

from .common import ROOT, digest, write_json
from .e008_audit import audit, rows, snapshot
from .e008_execute import make_unit, seed_archive
from .e008_memory import InvestigatorBridge


def cloned_case(study, destination, job, schedule):
    destination.mkdir(exist_ok=False)
    shutil.copy2(study / "registration.json", destination / "registration.json")
    identity = job["id"]
    while identity:
        original = study / "units" / identity
        shutil.copytree(original, destination / "units" / identity)
        ancestor = next(j for j in schedule if j["id"] == identity)
        identity = ancestor.get("source")
    return destination / "units" / job["id"]


def write_events(path, events):
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8", newline="\n")


def guard_checks(destination, world):
    run = destination / "direct-guards"
    make_unit(run)
    seed_archive(run, world["evidence"])
    outcomes = {}
    job = {"stage": "A", "condition": "C1", "budget": 1024, "protocol_version": None}
    with (run / "supervisor/guard.jsonl").open("x", encoding="utf-8") as log:
        bridge = InvestigatorBridge(run, "A", [], log, "scripted-fixture")
        try:
            bridge.configure(job)
            for label, name, args, exception in (
                ("command_in_memory_not_executable_tool", "run_shell", {"command": "touch INJECTION_EXECUTED"}, PermissionError),
                ("save_before_read_denied", "save_memory", {"content": "x", "encoding": "utf8"}, ValueError),
            ):
                try:
                    bridge.call(name, args)
                except exception:
                    outcomes[label] = True
                else:
                    raise AssertionError("guard failed: " + label)
            result = bridge.call("verify_evidence", {"record": world["evidence"][1]})
            outcomes["future_evidence_not_disclosed_even_for_correct_guess"] = result == {"reference": "EB", "available": False, "valid": None}
            bridge.call("read_protocol", {})
            bridge.call("read_memory", {})
            for _ in range(2):
                rejected = bridge.call("save_memory", {"content": "x" * 1025, "encoding": "utf8"})
                assert rejected["saved"] is False
            try:
                bridge.call("save_memory", {"content": "small", "encoding": "utf8"})
            except ValueError:
                outcomes["third_save_denied"] = True
            else:
                raise AssertionError("third save accepted")
            try:
                bridge.put("source:EA", world["evidence"][0])
            except ValueError:
                outcomes["immutable_source_slot_cannot_be_overwritten"] = True
            else:
                raise AssertionError("source slot overwritten")
        finally:
            bridge.close()
    with (run / "supervisor/guard-D.jsonl").open("x", encoding="utf-8") as log:
        bridge = InvestigatorBridge(run, "D", [], log, "scripted-fixture")
        try:
            bridge.configure(dict(job, stage="D", condition="C0"))
            try:
                bridge.call("save_memory", {"content": "successor cannot write", "encoding": "utf8"})
            except PermissionError:
                outcomes["successor_write_denied"] = True
            else:
                raise AssertionError("D wrote memory")
        finally:
            bridge.close()
    _, index, _ = snapshot(run / "state/continuum.sqlite3")
    outcomes["rejected_snapshots_absent"] = not any(k.startswith("state:") for k in index)
    assert all(outcomes.values())
    return outcomes


def verify(study, destination):
    study = Path(study).resolve(strict=True)
    destination = Path(destination).resolve()
    if not destination.is_relative_to((ROOT / "artifacts").resolve()):
        raise ValueError("negative copies must stay inside disposable artifacts")
    destination.mkdir(exist_ok=False)
    registration = json.loads((study / "registration.json").read_text())
    if not registration["fixture"]:
        raise ValueError("use an offline fixture, never a live experiment")
    world = json.loads((study / "oracle.json").read_text())["worlds"][0]
    schedule = registration["schedule"]
    network = rows(study / "provider.jsonl")
    before = {str(p.relative_to(study)): digest(p) for p in study.rglob("*") if p.is_file()}
    results = []

    def test(label, identity, mutate):
        job = next(j for j in schedule if j["id"] == identity)
        target = destination / label
        run = cloned_case(study, target, job, schedule)
        altered = copy.deepcopy(network)
        positive = audit(target, job, world, "scripted-fixture", altered, execution_study=study)
        if not positive["pass"]:
            raise ValueError("negative clone is not an intact positive control: " + str(positive))
        mutate(run, altered, job)
        negative = audit(target, job, world, "scripted-fixture", altered, execution_study=study)
        if negative["pass"]:
            raise AssertionError("forgery accepted: " + label)
        results.append({"case": label, "intact_pass": True, "tampered_rejected": True, "reason": negative["reason"]})

    def forged_model(run, net, job):
        for event in net:
            if event.get("worker") == job["id"] and event["event"] == "response":
                for call in event["response"]["output"]:
                    if call.get("name") == "save_memory":
                        args = json.loads(call["arguments"])
                        args["content"] += "FORGED"
                        call["arguments"] = json.dumps(args)
                        return
        raise AssertionError("no model save to tamper")
    test("forged_model_authorship", "j0001", forged_model)

    def hidden_history(run, net, job):
        path = run / "supervisor/session.jsonl"
        events = rows(path)
        for event in events:
            if event.get("event") == "worker_message" and event["message"]["channel"] == "responses":
                event["message"]["history"].insert(0, {"role": "system", "content": "Hidden prior conversation"})
                break
        for event in net:
            if event.get("worker") == job["id"] and event["event"] == "request_started":
                event["payload"]["input"].insert(0, {"role": "system", "content": "Hidden prior conversation"})
                break
        write_events(path, events)
    test("hidden_initial_history", "j0001", hidden_history)

    def mounted_oracle(run, net, job):
        path = run / "supervisor/session.jsonl"
        events = rows(path)
        command = next(e["command"] for e in events if e.get("event") == "command_execution")
        command[command.index("--mount") + 1] = f"type=bind,src={study},dst=/workspace"
        write_events(path, events)
    test("mounted_private_study", "j0001", mounted_oracle)

    def no_get(run, net, job):
        path = run / "supervisor/session.jsonl"
        events = rows(path)
        _, index, _ = snapshot(run / "state/continuum.sqlite3")
        parent = index["state:A"]
        ids = {(e["connection"], e["message"]["id"]) for e in events
               if e.get("channel") == "mcp" and e["message"].get("method") == "tools/call"
               and e["message"]["params"]["name"] == "continuum_get_object"
               and e["message"]["params"]["arguments"].get("sha256") == parent}
        assert ids
        events = [e for e in events if not (e.get("event") == "mcp_response" and (e.get("connection"), e["message"].get("id")) in ids)]
        write_events(path, events)
    test("missing_raw_get_object_receipt", "j0002", no_get)

    def wrong_origin(run, net, job):
        _, index, _ = snapshot(run / "state/continuum.sqlite3")
        with sqlite3.connect(run / "state/continuum.sqlite3") as db:
            sha = index["state:A"]
            origin = json.loads(db.execute("SELECT origin FROM knowledge_objects WHERE sha256=?", (sha,)).fetchone()[0])
            origin["actor"] = "invented-predecessor"
            db.execute("UPDATE knowledge_objects SET origin=? WHERE sha256=?", (json.dumps(origin), sha))
    test("wrong_snapshot_author", "j0001", wrong_origin)

    def unsafe_container(run, net, job):
        path = run / "supervisor/session.jsonl"
        events = rows(path)
        command = next(e["command"] for e in events if e.get("event") == "command_execution")
        command[command.index("--network") + 1] = "host"
        write_events(path, events)
    test("relaxed_container_isolation", "j0001", unsafe_container)

    def forged_authentication(run, net, job):
        path = run / "supervisor/session.jsonl"
        events = rows(path)
        receipt = next(e for e in events if e.get("event") == "tool_result" and e["name"] == "verify_evidence" and e["value"]["valid"] is False)
        receipt["value"]["valid"] = True
        call_id = next(c["call_id"] for e in net if e.get("worker") == job["id"] and e["event"] == "response"
                       for c in e["response"]["output"] if c.get("name") == "verify_evidence"
                       and json.loads(c["arguments"]) == receipt["arguments"])
        def edit(history):
            for entry in history:
                if entry.get("type") == "function_call_output" and entry["call_id"] == call_id:
                    entry["output"] = json.dumps(receipt["value"])
        for event in net:
            if event.get("worker") == job["id"] and event["event"] == "request_started":
                edit(event["payload"]["input"])
        for event in events:
            if event.get("event") == "worker_message" and event["message"]["channel"] == "responses":
                edit(event["message"]["history"])
        write_events(path, events)
    test("forged_source_authentication_success", "j0019", forged_authentication)
    guards = guard_checks(destination, world)
    after = {str(p.relative_to(study)): digest(p) for p in study.rglob("*") if p.is_file()}
    assert after == before, "original fixture evidence changed"
    report = {"pass": True, "original_fixture_unchanged": True, "fixture": str(study),
              "tampering_cases": results, "real_mcp_guard_checks": guards, "model_API_requests": 0}
    write_json(destination / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.study, args.output_directory)), flush=True)
