"""Reconstruct actual E008 API/tool/MCP lineage, independently of bridge decisions."""
import base64
import hashlib
import json

from .common import PROJECT, digest, source_hashes
from .e003_audit import pairs, read_db


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def context_network(study, job):
    from .e008_network import span_events
    path = study / "units" / job["id"] / "provider-span.json"
    if path.exists():
        return span_events(study / "provider.jsonl", json.loads(path.read_text(encoding="utf-8")), job["id"])
    # Historical immutable fixtures predate spans; do not rewrite their files.
    return rows(study / "provider.jsonl")


def snapshot(path):
    db = read_db(path)
    objects = {obj["sha256"]: obj for obj in db["knowledge_objects"]}
    if len(db["tasks"]) != 1:
        raise ValueError("one knowledge archive task required")
    index = json.loads(db["tasks"][0]["result"])
    if any(hashlib.sha256(obj["content"]).hexdigest() != sha for sha, obj in objects.items()):
        raise ValueError("corrupt durable object")
    if any(sha not in objects for sha in index.values()):
        raise ValueError("dangling archive slot")
    return db, index, objects


def network_chain(run, result, events, network, model, tools, limits):
    messages = [e["message"] for e in events if e.get("event") == "worker_message"]
    histories = [m["history"] for m in messages if m["channel"] == "responses"]
    text = json.loads((run / "workers" / result["job"]["stage"] / "repo/PROMPT.txt").read_text())["prompt"]
    if not histories or histories[0] != [{"role": "user", "content": text}]:
        raise ValueError("hidden or nonfresh initial history")
    requests = [e for e in network if e.get("worker") == run.name and e["event"] == "request_started"]
    responses = [e for e in network if e.get("worker") == run.name and e["event"] == "response"]
    actions = [m for m in messages if m["channel"] == "tool"]
    receipts = [e for e in events if e.get("event") == "tool_result"]
    if len(requests) != len(responses) or len(requests) != len(histories) or len(actions) != len(receipts):
        raise ValueError("network/tool receipt count mismatch")
    if len(requests) > limits["responses_per_context"]:
        raise ValueError("response count exceeds registration")
    reconstructed, used, final = histories[0], 0, None
    crash = result["status"] == "injected_crash_after_commit"
    for i, (request, response) in enumerate(zip(requests, responses)):
        payload = request["payload"]
        if set(payload) != {"model", "input", "tools", "store", "max_output_tokens", "parallel_tool_calls"}:
            raise ValueError("unexpected API context fields")
        if payload["input"] != reconstructed or histories[i] != reconstructed or request["attempt"] != response["attempt"]:
            raise ValueError("unbound API context/response")
        if payload["model"] != model or payload["tools"] != tools or payload["store"] is not False or payload["parallel_tool_calls"] is not False:
            raise ValueError("API model/tools/storage differ")
        if payload["max_output_tokens"] != limits["output_tokens"] or len(json.dumps(payload).encode()) > 262144:
            raise ValueError("API request/output envelope differs")
        returned = response["response"]
        if returned["model"] != model or returned["status"] != "completed":
            raise ValueError("returned model/status mismatch")
        reconstructed = reconstructed + returned["output"]
        calls = [v for v in returned["output"] if v.get("type") == "function_call"]
        if calls:
            for call in calls:
                if used >= len(actions):
                    raise ValueError("model tool call not executed")
                action, receipt = actions[used], receipts[used]
                args = json.loads(call["arguments"])
                if action["name"] != call["name"] or receipt["name"] != call["name"] or json_bytes(action["arguments"]) != json_bytes(args) or json_bytes(receipt["arguments"]) != json_bytes(args):
                    raise ValueError("tool bytes not authored by recorded model")
                used += 1
                if crash and used == len(receipts):
                    if call["name"] != "save_memory" or not receipt["value"].get("saved") or i != len(requests) - 1:
                        raise ValueError("invalid crash receipt")
                else:
                    reconstructed.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(receipt["value"])})
        else:
            text = "".join(p.get("text", "") for v in returned["output"] if v.get("type") == "message" for p in v.get("content", []))
            final = json.loads(text)
            if i != len(requests) - 1:
                raise ValueError("API continued after final")
    finals = [json.loads(m["line"]) for m in messages if m["channel"] == "worker"]
    if used != len(receipts):
        raise ValueError("unused receipt")
    if crash:
        killed = [e for e in events if e.get("event") == "injected_crash_after_commit"]
        if final is not None or finals or len(killed) != 1 or killed[0]["receipt_delivered"] or killed[0]["kill_result"]["exit_status"] != 0 or result["exit_status"] != 137:
            raise ValueError("crash not observed before acknowledgement/final")
    elif final != result.get("answer") or finals != [final]:
        raise ValueError("final not bound to returned model answer")
    return receipts


def verify_container(study, job, events, registration, *, execution_study=None):
    commands = [e["command"] for e in events if e.get("event") == "command_execution"]
    if len(commands) != 1:
        raise ValueError("missing unique container execution")
    argv = commands[0]
    for flag, value in (("--network", "none"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges"),
                        ("--user", "65534:65534"), ("--pids-limit", "128"), ("--memory", "256m"), ("--cpus", "1"),
                        ("--pull", "never"), ("--entrypoint", "python")):
        if argv.count(flag) != 1 or argv[argv.index(flag) + 1] != value:
            raise ValueError("container isolation flags differ")
    if "--read-only" not in argv or argv[-2:] != [registration["image"], "/runtime/e002_worker.py"] or argv.count("--mount") != 6:
        raise ValueError("container image/mount count/runtime differs")
    executed_study = execution_study if execution_study is not None else study
    executed_worker = (executed_study / "units" / job["id"] / "workers" / job["stage"]).resolve()
    expected = ["docker", "run", "--rm", "--pull", "never", "-i", "--name",
                "continuum-" + executed_study.name + "-" + job["id"],
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--user", "65534:65534",
                "--pids-limit", "128", "--memory", "256m", "--cpus", "1",
                "--tmpfs", "/tmp:rw,nosuid,size=128m", "--tmpfs", "/home/research:rw,nosuid,size=64m",
                "--workdir", "/workspace", "--env", "HOME=/home/research", "--env", "CODEX_HOME=/codex-home",
                "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONUNBUFFERED=1",
                "--env", "PYTHONNOUSERSITE=1", "--env", "OLLAMA_HOST=127.0.0.1:11434",
                "--env", "OLLAMA_MODELS=/models", "--entrypoint", "python"]
    for source, target, readonly in (
        (executed_worker / "repo", "/workspace", False),
        (executed_worker / "codex-home", "/codex-home", False),
        (executed_worker / "codex-home/config.toml", "/codex-home/config.toml", True),
        (executed_worker / "repo/AGENTS.md", "/workspace/AGENTS.md", True),
        (executed_worker / "skills", "/workspace/.agents/skills", True),
        (PROJECT / "research/worker_runtime", "/runtime", True),
    ):
        expected += ["--mount", f"type=bind,src={source.resolve()},dst={target}" + (",readonly" if readonly else "")]
    expected += [registration["image"], "/runtime/e002_worker.py"]
    if argv != expected:
        raise ValueError("container mounts/environment/arguments differ from isolated execution contract")


def audit(study, job, world, model, network=None, *, execution_study=None):
    run = study / "units" / job["id"]
    result = json.loads((run / "result.json").read_text())
    try:
        if result["status"] not in ("completed", "budget_rejected", "injected_crash_after_commit"):
            return {"pass": False, "executed_successfully": False, "reason": result["status"]}
        if result["job"] != job or (result["status"] != "injected_crash_after_commit" and result["exit_status"] != 0):
            raise ValueError("terminal job/exit mismatch")
        worker = run / "workers" / job["stage"]
        if source_hashes(worker) != json.loads((run / "context-manifest.json").read_text()):
            raise ValueError("worker input mutation")
        from .e008_protocol import prompt, tools_for
        sanitized = {k: world[k] for k in ("evidence", "panel", "successor")}
        text = json.loads((worker / "repo/PROMPT.txt").read_text())["prompt"]
        if text != prompt(job, sanitized):
            raise ValueError("prompt uses private oracle fields")
        data = json.loads(text.split("PUBLIC_INPUT: ", 1)[1])
        allowed = {"A": ["EA"], "B": ["EA", "EB"], "C": ["EA", "EB", "EC"], "D": ["EA", "EB", "EC"]}[job["stage"]]
        if job["condition"] in ("C0", "SINGLE-A", "SINGLE-B"):
            allowed = [{"C0": "EC", "SINGLE-A": "EA", "SINGLE-B": "EB"}[job["condition"]]]
        current = allowed if job["condition"] == "FULL-JOURNAL" else [allowed[-1]]
        if data["evidence"] != [r for r in world["evidence"] if r["id"] in current]:
            raise ValueError("primary evidence availability differs")
        if data["source_ids_authorized_for_authentication"] != allowed:
            raise ValueError("source authorization differs")
        if job["stage"] != "D" and data["questions"] != world["panel"]:
            raise ValueError("successor question leakage")
        events = rows(run / "supervisor/session.jsonl")
        registration = json.loads((study / "registration.json").read_text())
        verify_container(study, job, events, registration, execution_study=execution_study)
        receipts = network_chain(run, result, events, network if network is not None else context_network(study, job),
                                 model, tools_for(job["stage"]), registration["limits"])
        calls = pairs(events)
        db, index, objects = snapshot(run / "state/continuum.sqlite3")
        if any(json.loads(objects[index["source:" + r["id"]]]["content"]) != r for r in world["evidence"]):
            raise ValueError("primary registry differs from assigned world")
        previous_stage = {"B": "A", "C": "B", "D": "C"}.get(job["stage"])
        if job["condition"] in ("C0", "SINGLE-A", "SINGLE-B", "FULL-JOURNAL"):
            previous_stage = None
        parent = index.get("state:" + previous_stage) if previous_stage else None
        if previous_stage:
            source = json.loads((run / "source.json").read_text())
            origin = study / "units" / job["source"] / "state/continuum.sqlite3"
            prior_db, prior_index, prior_objects = snapshot(origin)
            if source["source_id"] != job["source"] or source["history_copied"] or source["db_sha256"] != digest(origin) or prior_index.get("state:" + previous_stage) != parent:
                raise ValueError("predecessor copy identity changed")
            if any(objects.get(sha) != obj for sha, obj in prior_objects.items()):
                raise ValueError("historical object overwritten")
            if job["stage"] == "D" and db != prior_db:
                raise ValueError("read-only successor modified predecessor data")

        def retrieved(sha):
            obj = objects[sha]
            if not any(c["name"] == "continuum_get_object" and c["arguments"]["sha256"] == sha
                       and base64.b64decode(c["value"]["content_base64"]) == obj["content"] for c in calls):
                raise ValueError("object not successfully retrieved through MCP")
            return json.loads(obj["content"])

        counts = {"read_protocol": 0, "read_memory": 0, "verify_evidence": 0, "save_memory": 0}
        accepted = []
        for receipt in receipts:
            name, args, delivered = receipt["name"], receipt["arguments"], receipt["value"]
            if name not in counts:
                raise ValueError("unregistered tool receipt")
            counts[name] += 1
            if name in ("read_protocol", "read_memory"):
                if args != {} or counts[name] > 2:
                    raise ValueError("read quota/schema")
                if name == "read_protocol":
                    want = retrieved(index["protocol"]) if job.get("protocol_version") else None
                    if delivered != {"protocol": want} or (want and want["version"] != job["protocol_version"]):
                        raise ValueError("wrong protocol delivery")
                else:
                    previous = retrieved(parent) if parent else None
                    if delivered != {"snapshot": previous, "sha256": parent}:
                        raise ValueError("wrong predecessor bytes")
                    if previous is not None and len(json.dumps(delivered).encode()) > job["budget"]:
                        raise ValueError("read-result byte ceiling")
            elif name == "verify_evidence":
                if counts[name] > 3 or set(args) != {"record"}:
                    raise ValueError("authentication quota/schema")
                identity = args["record"].get("id")
                enabled = isinstance(identity, str) and identity in allowed and not job.get("verification_disabled")
                actual = retrieved(index["source:" + identity]) if enabled else None
                want = {"reference": identity if isinstance(identity, str) else None, "available": enabled,
                        "valid": json_bytes(actual) == json_bytes(args["record"]) if enabled else None}
                if delivered != want:
                    raise ValueError("authentication result not bound to source")
            else:
                if job["stage"] == "D" or not counts["read_protocol"] or not counts["read_memory"] or counts[name] > 2 or accepted:
                    raise ValueError("checkpoint transition")
                if set(args) != {"content", "encoding"}:
                    raise ValueError("checkpoint schema")
                invalid = not isinstance(args["content"], str) or not args["content"] or args["encoding"] not in ("utf8", "base64")
                if not invalid and args["encoding"] == "base64":
                    try:
                        invalid = not base64.b64decode(args["content"], validate=True)
                    except ValueError:
                        invalid = True
                value = {"content": args["content"], "encoding": args["encoding"], "stage": job["stage"],
                         "author": run.name + ":" + job["stage"], "parent_sha256": parent}
                raw = json_bytes(value)
                sha = hashlib.sha256(raw).hexdigest()
                size = len(json.dumps({"snapshot": value, "sha256": sha}).encode())
                if invalid or size > job["budget"]:
                    want = {"saved": False, "reason": "invalid_encoding_or_empty" if invalid else "byte_ceiling",
                            "bytes": None if invalid else size, "budget": job["budget"], "attempts_left": 2 - counts[name]}
                else:
                    want = {"saved": True, "bytes": size, "sha256": sha}
                    if index.get("state:" + job["stage"]) != sha or objects[sha]["content"] != raw:
                        raise ValueError("model snapshot bytes not persisted")
                    origin = json.loads(objects[sha]["origin"])
                    if origin["actor"] != value["author"] or origin["model_declared"] != model:
                        raise ValueError("snapshot origin not attributed to model")
                    put = next(c for c in calls if c["name"] == "continuum_put_object"
                               and base64.b64decode(c["arguments"]["content_base64"]) == raw and c["value"]["sha256"] == sha)
                    if not any(c["name"] == "continuum_checkpoint_task" and c["start"] > put["end"]
                               and json.loads(c["value"]["result"]).get("state:" + job["stage"]) == sha for c in calls):
                        raise ValueError("model object not durably checkpointed")
                    accepted.append({"sha256": sha, "read_result_bytes": size, "payload_bytes": len(args["content"].encode())})
                if delivered != want:
                    raise ValueError("checkpoint size/acceptance feedback differs")
        if not counts["read_protocol"] or not counts["read_memory"]:
            raise ValueError("assigned state never read")
        if job["stage"] != "D" and not 1 <= counts["save_memory"] <= 2:
            raise ValueError("no checkpoint attempt")
        if bool(accepted) is not result["saved"] or counts["save_memory"] != result["save_attempts"] or counts["verify_evidence"] != result["source_verifications"]:
            raise ValueError("reported state transitions differ")
        if job["stage"] != "D" and not accepted and "state:" + job["stage"] in index:
            raise ValueError("rejected state persisted")
        return {"pass": True, "executed_successfully": True, "tools": counts, "accepted": accepted,
                "mcp_calls": len(calls), "prior_snapshot_sha256": parent,
                "authenticity_results": [r["value"] for r in receipts if r["name"] == "verify_evidence"]}
    except (ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
        return {"pass": False, "executed_successfully": True, "reason": type(exc).__name__ + ": " + str(exc)}
