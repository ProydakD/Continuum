"""Read-only independent reconstruction from actual Responses, worker and MCP bytes."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .common import digest
from .e009_broker import frame, parse_frame, read_envelope
from .e009_episode_eval import score_chain, score_natural_chain
from .e009_protocol import assigned_seed, fresh_history, output_items, public_input, request_body, final_text
from .e009_revision import sha
from .e009_sources import EvidenceRegistry


def mcp_calls(directory):
    path = directory / "mcp/wire.jsonl"
    if not path.exists():
        return [], {"stdin": 0, "stdout": 0}
    pending, calls = {}, []
    totals = {"stdin": 0, "stdout": 0}
    for line in path.read_bytes().splitlines():
        event = json.loads(line)
        raw = base64.b64decode(event["base64"], validate=True)
        if len(raw) != event["bytes"]:
            raise ValueError("MCP byte accounting mismatch")
        totals[event["direction"]] += len(raw)
        msg = parse_frame(raw)
        if event["direction"] == "stdin" and "id" in msg:
            pending[msg["id"]] = msg
        elif event["direction"] == "stdout" and "id" in msg:
            req = pending.pop(msg["id"])
            if req["method"] == "tools/call" and "result" in msg:
                result = msg["result"]
                if result.get("isError"):
                    continue
                value = result.get("structuredContent")
                if value is None:
                    value = json.loads(result["content"][0]["text"])
                calls.append((req["params"]["name"], req["params"]["arguments"], value))
    if pending:
        raise ValueError("MCP request lacks recorded outcome")
    return calls, totals


def object_packet(obj, expected):
    raw = base64.b64decode(obj["content_base64"], validate=True)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("MCP object bytes/hash differ")
    return parse_frame(raw)


def audit_transport(directory, terminal, binding):
    """Recompute resource totals and bind each response to durable transport evidence."""
    path = directory / "provider-attempts.json"
    if not path.exists():
        if not binding["fixture"] and terminal.get("responses"):
            raise ValueError("live stage lacks durable transport evidence")
        return None
    attempts = json.loads(path.read_text(encoding="utf-8"))
    if len({a["id"] for a in attempts}) != len(attempts):
        raise ValueError("duplicate attempt identity")
    if any(a["status"] not in {"pending", "terminal"} for a in attempts):
        raise ValueError("unknown attempt state")
    if terminal["status"] == "completed" and any(a["status"] == "pending" for a in attempts):
        raise ValueError("completed stage has pending transport")
    for attempt in attempts:
        if attempt.get("response_body_file"):
            body_path = directory / "provider-bodies" / Path(attempt["response_body_file"]).name
            if digest(body_path) != attempt["response_sha256"]:
                raise ValueError("retained response bytes differ from transport")
            if hashlib.sha256(frame(json.loads(body_path.read_bytes()))).hexdigest() != attempt["response_json_sha256"]:
                raise ValueError("retained response JSON differs from transport")
        elif binding.get("protocol_version", 1) >= 2 and attempt.get("response_json_sha256"):
            raise ValueError("parsed live response lacks retained body")
        usage = attempt.get("usage")
        if usage is not None and (not isinstance(usage, dict) or not all(
                type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens"))):
            raise ValueError("invalid reported usage")
    expected = {"fixture": binding["fixture"], "transport_attempts": len(attempts),
                "submitted_or_uncertain": sum(a["status"] == "pending" or a.get("request_may_have_been_sent", False)
                                             for a in attempts),
                "unknown_usage_attempts": sum(a.get("usage_state") == "unknown" for a in attempts),
                "reported_input_tokens": sum((a.get("usage") or {}).get("input_tokens", 0) for a in attempts),
                "reported_output_tokens": sum((a.get("usage") or {}).get("output_tokens", 0) for a in attempts),
                "cost_usd": None}
    if frame(terminal["provider_accounting"]) != frame(expected):
        raise ValueError("provider accounting not equal to recorded attempts")
    request_hashes = set()
    for request_path in sorted((directory / "provider").glob("*-request.json")):
        request_sha = hashlib.sha256(frame(json.loads(request_path.read_text(encoding="utf-8")))).hexdigest()
        if request_sha in request_hashes:
            raise ValueError("duplicate provider request")
        request_hashes.add(request_sha)
        matching = [a for a in attempts if a.get("request_sha256") == request_sha]
        if not matching:
            raise ValueError("provider request lacks durable attempt")
        if (len({a["request_id"] for a in matching}) != 1
                or [a["ordinal"] for a in matching] != list(range(1, len(matching) + 1))):
            raise ValueError("retry identities/order differ")
        response_path = request_path.with_name(request_path.name.replace("-request", "-response"))
        if response_path.exists():
            response = json.loads(response_path.read_text(encoding="utf-8"))
            response_sha = hashlib.sha256(frame(response)).hexdigest()
            if response.get("model") != binding["provider_model"]:
                raise ValueError("response model differs from assigned model")
            if sum(a.get("reason") == "completed" and a.get("response_json_sha256") == response_sha
                   and a.get("reported_model") == binding["provider_model"] for a in matching) != 1:
                raise ValueError("provider response lacks exactly one completed attempt")
    if {a.get("request_sha256") for a in attempts} != request_hashes:
        raise ValueError("unregistered transport request")
    return expected


def replay(directory, expected_manifest, oracle):
    run = Path(directory).resolve(strict=True)
    if digest(run / "MANIFEST.json") != expected_manifest:
        raise ValueError("external manifest binding differs")
    manifest = json.loads((run / "MANIFEST.json").read_text(encoding="utf-8"))
    inventory = {p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()}
    if inventory != set(manifest) | {"MANIFEST.json"}:
        raise ValueError("raw inventory changed")
    for name, expected in manifest.items():
        target = (run / name).resolve(strict=True)
        if not target.is_relative_to(run) or digest(target) != expected:
            raise ValueError("raw file escaped or changed")
    read = lambda name: json.loads((run / name).read_text(encoding="utf-8"))
    binding, episode = read("binding.json"), read("private/episode.json")
    protocol_version = binding.get("protocol_version", 1)
    if sha(episode) != binding["episode_sha256"]:
        raise ValueError("episode binding differs")
    registry = EvidenceRegistry(read("private/catalog.json"), binding["catalog_sha256"])
    condition, track = binding["condition"], binding["track"]
    assignment = {k: binding[k] for k in ("episode", "track", "condition", "episode_sha256", "catalog_sha256")}
    publications, trace, container_ids, resources = [], [], [], []
    prior_index = {}
    for stage in "ABCDE":
        directory = run / stage
        terminal = read(f"{stage}/terminal.json")
        record = {"stage": stage, "instance_id": terminal["instance_id"], "terminal_status": terminal["status"]}
        calls, mcp_bytes = mcp_calls(directory)
        provider_accounting = audit_transport(directory, terminal, binding)
        commits = [(a, v) for n, a, v in calls if n == "continuum_checkpoint_task"]
        if len(commits) > 1:
            raise ValueError("multiple stage commits")
        objects = {a["sha256"]: v for n, a, v in calls if n == "continuum_put_object"}
        publication = measurement = index = None
        if commits:
            args, committed = commits[0]
            if args["result"] != committed["result"] or committed["lease_owner"] is not None:
                raise ValueError("checkpoint not acknowledged/released")
            index = json.loads(args["result"])
            if (index["stage"] != stage or index["condition"] != condition or index["assignment"] != assignment
                    or index["parent_memory_sha256"] != prior_index.get("memory_sha256")
                    or index != terminal.get("index") or not terminal.get("committed")):
                raise ValueError("durable assignment/parent binding differs")
            obj = objects[index["memory_sha256"]]
            packet = object_packet(obj, index["memory_sha256"])
            private = object_packet(objects[index["measurement_sha256"]], index["measurement_sha256"])
            for value in (packet, private):
                if value["actor"] != terminal["instance_id"] or value["stage"] != stage:
                    raise ValueError("durable object identity differs")
            if obj["origin"]["actor"] != terminal["instance_id"]:
                raise ValueError("server provenance mismatch")
            publication = read_envelope(packet["memory"], stage, index["memory_sha256"], obj["origin"])
            measurement = private["measurement"]
            record["published_memory"] = packet["memory"]
            record["claims"] = measurement.get("claims")
        elif terminal.get("committed"):
            raise ValueError("terminal claims an unobserved commit")
        if not (directory / "worker-wire.jsonl").exists():
            if terminal["status"] == "completed":
                raise ValueError("completed stage lacks wire evidence")
            trace.append(record)
            continue
        expected_public = public_input(episode, registry, stage, condition, track)
        if frame(read(f"{stage}/public.json")) != frame(expected_public):
            raise ValueError("stage public projection changed")
        history = fresh_history(expected_public)
        if (directory / "worker/repo/PROMPT.txt").exists():
            if frame(read(f"{stage}/worker/repo/PROMPT.txt")) != frame({"history": history}):
                raise ValueError("fresh prompt contains additional history")
        seed = assigned_seed(episode, condition, track, stage, protocol_version)
        if condition == "FULL-JOURNAL":
            journal = ([read_envelope(seed, None, None, {"actor": "registered-input-history"})] if seed else [])
            expected_read = {"memory": None, "journal": journal + deepcopy(publications),
                             "trust": "unverified_author_assertions"}
        elif condition == "C0":
            expected_read = read_envelope(None, None, None, None)
        elif publications:
            expected_read = publications[-1]
        else:
            expected_read = read_envelope(seed, None, None, {"actor": "registered-input-history"} if seed else None)
        events = [json.loads(line) for line in (directory / "worker-wire.jsonl").read_bytes().splitlines()]
        input_raw, output_raw = [], []
        pending, last, last_output = [], None, None
        seen_call_ids = set()
        response_number = reads = matched_publications = observed_tool_calls = 0
        observed_final = None
        read_bytes = 0
        request_bytes = 0
        for event in events:
            raw = base64.b64decode(event["base64"], validate=True)
            if event["bytes"] != len(raw):
                raise ValueError("worker byte mismatch")
            (input_raw if event["direction"] == "stdin" else output_raw).append(raw)
            msg = parse_frame(raw)
            if event["kind"] == "unprocessed_tail":
                if terminal["status"] == "completed":
                    raise ValueError("completed stage has unprocessed output")
                continue
            if event["direction"] == "stdout":
                channel = msg.get("channel")
                if channel == "hello":
                    info = json.loads(read(f"{stage}/inspect-command.json")["stdout"])[0]
                    if (info["Id"] != terminal["container_id"] or info["Config"]["Hostname"] != msg["hostname"]
                            or info["Image"] != binding["image"] or info["HostConfig"]["NetworkMode"] != "none"):
                        raise ValueError("container identity/boundary mismatch")
                    container_ids.append(info["Id"])
                elif channel == "responses":
                    if pending or frame(msg["history"]) != frame(history):
                        raise ValueError("history not reconstructed from same-stage output")
                    response_number += 1
                    request = read(f"{stage}/provider/{response_number:03}-request.json")
                    if frame(request) != frame(request_body(binding["provider_model"], history, stage, condition, binding["limits"]["output_tokens"], protocol_version)):
                        raise ValueError("provider request contains hidden input or changed protocol")
                    request_bytes += len(frame(request))
                elif channel == "tool":
                    if (not pending or msg["name"] != pending[0]["name"] or msg["call_id"] != pending[0]["call_id"]
                            or frame(msg["arguments"]) != frame(parse_frame(pending[0]["arguments"].encode() + b"\n"))):
                        raise ValueError("tool not bound to provider call")
                    last = msg
                    observed_tool_calls += 1
                    if msg["name"] == "publish" and publication is not None:
                        args = msg["arguments"]
                        if frame(args) == frame({"published_memory": publication["memory"], "measurement": measurement}):
                            matched_publications += 1
                elif channel == "final":
                    if pending or msg["text"] != final_text(last_output):
                        raise ValueError("final not bound to provider output")
                    observed_final = parse_frame(msg["text"].encode() + b"\n")
                    if frame(observed_final) != frame(terminal.get("final")):
                        raise ValueError("terminal answer differs from actual provider")
                else:
                    raise ValueError("unknown worker trace channel")
            elif event["kind"] == "response":
                response = read(f"{stage}/provider/{response_number:03}-response.json")
                if frame(msg) != frame({"result": response}):
                    raise ValueError("response differs from recorded provider body")
                last_output = output_items(response, protocol_version)
                history.extend(last_output)
                output_calls = [item for item in last_output if item.get("type") == "function_call"]
                ids = {call["call_id"] for call in output_calls}
                if ids & seen_call_ids:
                    raise ValueError("repeated provider call identity")
                seen_call_ids.update(ids)
                pending = output_calls
            elif event["kind"] == "tool":
                if not pending or last is None:
                    raise ValueError("unexpected function output")
                if last["name"] == "read_memory" and last["arguments"] == {} and "result" in msg:
                    if frame(msg["result"]) != frame(expected_read):
                        raise ValueError("memory read not equal to explicit public predecessor")
                    reads += 1
                    read_bytes += len(raw)
                    if len(raw) > (131072 if condition == "FULL-JOURNAL" else 8192):
                        raise ValueError("memory read over registered bound")
                if last["name"] == "publish" and msg.get("result", {}).get("saved"):
                    if publication is None or msg["result"]["sha256"] != publication["sha256"]:
                        raise ValueError("publication receipt lacks durable proof")
                history.append({"type": "function_call_output", "call_id": pending.pop(0)["call_id"],
                                "output": raw.decode()})
                last = None
            else:
                raise ValueError("unknown controller reply")
        if b"".join(input_raw) != (directory / "worker-input.bin").read_bytes():
            raise ValueError("stdin stream and ledger differ")
        if b"".join(output_raw) != (directory / "worker-output.bin").read_bytes():
            raise ValueError("stdout stream and ledger differ")
        if publication is not None and matched_publications != 1:
            raise ValueError("durable publication not equal to one provider-authored tool request")
        if terminal["status"] == "completed":
            if protocol_version >= 2 and observed_tool_calls > binding["limits"].get("tool_calls", 24):
                raise ValueError("completed stage exceeded tool call budget")
            if reads != 1 or observed_final is None or terminal["exit_status"] != 0:
                raise ValueError("unproven technical completion")
            if stage != "E" and (publication is None or observed_final != {"status": "published"}):
                raise ValueError("completed writer did not publish")
        if terminal["status"] == "injected_crash_after_commit":
            killed = read(f"{stage}/kill-command.json")
            if terminal["exit_status"] != 137 or killed["exit_status"] or publication is None:
                raise ValueError("unproven committed crash")
        if stage == "E" and observed_final is not None:
            record.update(observed_final)
        if publication is not None:
            publications.append(publication)
            prior_index = index
        trace.append(record)
        if "tool_calls" in terminal and terminal["tool_calls"] != observed_tool_calls:
            raise ValueError("tool call accounting differs from wire")
        resources.append({"stage": stage, "mcp_bytes": mcp_bytes, "read_envelope_bytes": read_bytes,
                          "provider_request_bytes": request_bytes, "response_calls": response_number,
                          "tool_calls": observed_tool_calls,
                          "provider_accounting": provider_accounting})
    if len(set(container_ids)) != len(container_ids):
        raise ValueError("container reused between stages")
    if frame(read("terminal.json")) != frame([read(f"{s}/terminal.json") for s in "ABCDE"]):
        raise ValueError("terminal aggregate differs")
    score = (score_natural_chain(episode, trace, oracle, condition) if track == "natural"
             else score_chain(episode, trace, oracle, condition))
    if any(digest(run / name) != expected for name, expected in manifest.items()):
        raise ValueError("replay mutated raw files")
    return {"score": score, "trace": trace, "resources": resources, "raw_files_verified": len(manifest),
            "raw_unchanged": True, "fixture": binding["fixture"],
            "api_calls": 0 if binding["fixture"] else None}
