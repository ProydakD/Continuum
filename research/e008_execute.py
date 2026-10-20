"""Fresh isolated E008 investigators using the existing Worker/Supervisor boundary."""
import json
import queue
import subprocess
import threading
import time

from .common import PROJECT, command, digest, source_hashes, write_json
from .e003 import copy_database
from .e008_memory import InvestigatorBridge, KnowledgeArchive
from .e008_protocol import prompt, tools_for
from .profiles import create_worker
from .sandbox import container_command
from .supervisor import read_lines


def make_unit(path):
    for name in ("state", "supervisor", "workers"):
        (path / name).mkdir(parents=True, exist_ok=True)


def seed_archive(run, evidence, protocol=None):
    """Trusted primary tables; only narrow authenticity checks can inspect these."""
    make_unit(run)
    with (run / "supervisor/seed.jsonl").open("x", encoding="utf-8") as log:
        archive = KnowledgeArchive(run, "host", [], log, "registered-evidence-controller")
        try:
            for record in evidence:
                archive.put("source:" + record["id"], record)
            if protocol is not None:
                archive.put("protocol", protocol)
        finally:
            archive.close()


def copy_predecessor(run, source, source_id):
    make_unit(run)
    origin = source / "state/continuum.sqlite3"
    before = digest(origin)
    copy_database(origin, run / "state/continuum.sqlite3")
    if digest(origin) != before:
        raise PermissionError("immutable predecessor changed while copying")
    write_json(run / "source.json", {"source_id": source_id, "source": str(source),
        "db_sha256": before, "copy_sha256": digest(run / "state/continuum.sqlite3"), "history_copied": False})


def execute(study, registration, job, world, provider):
    run = study / "units" / job["id"]
    stage = job["stage"]
    worker = run / "workers" / stage
    if worker.exists():
        raise RuntimeError("worker context already exists; do not relaunch")
    # The legacy profile scaffold has A/B/C templates. It supplies isolation only;
    # its temporary template is replaced before hashing/launching fresh stage D.
    create_worker(worker, "C" if stage == "D" else stage, "none")
    write_json(worker / "repo/PROMPT.txt", {"prompt": prompt(job, world)})
    before = source_hashes(worker)
    write_json(run / "context-manifest.json", before)
    name = "continuum-" + study.name + "-" + job["id"]
    argv = container_command(registration["image"], name, worker, ["/runtime/e002_worker.py"])
    limits = registration["limits"]
    deadline = limits["investigator_seconds"]
    started = time.monotonic()
    process = bridge = timer = None
    report = {"status": "failed", "exit_status": None, "job": job, "fixture": registration["fixture"]}
    with (run / "supervisor/session.jsonl").open("x", encoding="utf-8") as log, (run / "supervisor/session.stderr.txt").open("x", encoding="utf-8") as err:
        try:
            bridge = InvestigatorBridge(run, stage, [], log, provider.model)
            bridge.configure(job)
            bridge.emit({"event": "command_execution", "command": argv, "at": time.time()})
            process = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=err, text=True, encoding="utf-8")
            timer = threading.Timer(deadline, lambda: command(["docker", "rm", "-f", name], timeout=15))
            timer.daemon = True
            timer.start()
            inbox = queue.Queue(maxsize=128)
            threading.Thread(target=read_lines, args=(process.stdout, inbox, "worker"), daemon=True).start()
            final, requests, crashed = None, 0, False
            while True:
                remaining = deadline - (time.monotonic() - started)
                if remaining <= 0 or (study / "STOP").exists():
                    raise TimeoutError("investigator deadline or operator STOP")
                _, line = inbox.get(timeout=remaining)
                if line is None:
                    break
                if len(line) > 262144:
                    raise ValueError("oversized worker message")
                event = json.loads(line)
                bridge.emit({"event": "worker_message", "message": event})
                if event["channel"] == "responses":
                    requests += 1
                    if requests > limits["responses_per_context"]:
                        raise ValueError("registered response ceiling")
                    try:
                        response = provider.respond(job["id"], event["history"], tools_for(stage),
                            timeout=min(remaining, limits["request_seconds"]), max_output_tokens=limits["output_tokens"])
                    except Exception:
                        report["failure_origin"] = "provider"
                        raise
                elif event["channel"] == "tool":
                    response = bridge.call(event["name"], event["arguments"])
                    bridge.emit({"event": "tool_result", "name": event["name"], "arguments": event["arguments"], "value": response})
                    if job.get("crash_after_commit") and bridge.saved:
                        killed = command(["docker", "kill", name], timeout=15)
                        bridge.emit({"event": "injected_crash_after_commit", "kill_result": killed, "at": time.time(), "receipt_delivered": False})
                        crashed = True
                        break
                elif event["channel"] == "worker":
                    if final is not None:
                        raise ValueError("multiple investigator finals")
                    final = json.loads(event["line"])
                    continue
                else:
                    raise PermissionError("unregistered worker channel")
                process.stdin.write(json.dumps({"result": response}) + "\n")
                process.stdin.flush()
            report["exit_status"] = process.wait(timeout=15)
            if crashed:
                if process.returncode != 137 or not bridge.saved:
                    raise ValueError("crash-after-durable-commit not observed")
                report["status"] = "injected_crash_after_commit"
            else:
                if process.returncode != 0 or final is None:
                    raise ValueError("investigator did not return a successful final")
                bridge.finish(final)
                report.update(status="budget_rejected" if stage != "D" and not bridge.saved else "completed", answer=final)
        except Exception as exc:
            report.update(failure_type=type(exc).__name__, failure=str(exc))
        finally:
            if timer:
                timer.cancel()
            if process:
                if process.poll() is None:
                    command(["docker", "rm", "-f", name], timeout=15)
                    process.wait(timeout=15)
                report["exit_status"] = process.returncode
                process.stdin.close()
                process.stdout.close()
            if bridge:
                report.update(saved=bridge.saved, save_attempts=bridge.attempts, source_verifications=bridge.verifications,
                              reads=bridge.read_counts)
                bridge.close()
    if source_hashes(worker) != before:
        report.update(status="failed", failure_origin="safeguard", failure_type="PermissionError", failure="worker inputs changed")
    report["seconds"] = time.monotonic() - started
    write_json(run / "result.json", report)
    return report
