"""Bounded process supervisor. Stored next_step/result are never command sources."""
from contextlib import closing
import json
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from continuum.store import Store, ConflictError
from .common import MAX_LINE, PROJECT, command, server_env, source_hashes, write_json
from .profiles import load_manifest
from .sandbox import container_command


class Budget:
    def __init__(self, path, limits):
        self.path, self.limits = path, limits
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS launches(stage TEXT PRIMARY KEY, status TEXT, started REAL, finished REAL)")
            conn.commit()

    def reserve(self, stage):
        with closing(sqlite3.connect(self.path, timeout=5)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM launches WHERE stage=?", (stage,)).fetchone():
                raise RuntimeError("stage already attempted; no automatic retries")
            rows = conn.execute("SELECT status,started FROM launches").fetchall()
            if len(rows) >= self.limits["max_launches"]:
                raise RuntimeError("launch budget exhausted")
            if sum(r[0] == "running" for r in rows) >= self.limits["max_concurrency"]:
                raise RuntimeError("concurrency occupied; inspect orphaned run, never auto-takeover")
            if rows and time.time() - min(r[1] for r in rows) >= self.limits["total_seconds"]:
                raise RuntimeError("total wall-time budget exhausted")
            conn.execute("INSERT INTO launches VALUES(?,?,?,NULL)", (stage, "running", time.time()))
            conn.commit()

    def finish(self, stage, status):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE launches SET status=?,finished=? WHERE stage=?", (status, time.time(), stage))
            conn.commit()

    def remaining(self):
        with closing(sqlite3.connect(self.path)) as conn:
            start = conn.execute("SELECT MIN(started) FROM launches").fetchone()[0]
            return self.limits["total_seconds"] - (time.time() - start)


def read_lines(pipe, inbox, channel):
    try:
        while line := pipe.readline(MAX_LINE + 1):
            inbox.put((channel, line))
            if len(line) > MAX_LINE:
                break
    finally:
        inbox.put((channel, None))


def run_worker(run, stage, mode="fixture", authorize=False):
    run = Path(run).resolve()
    manifest = load_manifest(run)
    if stage not in "ABC" or len(stage) != 1 or mode not in {"fixture", "codex"}:
        raise ValueError("unregistered action")
    if mode != manifest["execution_mode"]:
        raise ValueError("cannot mix fixture and model conditions in one run")
    if mode == "codex" and (not authorize or not manifest["model_declared"]):
        raise PermissionError("explicit model-run authorization and local model identity required")
    preflight = json.loads((run / "supervisor" / "preflight.json").read_text())
    if not preflight["infrastructure_pass"] or preflight["code_hashes"] != manifest["code_hashes"]:
        raise RuntimeError("fresh matching preflight required")
    if mode == "codex" and not preflight.get("model_runtime_ready"):
        raise RuntimeError("model runtime absent; fixture PASS cannot authorize model launch")
    if manifest["limits"]["max_cost_usd"] != 0:
        raise PermissionError("only offline zero-external-cost runs supported")
    if manifest["control"] != "handoff" and stage != "B":
        raise ValueError("negative controls run only stage B")
    if manifest["control"] == "handoff" and stage in "BC":
        previous = run / "supervisor" / f"{chr(ord(stage)-1)}-result.json"
        if not previous.exists() or json.loads(previous.read_text())["status"] != "completed":
            raise RuntimeError("previous stage has not completed; do not invent continuation")
    worker = run / "workers" / stage
    if source_hashes(worker) != manifest["instances"][stage]["initial_hashes"]:
        raise RuntimeError("worker initial context changed or already used")
    budget = Budget(run / "supervisor" / "budget.sqlite3", manifest["limits"])
    budget.reserve(stage)
    name = f"continuum-{run.name}-{stage.lower()}"
    actor = manifest["instances"][stage]["actor"]
    argv = container_command(manifest["image"], name, worker,
                             ["/runtime/entry.py", "--mode", mode, "--stage", stage,
                              "--model", manifest["model_declared"]], live=mode == "codex")
    event_path = run / "supervisor" / f"{stage}.jsonl"
    stderr_path = run / "supervisor" / f"{stage}.stderr.txt"
    brokers, broker_logs = {}, []
    inbox = queue.Queue(maxsize=128)
    process = None
    container_created = False
    start = time.monotonic()
    status, exit_code, failure = "failed", None, None
    count, size, tokens = 0, 0, 0
    lease_store = Store(run / "state" / "continuum.sqlite3", actor=actor, scope="lab",
                        origin={"run_id": run.name, "role": "supervisor_lease_keeper"})
    next_renew = time.monotonic() + 5
    try:
        with event_path.open("w", encoding="utf-8") as events, stderr_path.open("w", encoding="utf-8") as stderr:
            create_argv = ["docker", "create", *argv[2:]]
            events.write(json.dumps({"event": "command_execution", "command": create_argv, "mode": mode,
                                     "actor": actor, "at": time.time()}) + "\n")
            events.flush()
            creation = command(create_argv, timeout=30)
            events.write(json.dumps({"event": "command_result", **creation}) + "\n")
            if creation["exit_status"]:
                exit_code = creation["exit_status"]
                raise RuntimeError("container creation failed: " + creation["stderr"])
            container_created = True
            attach_argv = ["docker", "start", "--attach", "--interactive", name]
            events.write(json.dumps({"event": "command_execution", "command": attach_argv, "at": time.time()}) + "\n")
            events.flush()
            process = subprocess.Popen(attach_argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            threading.Thread(target=read_lines, args=(process.stdout, inbox, "container"), daemon=True).start()
            threading.Thread(target=read_lines, args=(process.stderr, inbox, "stderr"), daemon=True).start()
            ended = set()
            while True:
                if time.monotonic() - start > manifest["limits"]["worker_seconds"] or budget.remaining() <= 0:
                    raise TimeoutError("wall-time budget exhausted")
                if (run / "STOP").exists():
                    raise RuntimeError("operator kill switch")
                if time.monotonic() >= next_renew:
                    for task in lease_store.list_tasks(status="active", limit=100):
                        if task["lease_owner"] == actor and task["lease_until"] - time.time() < 300:
                            try:
                                lease_store.renew_lease(task["id"], task["revision"], 600)
                            except ConflictError:
                                pass  # Next heartbeat re-reads; never overwrite a revision or expired lease.
                    next_renew = time.monotonic() + 5
                try:
                    channel, line = inbox.get(timeout=0.1)
                except queue.Empty:
                    if process.poll() is not None and {"container", "stderr"} <= ended:
                        break
                    continue
                if line is None:
                    if channel.startswith("broker:") and process.poll() is None:
                        raise RuntimeError("MCP broker disconnected; inspect isolated broker stderr")
                    ended.add(channel)
                    continue
                size += len(line.encode("utf-8"))
                if len(line) > MAX_LINE or size > manifest["limits"]["max_output_bytes"]:
                    raise RuntimeError("output budget exhausted")
                if channel == "stderr":
                    stderr.write(line)
                    continue
                if channel.startswith("broker:"):
                    connection = channel.split(":", 1)[1]
                    response = {"connection": connection, "message": json.loads(line)}
                    process.stdin.write(json.dumps(response) + "\n")
                    process.stdin.flush()
                    events.write(json.dumps({"event": "mcp_response", **response}) + "\n")
                    continue
                message = json.loads(line)
                events.write(json.dumps(message) + "\n")
                events.flush()
                if message.get("channel") == "mcp":
                    count += 1
                    if count > manifest["limits"]["max_messages"]:
                        raise RuntimeError("MCP message budget exhausted")
                    connection = message["connection"]
                    if not isinstance(connection, str) or len(connection) != 32 or not all(c in "0123456789abcdef" for c in connection):
                        raise ValueError("invalid bridge connection")
                    if connection not in brokers:
                        if len(brokers) >= 4:
                            raise RuntimeError("MCP connection budget exhausted")
                        log = (run / "supervisor" / f"{stage}-broker-{len(brokers)}.stderr.txt").open("w", encoding="utf-8")
                        broker_logs.append(log)
                        broker = subprocess.Popen([sys.executable, "-m", "continuum.mcp_server"], cwd=PROJECT,
                            env=server_env(run / "state" / "continuum.sqlite3", actor, run.name,
                                           manifest["model_declared"] if mode == "codex" else "deterministic-fixture"),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8")
                        brokers[connection] = broker
                        threading.Thread(target=read_lines, args=(broker.stdout, inbox, "broker:" + connection), daemon=True).start()
                    brokers[connection].stdin.write(json.dumps(message["message"]) + "\n")
                    brokers[connection].stdin.flush()
                elif message.get("channel") == "worker":
                    if mode == "codex":
                        event = json.loads(message["line"])
                        if event.get("type") == "turn.completed":
                            usage = event.get("usage", {})
                            tokens += sum(usage.get(k, 0) for k in ("input_tokens", "output_tokens"))
                            if tokens > manifest["limits"]["max_tokens"]:
                                raise RuntimeError("observed token budget exceeded")
                else:
                    raise ValueError("unregistered bridge channel")
            exit_code = process.wait(timeout=5)
            status = "completed" if exit_code == 0 else "failed"
    except BaseException as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        if process is not None and process.poll() is None:
            command(["docker", "rm", "-f", name], timeout=20)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None:
            exit_code = process.returncode
        if container_created:
            command(["docker", "rm", "-f", name], timeout=20)
        for broker in brokers.values():
            broker.terminate()
            broker.wait(timeout=10)
        for log in broker_logs:
            log.close()
        budget.finish(stage, status)
        report = {"status": status, "exit_status": exit_code, "failure": failure,
                  "duration_seconds": time.monotonic() - start, "mode": mode,
                  "observed_tokens": tokens, "external_cost_usd": 0, "actor": actor,
                  "model_actual": "unverified" if mode == "codex" else "none; deterministic fixture"}
        write_json(run / "supervisor" / f"{stage}-result.json", report)
    return report
