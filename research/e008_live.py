"""E008 live-series admission, single-use compatibility and durable recovery.

Preparation consumes a reviewed, committed preregistration; it does not invent
one or treat this runner's existence as evidence of scientific readiness.
"""
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

from .common import PROJECT, ROOT, digest, runtime_identity
from .e003 import Jobs, implementation_hashes
from .e008_controller import run_next
from .e008_design import bounds, schedule
from .e008_design import signature
from .e008_execute import ledger_record
from .e008_locks import EvidenceSnapshot, SnapshotDecisions, read, write_once
from .e008_resources import BoundedProvider, SeriesLedger, SeriesStopped, provider_failure_action, resource_policy
from .sandbox import image_id

REGISTRATION = "docs/research/E008-PREREGISTRATION.json"
GATE_CHECKS = {"unit", "isolation", "handoff", "negative_provenance",
               "development_lifecycle", "transport", "reference", "analysis"}
RECOVERY_DELAYS = (30, 120, 300)


def git_bytes(project, *args):
    return subprocess.run(["git", *args], cwd=project, check=True, capture_output=True).stdout


def commit_binding(project, registration, hashes):
    """Observe real Git objects before admission; commit timestamps are not proof."""
    project = Path(project).resolve(strict=True)
    commit = git_bytes(project, "rev-parse", "HEAD").decode().strip()
    for name, expected in {**hashes, REGISTRATION: digest(registration)}.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
            raise PermissionError("unsafe registered repository path")
        committed = git_bytes(project, "show", commit + ":" + name)
        if hashlib.sha256(committed).hexdigest() != expected or digest(project / name) != expected:
            raise PermissionError("preregistration/source bytes are not committed: " + name)
    return {"commit": commit, "registration_path": REGISTRATION,
            "registration_sha256": digest(registration)}


@contextmanager
def controller_lock(study):
    """OS-held local lock: process death releases it; simultaneous resume cannot."""
    path = Path(study) / "controller.lock"
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SeriesStopped("another controller holds this study") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if __import__("os").name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def verified_gold(cache, corpus, hashes):
    cache = Path(cache).resolve(strict=True)
    manifest = read(cache / "manifest.json")
    worlds = {w["id"]: w for w in corpus["worlds"]}
    if manifest.get("complete") is not True or set(manifest["worlds"]) != set(worlds):
        raise PermissionError("complete gold cache for every assigned world required")
    if any(hashes.get(name) != value for name, value in manifest["binding"]["source_hashes"].items()):
        raise PermissionError("gold evaluator source changed")
    gold = {}
    for identity, entry in manifest["worlds"].items():
        if entry["file"] != identity + ".json" or not re.fullmatch(r"[A-Za-z0-9_-]+", identity):
            raise PermissionError("unsafe gold filename")
        if entry["split"] != worlds[identity]["split"] or digest(cache / entry["file"]) != entry["sha256"]:
            raise PermissionError("gold split/content changed")
        gold[identity] = read(cache / entry["file"])
    return manifest, gold


def verify_inputs(reg, corpus_path, gold_cache, gate_path, *, amendment=None, resumption=None):
    current = implementation_hashes()
    expected = amendment["implementation_hashes"] if amendment else reg["implementation_hashes"]
    if resumption:
        expected = resumption["implementation_hashes"]
    if (reg.get("experiment") != "E-008" or reg.get("fixture") is not False
            or reg.get("preregistered") is not True or expected != current
            or reg["runtime"] != runtime_identity()):
        raise PermissionError("frozen live preregistration and unchanged implementation/runtime required")
    corpus = read(corpus_path)
    jobs = schedule(corpus["worlds"], seed=corpus["schedule_seed"])
    if reg["schedule"] != jobs or corpus["schedule"] != jobs or reg["bounds"] != bounds(jobs):
        raise PermissionError("complete registered schedule differs from corpus")
    if len(corpus["worlds"]) != 90 or len(jobs) != 3426:
        raise PermissionError("reduced fixture is not the registered study")
    if reg["oracle_sha256"] != digest(corpus_path):
        raise PermissionError("corpus bytes changed")
    if reg["resources"] != resource_policy(jobs) or reg["recovery_delays"] != list(RECOVERY_DELAYS):
        raise PermissionError("unregistered resource/recovery policy")
    limits = reg["limits"]
    if (set(limits) != {"investigator_seconds", "request_seconds", "output_tokens", "responses_per_context"}
            or limits != {"investigator_seconds": 600, "request_seconds": 120,
                          "output_tokens": 8192, "responses_per_context": 10}):
        raise PermissionError("unregistered context limits")
    if (reg["wire_api"] != "responses" or reg["credential_environment_variable"] != "API_KEY"
            or set(reg["models"]) != {"primary", "secondary"}
            or not all(isinstance(v, str) and v for v in reg["models"].values())
            or reg["models"]["primary"] == reg["models"]["secondary"]):
        raise PermissionError("two distinct frozen model identities required")
    manifest, gold = verified_gold(gold_cache, corpus, current)
    if (reg["gold_manifest_sha256"] != digest(gold_cache / "manifest.json")
            or manifest["binding"]["corpus_sha256"] != digest(corpus_path)):
        raise PermissionError("gold cache belongs to another corpus")
    gate = read(gate_path)
    if (reg["offline_gate_sha256"] != digest(gate_path) or gate.get("pass") is not True
            or gate["implementation_hashes"] != reg["implementation_hashes"] or set(gate["checks"]) != GATE_CHECKS):
        raise PermissionError("complete independently reviewed offline gate required")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("offline evidence changed")
    return corpus, gold


def prepare(identity, corpus_path, gold_cache, gate_path):
    """No API; copy existing identities/bytes only after real commit verification."""
    if not re.fullmatch(r"e008-series-[a-z0-9-]{1,24}", identity):
        raise ValueError("new E008 series identity required")
    registration = PROJECT / REGISTRATION
    reg = read(registration)
    corpus_path, gold_cache, gate_path = map(lambda p: Path(p).resolve(strict=True),
                                            (corpus_path, gold_cache, gate_path))
    corpus, _ = verify_inputs(reg, corpus_path, gold_cache, gate_path)
    committed = commit_binding(PROJECT, registration, reg["implementation_hashes"])
    if image_id(reg["image"]) != reg["image"]:
        raise PermissionError("pinned offline image unavailable")
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    # A partial copy stays visible after an error; prepare never overwrites it.
    for source, target in ((registration, "registration.json"), (corpus_path, "oracle.json"),
                           (gate_path, "offline-gate.json")):
        shutil.copyfile(source, study / target)
    (study / "gold").mkdir()
    for entry in read(gold_cache / "manifest.json")["worlds"].values():
        shutil.copyfile(gold_cache / entry["file"], study / "gold" / entry["file"])
    shutil.copyfile(gold_cache / "manifest.json", study / "gold/manifest.json")
    Jobs(study / "jobs.sqlite3", [ledger_record(j) for j in reg["schedule"]])
    write_once(study / "live-gate.json", {**committed, "prepared_at": time.time(),
                                         "model_API_requests_before_gate": 0})
    write_once(study / "manifest.json", {
        "registration_sha256": digest(study / "registration.json"),
        "gate_sha256": digest(study / "live-gate.json"), "prepared_source_commit": committed["commit"]})
    # Reopen and verify copied bytes, not just their sources.
    verify_inputs(read(study / "registration.json"), study / "oracle.json",
                  study / "gold", study / "offline-gate.json")
    return {"study": str(study.resolve()), "prepared": True, "model_API_requests": 0,
            "worlds": len(corpus["worlds"]), "positions": len(reg["schedule"]), **committed}


def load(study, *, amendment_path=None, resumption_path=None):
    study = Path(study).resolve(strict=True)
    if study.parent != (ROOT / "runs").resolve() or not study.name.startswith("e008-series-"):
        raise PermissionError("study outside registered research directory")
    reg, manifest, gate = map(read, (study / "registration.json", study / "manifest.json",
                                    study / "live-gate.json"))
    if (manifest["registration_sha256"] != digest(study / "registration.json")
            or manifest["gate_sha256"] != digest(study / "live-gate.json")
            or gate["registration_sha256"] != manifest["registration_sha256"]
            or gate["commit"] != manifest["prepared_source_commit"]):
        raise PermissionError("prepared admission record changed")
    amendment = resumption = None
    if resumption_path and not amendment_path:
        raise PermissionError("operational resumption requires explicit immutable model amendment")
    if amendment_path is None:
        commit_binding(PROJECT, study / "registration.json", reg["implementation_hashes"])
    else:
        from .e008_transition import load_amendment
        amendment = load_amendment(study, amendment_path, resumption_path=resumption_path)
        resumption = read(resumption_path) if resumption_path else None
    git_bytes(PROJECT, "merge-base", "--is-ancestor", gate["commit"], "HEAD")
    corpus, gold = verify_inputs(reg, study / "oracle.json", study / "gold", study / "offline-gate.json",
                                amendment=amendment, resumption=resumption)
    if (study / "network-start.json").exists():
        started = read(study / "network-start.json")
        if started["gate_sha256"] != digest(study / "live-gate.json") or started["at"] < gate["prepared_at"]:
            raise PermissionError("network preceded the frozen Git admission gate")
    return reg, corpus, gold


def event_offset(provider):
    return provider.log.stat().st_size if provider.log.exists() else 0


def network_bytes(provider, offset, length):
    if not provider.log.exists():
        if offset or length:
            raise PermissionError("provider trace disappeared")
        return b""
    with provider.log.open("rb") as stream:
        stream.seek(offset)
        raw = stream.read(length)
    if len(raw) != length:
        raise PermissionError("provider trace truncated")
    return raw


def save_network_result(path, provider, offset, result):
    length = event_offset(provider) - offset
    if length < 0:
        raise PermissionError("provider trace shrank during operation")
    proof = {"offset": offset, "length": length,
             "sha256": hashlib.sha256(network_bytes(provider, offset, length)).hexdigest(),
             "result_sha256": signature(result)}
    write_once(path, result)
    write_once(path.with_suffix(".evidence.json"), proof)
    return result


def load_network_result(path, provider):
    evidence = path.with_suffix(".evidence.json")
    if not evidence.exists():
        raise SeriesStopped("network result not sealed; inspect orphan, do not repeat")
    result, proof = read(path), read(evidence)
    if (signature(result) != proof["result_sha256"]
            or hashlib.sha256(network_bytes(provider, proof["offset"], proof["length"])).hexdigest() != proof["sha256"]):
        raise PermissionError("network gate result or original trace changed")
    return result


def last_http_status(provider, offset, worker=None):
    if not provider.log.exists():
        return None
    with provider.log.open("rb") as stream:
        stream.seek(offset)
        status = None
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if row.get("event") == "transport_bytes" and row.get("worker") == worker:
                    status = row["http_status"]
    return status


SMOKE_TOOLS = [{"type": "function", "name": "echo", "description": "Return the supplied integer.",
                "parameters": {"type": "object", "properties": {"value": {"type": "integer"}},
                               "required": ["value"], "additionalProperties": False}}]
SMOKE_HISTORY = [
    {"role": "user", "content": "Call echo with value 13."},
    {"type": "function_call", "name": "echo", "arguments": '{"value":13}', "call_id": "synthetic-smoke-13"},
    {"type": "function_call_output", "call_id": "synthetic-smoke-13", "output": '{"value":13}'},
    {"role": "user", "content": "Now call echo with value 17. Do not give a text answer."},
]


def compatibility(study, role, provider):
    """One metadata query and ONE Responses request per role, never repeated.

    A synthetic prior call tests acceptance of a tool-result input, not model
    memory. This does not claim a two-request round trip or scientific success.
    """
    if role not in ("primary", "secondary"):
        raise ValueError("unknown model role")
    root = Path(study) / "compatibility" / role
    result_path = root / "result.json"
    if result_path.exists():
        value = load_network_result(result_path, provider)
        if value["model"] != provider.model:
            raise PermissionError("compatibility model changed")
        return value
    if root.exists():
        raise SeriesStopped("orphan compatibility probe; do not repeat")
    provider.ledger.check_context()
    write_once(root / "started.json", {"at": time.time(), "model": provider.model})
    result = {"model": provider.model, "role": role, "pass": False, "action": "stop",
              "scientific_sample": False, "response_limit": 1}
    worker = None
    start_offset = offset = event_offset(provider)
    try:
        available = provider.models()
        if provider.model not in available:
            result.update(reason="model_not_in_catalog", action="unavailable" if role == "secondary" else "stop")
        else:
            worker = "smoke-" + role
            offset = event_offset(provider)
            response = provider.respond(worker, SMOKE_HISTORY, SMOKE_TOOLS, timeout=120, max_output_tokens=256)
            calls = [item for item in response["output"] if item.get("type") == "function_call"]
            if (len(calls) != 1 or calls[0].get("name") != "echo"
                    or not isinstance(calls[0].get("call_id"), str) or not calls[0]["call_id"]
                    or json.loads(calls[0]["arguments"]) != {"value": 17}):
                raise ValueError("incompatible function call")
            result.update({"pass": True, "action": "continue", "reason": "single_response_tool_protocol"})
    except Exception as exc:
        status = last_http_status(provider, offset, worker)
        action = provider_failure_action(type(exc).__name__, status)
        # A secondary outage may omit only its preassigned controls. Auth/TLS,
        # malformed responses or safeguards always stop the whole series.
        result.update(failure_type=type(exc).__name__, http_status=status,
                      action="unavailable" if role == "secondary" and action == "recover_next_position" else "stop")
    return save_network_result(result_path, provider, start_offset, result)


def wait_until(deadline, guard):
    while time.time() < deadline:
        remaining = guard.check_context()
        time.sleep(max(0, min(1, deadline - time.time(), remaining)))


def recover(study, identity, provider):
    """Only GET catalog recovery for the NEXT position; no replay of Responses."""
    root = Path(study) / "recovery" / identity
    for number, delay in enumerate(RECOVERY_DELAYS, 1):
        start_path, result_path = root / f"{number}-started.json", root / f"{number}-result.json"
        if result_path.exists():
            result = load_network_result(result_path, provider)
        else:
            if start_path.exists():
                attempt = read(start_path)
                if (root / f"{number}-sending.json").exists():
                    raise SeriesStopped("orphan recovery HTTP; never replay it")
            else:
                attempt = write_once(start_path, {"at": time.time(), "delay": delay, "model": provider.model})
            if attempt["model"] != provider.model or attempt["delay"] != delay:
                raise PermissionError("recovery assignment changed")
            wait_until(attempt["at"] + delay, provider.ledger)
            provider.ledger.check_context()
            offset = event_offset(provider)
            write_once(root / f"{number}-sending.json", {"at": time.time()})
            try:
                available = provider.model in provider.models()
                result = {"available": available, "action": "continue" if available else "recover_next_position"}
            except Exception as exc:
                status = last_http_status(provider, offset)
                result = {"available": False, "failure_type": type(exc).__name__, "http_status": status,
                          "action": provider_failure_action(type(exc).__name__, status)}
            save_network_result(result_path, provider, offset, result)
        if result["available"]:
            return write_once(root / "complete.json", {"pass": True, "attempts": number, "model": provider.model})
        if result["action"] == "stop":
            raise SeriesStopped("non-transient provider failure during recovery")
    raise SeriesStopped("registered recovery exhausted; no extra probes")


def resume_failure(study, job, result, provider, *, resumption=None):
    """A recorded failure stays a failure even if the provider recovers."""
    if result.get("failure_origin") != "provider":
        if result.get("failure_origin") in ("controller", "safeguard"):
            raise SeriesStopped("controller/safeguard failure requires explicit reconciliation")
        return
    status = last_http_status(provider, 0, job["id"])
    if provider_failure_action(result.get("failure_type"), status) != "recover_next_position":
        raise SeriesStopped("non-transient provider failure; no new model context")
    if resumption and resumption.get("amendment_id") == "E008-A007" and status == 502:
        from . import e008_deadline_resumption
        return e008_deadline_resumption.recover_failure(study, job, result, provider, resumption)
    if resumption and resumption.get("amendment_id") == "E008-A006" and status == 502:
        from . import e008_http408_followup
        return e008_http408_followup.recover_failure(study, job, result, provider, resumption)
    if resumption and resumption.get("amendment_id") == "E008-A005" and status == 502:
        from . import e008_direct_resumption
        if int(job["id"][1:]) > e008_direct_resumption.CUTOVER:
            return e008_direct_resumption.recover_failure(study, job, result, provider, resumption)
    if resumption and resumption.get("amendment_id") == "E008-A004" and status == 502:
        from . import e008_minute_resumption
        if int(job["id"][1:]) > e008_minute_resumption.CUTOVER:
            return e008_minute_resumption.recover_failure(study, job, result, provider, resumption)
    recover(study, job["id"], provider)


def run(study, *, authorize_api=False, max_positions=None, amendment_path=None, resumption_path=None):
    """Resume only pending positions; invocation batching never changes the plan."""
    if not authorize_api:
        raise PermissionError("explicit API authorization required")
    if max_positions is not None and (type(max_positions) is not int or max_positions <= 0):
        raise ValueError("positive optional dispatch batch size required")
    study = Path(study).resolve(strict=True)
    if study.parent != (ROOT / "runs").resolve() or not study.name.startswith("e008-series-"):
        raise PermissionError("study outside registered research directory")
    with controller_lock(study):
        reg, corpus, gold = load(study, amendment_path=amendment_path, resumption_path=resumption_path)
        amendment = read(amendment_path) if amendment_path else None
        resumption = read(resumption_path) if resumption_path else None
        jobs = reg["schedule"]
        evidence = EvidenceSnapshot(study, jobs)
        # A terminal invocation is a verification, not a new smoke or API request.
        if evidence.next_job() is None:
            return {"terminal": True, "new_positions": 0, "new_network_requests": 0,
                    "research_complete": False}
        extension = None
        if resumption and resumption.get("amendment_id") == "E008-A007":
            from .e008_deadline_resumption import prepare_admission
            prepare_admission(study, resumption)
            extension = resumption
        guard = SeriesLedger(study, reg["resources"], deadline_extension=extension)
        guard.use_evidence(evidence)
        try:
            guard.start()
            guard.check_context()
            if not (study / "network-start.json").exists():
                with closing(sqlite3.connect(guard.path)) as db:
                    if db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] or db.execute(
                            "SELECT COUNT(*) FROM metadata_attempts").fetchone()[0]:
                        raise SeriesStopped("network attempts exist without their admission record")
                write_once(study / "network-start.json", {"at": time.time(), "gate_sha256": digest(study / "live-gate.json")})
            models = amendment["proposed_models"] if amendment else reg["models"]
            providers = {role: BoundedProvider(reg["provider"], model, guard, study / "provider.jsonl", authorize=True)
                         for role, model in models.items()}
            if amendment:
                from .e008_transition import check_gate, reconciles
                checked = check_gate(study, reg, amendment, guard)
                if checked["action"] == "unavailable":
                    providers["secondary"] = None
            else:
                for role in ("primary", "secondary"):
                    checked = compatibility(study, role, providers[role])
                    if not checked["pass"]:
                        if role == "primary" or checked["action"] != "unavailable":
                            raise SeriesStopped("compatibility gate failed; no repeat")
                        providers[role] = None
            if resumption:
                from .e008_resumption import prepare_admission, recovery_gate
                prepare_admission(study, resumption)
                recovery_gate(study, resumption, providers["primary"])
            store = SnapshotDecisions(study, corpus["worlds"], jobs, evidence)
            # Recovery survives process death; a previous fatal error cannot
            # disappear just because its completed row is now in the snapshot.
            for finished in jobs[:len(evidence.outcomes)]:
                result = evidence.get(finished)["result"]
                if resumption:
                    from .e008_resumption import reconciles as operational_reconciles
                    if operational_reconciles(study, finished, result, resumption):
                        continue
                if amendment and reconciles(study, finished, result, amendment):
                    continue
                provider = providers[finished["model_role"]]
                if amendment and finished["id"] in amendment["preserved_outcome_hashes"]:
                    provider = BoundedProvider(reg["provider"], reg["models"][finished["model_role"]],
                                               guard, study / "provider.jsonl", authorize=True)
                resume_failure(study, finished, result, provider, resumption=resumption)
            count = 0
            while max_positions is None or count < max_positions:
                job = evidence.next_job()
                if job is None:
                    break
                provider = providers[job["model_role"]]
                result = run_next(study, reg, store, gold, provider, guard=guard,
                                  authorize_api=True, evidence=evidence, amendment=amendment, resumption=resumption)
                count += 1
                print(json.dumps({"event": "position_terminal", "job": job["id"], "status": result["status"]}), flush=True)
                resume_failure(study, job, result, provider, resumption=resumption)
            terminal = evidence.next_job() is None
            return {"terminal": terminal, "new_positions": count, "research_complete": False,
                    "next": "independent raw audit/REF/full report" if terminal else "resume first pending position"}
        finally:
            evidence.verify_all()
            if amendment:
                from .e008_amendment import verify_preserved_prefix
                verify_preserved_prefix(study, reg, amendment)
            if resumption:
                from .e008_resumption import verify_preserved
                verify_preserved(study, resumption)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("identity")
    prep.add_argument("--corpus", type=Path, required=True)
    prep.add_argument("--gold-cache", type=Path, required=True)
    prep.add_argument("--offline-gate", type=Path, required=True)
    launch = sub.add_parser("run")
    launch.add_argument("study", type=Path)
    launch.add_argument("--authorize-api", action="store_true")
    launch.add_argument("--max-positions", type=int)
    launch.add_argument("--amendment", type=Path)
    launch.add_argument("--resumption", type=Path)
    args = parser.parse_args()
    result = (prepare(args.identity, args.corpus, args.gold_cache, args.offline_gate) if args.command == "prepare"
              else run(args.study, authorize_api=args.authorize_api, max_positions=args.max_positions,
                       amendment_path=args.amendment, resumption_path=args.resumption))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
