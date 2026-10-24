"""Model-capable isolated E009 controller. Provider receives public request bodies only."""
from copy import deepcopy
import base64
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

from .common import PROJECT, command, digest, runtime_identity, source_hashes
from .e009_broker import BinaryMCP, MemoryBroker, frame, parse_frame
from .e009_protocol import assigned_seed, final_text, fresh_history, output_items, public_input, request_body
from .e009_provider import ProviderFailure
from .e009_raw import write_once
from .e009_revision import sha
from .e009_sources import EvidenceRegistry, evidence_catalog
from .e009_sandbox_gate import pipe_reader, worker_command
from .profiles import create_worker

LIMITS = {"stage_seconds": 120, "responses": 24, "request_seconds": 45, "output_tokens": 16000}


def execute_stage(run, episode, registry: EvidenceRegistry, stage, condition, track, provider, task_id,
                  assignment, image, limits, *, crash_after_commit=False):
    directory = run / stage
    directory.mkdir()
    actor = run.name + ":" + stage + ":" + uuid.uuid4().hex
    public = public_input(episode, registry, stage, condition, track)
    write_once(directory / "public.json", public)
    report = {"stage": stage, "instance_id": actor, "status": "failed", "exit_status": None,
              "task_id": task_id, "committed": False, "responses": 0, "provider_models": [],
              "container_id": None, "api_calls": 0 if provider.fixture else None}
    events = []
    transport = process = reader = inbox = None
    child_stdin, child_stdout = [], []
    worker = directory / "worker"
    name = "e009-response-" + uuid.uuid4().hex[:16]
    started = time.monotonic()
    initial = None

    def event(direction, raw, kind):
        events.append({"direction": direction, "bytes": len(raw), "base64": base64.b64encode(raw).decode(),
                       "kind": kind, "monotonic_ns": time.monotonic_ns()})

    def deliver(reply, kind):
        raw = frame(reply)
        if len(raw) > 262144:
            raise ValueError("worker reply frame limit")
        process.stdin.write(raw)
        process.stdin.flush()
        child_stdin.append(raw)
        event("stdin", raw, kind)
        return raw.decode("utf-8")

    try:
        if (run / "STOP").exists():
            report["status"] = "stopped"
            return report
        create_worker(worker, stage if stage in "ABC" else "C", "none")
        history = fresh_history(public)
        write_once(worker / "repo/SESSION.json", {"history": history})
        # create_worker makes PROMPT.txt; replace only this new scaffold before hashing.
        (worker / "repo/PROMPT.txt").write_bytes((worker / "repo/SESSION.json").read_bytes())
        initial = source_hashes(worker)
        write_once(directory / "worker-manifest.json", initial)
        transport = BinaryMCP(run / "private/state.sqlite3", actor, run.name, directory / "mcp", provider.model)
        broker = MemoryBroker(transport, stage, condition, actor, registry, task_id=task_id,
                              seed=assigned_seed(episode, condition, track, stage), assignment=assignment)
        report["task_id"] = broker.task["id"]
        argv = worker_command(image, name, worker, "responses.py")
        write_once(directory / "command.json", {"command": argv, "cwd": str(PROJECT)})
        pending = None
        last_output = None
        final = None
        with (directory / "stderr.bin").open("xb") as stderr:
            process = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
            inbox = queue.Queue(maxsize=32)
            reader = threading.Thread(target=pipe_reader, args=(process.stdout, inbox), daemon=True)
            reader.start()
            while True:
                remaining = limits["stage_seconds"] - (time.monotonic() - started)
                if (run / "STOP").exists():
                    report["status"] = "stopped"
                    break
                if remaining <= 0:
                    report["status"] = "timeout"
                    break
                try:
                    raw = inbox.get(timeout=min(0.5, remaining))
                except queue.Empty:
                    continue
                if not raw:
                    break
                child_stdout.append(raw)
                message = parse_frame(raw)
                event("stdout", raw, message.get("channel"))
                channel = message.get("channel")
                if channel == "hello":
                    if report["container_id"] is not None:
                        raise ValueError("duplicate hello")
                    inspected = command(["docker", "inspect", name], timeout=15)
                    write_once(directory / "inspect-command.json", inspected)
                    if inspected["exit_status"]:
                        raise RuntimeError("container inspection failed")
                    info = json.loads(inspected["stdout"])[0]
                    if (info["Image"] != image or info["HostConfig"]["NetworkMode"] != "none"
                            or not info["HostConfig"]["ReadonlyRootfs"]
                            or info["Config"]["User"] != "65534:65534"
                            or message["hostname"] != info["Config"]["Hostname"]
                            or any(e.startswith(("API_KEY=", "OPENAI_API_KEY=")) for e in info["Config"]["Env"])):
                        raise PermissionError("container boundary mismatch")
                    report["container_id"] = info["Id"]
                    continue
                if report["container_id"] is None:
                    raise PermissionError("no observed container boundary")
                if channel == "responses":
                    if pending is not None or final is not None or frame(message.get("history")) != frame(history):
                        raise ValueError("history rewrite or unfinished function call")
                    report["responses"] += 1
                    if report["responses"] > limits["responses"]:
                        report["status"] = "response_limit"
                        break
                    request = request_body(provider.model, history, stage, condition, limits["output_tokens"])
                    number = report["responses"]
                    write_once(directory / f"provider/{number:03}-request.json", request)
                    response = provider.respond(actor, deepcopy(request), timeout=min(remaining, limits["request_seconds"]))
                    write_once(directory / f"provider/{number:03}-response.json", response)
                    output = output_items(response)
                    report["provider_models"].append(response.get("model"))
                    last_output = output
                    history.extend(output)
                    calls = [item for item in output if item.get("type") == "function_call"]
                    pending = calls[0] if calls else None
                    deliver({"result": response}, "response")
                elif channel == "tool":
                    if (pending is None or set(message) != {"channel", "name", "call_id", "arguments"}
                            or message["name"] != pending["name"] or message["call_id"] != pending["call_id"]
                            or frame(message["arguments"]) != frame(parse_frame(pending["arguments"].encode() + b"\n"))):
                        raise ValueError("worker tool call not issued by provider")
                    try:
                        value = broker.call(message["name"], message["arguments"])
                        reply = {"result": value}
                    except (PermissionError, ValueError, KeyError, TypeError):
                        reply = {"error": "capability_rejected"}
                    if broker.committed:
                        report["committed"] = True
                        report["index"] = broker.index
                    if message["name"] == "publish" and broker.committed and crash_after_commit:
                        killed = command(["docker", "kill", name], timeout=15)
                        write_once(directory / "kill-command.json", killed)
                        if killed["exit_status"]:
                            raise RuntimeError("injected kill failed")
                        report["status"] = "injected_crash_after_commit"
                        report["receipt_delivered"] = False
                        break
                    serialized = deliver(reply, "tool")
                    history.append({"type": "function_call_output", "call_id": pending["call_id"], "output": serialized})
                    pending = None
                elif channel == "final":
                    if pending is not None or final is not None or message.get("text") != final_text(last_output):
                        raise ValueError("final differs from provider output")
                    final = parse_frame(message["text"].encode() + b"\n")
                    if not broker.reads or stage != "E" and (not broker.committed or final != {"status": "published"}):
                        raise ValueError("final lacks required read/publication")
                    if stage == "E" and (not isinstance(final, dict) or set(final) != {"answer", "basis"}):
                        raise ValueError("invalid final measurement shape")
                    report["final"] = final
                else:
                    raise PermissionError("unknown worker channel")
            if report["status"] in {"stopped", "timeout", "response_limit"} and process.poll() is None:
                write_once(directory / "stop-command.json", command(["docker", "kill", name], timeout=15))
            process.stdin.close()
            report["exit_status"] = process.wait(timeout=20)
            reader.join(timeout=2)
            while not inbox.empty():
                tail = inbox.get_nowait()
                if tail:
                    child_stdout.append(tail)
                    event("stdout", tail, "tail")
            if report["status"] == "injected_crash_after_commit":
                if report["exit_status"] != 137:
                    raise ValueError("kill exit not observed")
            elif report["status"] == "failed" and report["exit_status"] == 0 and final is not None:
                report["status"] = "completed"
    except Exception as error:
        # No exception text: provider errors may contain request credentials.
        report["failure_type"] = type(error).__name__
        if isinstance(error, ProviderFailure):
            report["failure_reason"] = error.reason
            if error.reason == "operator_stop":
                report["status"] = "stopped"
    finally:
        if process is not None:
            if process.poll() is None:
                write_once(directory / "cleanup-command.json", command(["docker", "rm", "-f", name], timeout=15))
                process.wait(timeout=15)
            report["exit_status"] = process.returncode
            if not process.stdin.closed:
                process.stdin.close()
            if reader is not None:
                reader.join(timeout=2)
            if inbox is not None:
                while not inbox.empty():
                    tail = inbox.get_nowait()
                    if tail:
                        child_stdout.append(tail)
                        event("stdout", tail, "unprocessed_tail")
            if not process.stdout.closed:
                process.stdout.close()
        if transport is not None:
            transport.close()
            report["mcp_bytes"] = transport.counts
        if initial is not None and source_hashes(worker) != initial:
            report["status"] = "failed"
            report["failure_type"] = "WorkerInputChanged"
        if hasattr(provider, "accounting"):
            report["provider_accounting"] = provider.accounting(actor)
            write_once(directory / "provider-attempts.json", provider.ledger.records(actor))
        report["seconds"] = time.monotonic() - started
        (directory / "worker-input.bin").write_bytes(b"".join(child_stdin))
        (directory / "worker-output.bin").write_bytes(b"".join(child_stdout))
        (directory / "worker-wire.jsonl").write_bytes(b"".join(map(frame, events)))
        write_once(directory / "terminal.json", report)
    return report


def run_chain(directory, episode, condition, track, provider, image, *,
              limits=None, crash_stage=None, stop_before=None):
    run = Path(directory).resolve()
    run.mkdir(parents=True, exist_ok=False)
    limits = dict(LIMITS if limits is None else limits)
    catalog = evidence_catalog(episode)
    registry = EvidenceRegistry(catalog, sha(catalog))
    assignment = {"episode": episode["id"], "track": track, "condition": condition,
                  "episode_sha256": sha(episode), "catalog_sha256": sha(catalog)}
    binding = {"schema": "e009-responses-run-v1", **assignment, "image": image, "limits": limits,
               "provider_model": provider.model, "fixture": provider.fixture,
               "crash_stage": crash_stage, "stop_before": stop_before}
    write_once(run / "private/episode.json", episode)
    write_once(run / "private/catalog.json", catalog)
    write_once(run / "binding.json", binding)
    write_once(run / "provenance.json", {"runtime": runtime_identity(),
        "head": command(["git", "rev-parse", "HEAD"])["stdout"].strip(),
        "source_hashes": {p.relative_to(PROJECT).as_posix(): digest(p)
                          for p in sorted((PROJECT / "research").rglob("e009*.py"))},
        "runtime_hashes": source_hashes(PROJECT / "research/e009_runtime")})
    records, task_id, recoverable = [], None, True
    for stage in "ABCDE":
        if stage == stop_before:
            (run / "STOP").write_text("registered synthetic STOP test\n", encoding="utf-8")
        if recoverable or (run / "STOP").exists():
            record = execute_stage(run, episode, registry, stage, condition, track, provider, task_id,
                                   assignment, image, limits, crash_after_commit=stage == crash_stage)
        else:
            (run / stage).mkdir()
            record = {"stage": stage, "instance_id": run.name + ":" + stage,
                      "status": "upstream_missing", "committed": False, "responses": 0, "exit_status": None}
            write_once(run / stage / "terminal.json", record)
        task_id = record.get("task_id", task_id)
        recoverable = bool(record["committed"])
        records.append(record)
    write_once(run / "terminal.json", records)
    manifest = {p.relative_to(run).as_posix(): digest(p) for p in sorted(run.rglob("*")) if p.is_file()}
    write_once(run / "MANIFEST.json", manifest)
    return {"directory": str(run), "manifest_sha256": digest(run / "MANIFEST.json"),
            "statuses": [r["status"] for r in records], "fixture": provider.fixture,
            "response_calls": sum(r["responses"] for r in records)}
