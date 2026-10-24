"""Locked availability/pilot execution. Credentials are process memory only; never CLI arguments."""
import argparse
import json
import math
from pathlib import Path
import random
import sqlite3
import time

from .common import PROJECT, digest
from .e009_episode import episode_corpus, make_episode
from .e009_execute import run_chain
from .e009_provider import HTTPSProvider, ProviderFailure
from .e009_protocol import PROTOCOL_VERSION
from .e009_raw import write_once
from .e009_revision import sha

DEADLINE_FIELDS = {"attempt_seconds", "request_seconds", "stage_seconds"}


def amendment_limits(previous, deadlines=None):
    deadlines = {} if deadlines is None else deadlines
    if not isinstance(deadlines, dict) or set(deadlines) - DEADLINE_FIELDS:
        raise ValueError("only explicit deadline fields can change")
    limits = {**previous, "tool_calls": 24, **deadlines}
    attempt, request, stage = (limits.get("attempt_seconds", 40), limits["request_seconds"], limits["stage_seconds"])
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
           for value in (attempt, request, stage)):
        raise ValueError("invalid execution deadline")
    # Four attempts plus registered backoff/jitter, unless a longer Retry-After intervenes.
    if request < 4 * attempt + 14.75 or stage < request:
        raise ValueError("deadline hierarchy cannot accommodate bounded retries")
    return limits


def execution_sources():
    paths = list((PROJECT / "research").glob("e009*.py"))
    paths += list((PROJECT / "research/e009_runtime").glob("*.py"))
    paths += list((PROJECT / "continuum").glob("*.py"))
    return {p.relative_to(PROJECT).as_posix(): digest(p) for p in sorted(paths)}


def create_plan(directory, image):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    development = sorted(e["hidden_model"] for e in episode_corpus()["episodes"])
    available = sorted(set(range(576)) - set(development))
    rng = random.Random(2026102411)
    rng.shuffle(available)
    pilot, t2_training, t2_validation = available[:12], available[12:24], available[24:36]
    conditions = ["F0", "F1", "S0", "S1", "FULL-JOURNAL"]
    assignments = []
    for world in pilot:
        order = [(condition, track) for condition in conditions for track in ("controlled", "natural")]
        rng.shuffle(order)
        for condition, track in order:
            assignments.append({"id": f"pilot-{len(assignments) + 1:03}", "world": world,
                                "condition": condition, "track": track})
    plan = {"schema": "e009-pilot-lock-v1", "primary_model_candidate": "gpt-6.1-sol",
            "protocol_version": PROTOCOL_VERSION,
            "base_url": "https://185.170.154.169/v1", "wire_api": "responses",
            "credential_environment_variable": "API_KEY", "source_hashes": execution_sources(), "image": image,
            "seed": 2026102411, "development_worlds": development, "pilot_worlds": pilot,
            "t2_training_worlds": t2_training, "t2_validation_worlds": t2_validation,
            "non_test_reserved": development + available[:84], "heldout_generated": False,
            "main_sample_size": None, "pilot_repeats": 1, "maximum_contexts": 600,
            "assignments": assignments, "limits": {"stage_seconds": 900, "responses": 24,
                                                  "request_seconds": 180, "output_tokens": 16000},
            "concurrency": 1, "replay_failed_assignments": False,
            "calibration_rule": "Retain every assigned outcome; no success-only selection. Inspect ceiling/floor, memory loss, guardrail and latency before final freeze.",
            "t2_protocol": {"lines": ["T2-a", "T2-b"], "shared_training_validation_split": True,
                "isolation": "independent developer contexts, no other line outputs; no gold or heldout",
                "development_after_primary_model_verification": True, "include_both_in_heldout": True,
                "candidate_development_contexts_per_line": 10,
                "candidate_training_validation_episode_budget_per_line": 24,
                "format": "model-developed machine-native serialization, bounded explicit memory; decoder/protocol fixed before heldout",
                "status": "protocol recorded; developers and T2 runtime not yet executed"}}
    write_once(directory / "PLAN.json", plan)
    write_once(directory / "PLAN-SHA256.json", {"sha256": digest(directory / "PLAN.json")})
    return {"directory": str(directory), "plan_sha256": digest(directory / "PLAN.json"),
            "assigned_chains": len(assignments), "maximum_contexts": plan["maximum_contexts"], "model_calls": 0}


def read_locked_plan(directory):
    directory = Path(directory).resolve()
    expected = json.loads((directory / "PLAN-SHA256.json").read_text())["sha256"]
    if digest(directory / "PLAN.json") != expected:
        raise ValueError("pilot plan hash changed")
    plan = json.loads((directory / "PLAN.json").read_text(encoding="utf-8"))
    binding = expected
    plan["_assignment_bindings"] = {a["id"]: binding for a in plan["assignments"]}
    amendments = sorted((directory / "amendments").glob("*.json"))
    for index, path in enumerate(amendments, 1):
        if path.name != f"amendment-{index:03}.json":
            raise ValueError("amendment sequence changed")
        record = json.loads(path.read_text())
        amendment = record["amendment"]
        if (sha(amendment) != record["sha256"] or amendment["parent_binding_sha256"] != binding
                or amendment["parent_plan_sha256"] != expected):
            raise ValueError("amendment hash chain changed")
        execution = amendment["execution"]
        expected_limits = amendment_limits(plan["limits"],
            {key: value for key, value in execution["limits"].items() if key in DEADLINE_FIELDS})
        if (set(execution) != {"source_hashes", "image", "protocol_version", "limits",
                              "transport_directory", "transport_not_before"}
                or execution["image"] != plan["image"]
                or execution["limits"] != expected_limits
                or type(execution["protocol_version"]) is not int
                or execution["protocol_version"] not in {2, 3}
                or execution["protocol_version"] < plan.get("protocol_version", 1)
                or execution["transport_directory"] != f"transport-amendment-{index:03}"
                or type(amendment["start_assignment"]) is not int
                or not 1 <= amendment["start_assignment"] <= len(plan["assignments"])):
            raise ValueError("unregistered pilot amendment fields")
        for name, value in amendment["frozen_receipts"].items():
            if Path(name).name != name or digest(directory / "receipts" / name) != value:
                raise ValueError("pre-amendment outcome changed")
        binding = digest(path)
        for assigned in plan["assignments"][amendment["start_assignment"] - 1:]:
            plan["_assignment_bindings"][assigned["id"]] = binding
        plan.update(execution)
    plan["_execution_binding_sha256"] = binding
    return directory, plan, expected


def load_plan(directory):
    directory, plan, expected = read_locked_plan(directory)
    if execution_sources() != plan["source_hashes"]:
        raise ValueError("pilot execution source binding changed; do not silently refreeze")
    return directory, plan, expected


def amend_plan(directory, reason, *, deadlines=None):
    """Explicit append-only execution amendment; assignments and prior outcomes never change."""
    directory, plan, plan_hash = read_locked_plan(directory)
    if not reason.strip():
        raise ValueError("amendment reason required")
    assigned = next_assignment(directory, plan)
    if assigned is None:
        raise ValueError("no unfinished pilot assignment")
    start = plan["assignments"].index(assigned) + 1
    receipts = {p.name: digest(p) for p in (directory / "receipts").glob("*.json")}
    if set(receipts) != {a["id"] + ".json" for a in plan["assignments"][:start - 1]}:
        raise ValueError("non-prefix outcomes cannot be amended")
    not_before = plan.get("transport_not_before", 0)
    ledger = directory / plan.get("transport_directory", "transport") / "attempts.sqlite3"
    if ledger.exists():
        with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
            if db.execute("SELECT 1 FROM requests WHERE status='pending'").fetchone():
                raise ValueError("pending transport prevents amendment")
            not_before = max([not_before] + [json.loads(row[0]).get("retry_at", 0)
                                           for row in db.execute("SELECT record FROM attempts")])
    number = len(list((directory / "amendments").glob("*.json"))) + 1
    execution = {"source_hashes": execution_sources(), "image": plan["image"],
                 "protocol_version": PROTOCOL_VERSION, "limits": amendment_limits(plan["limits"], deadlines),
                 "transport_directory": f"transport-amendment-{number:03}", "transport_not_before": not_before}
    amendment = {"schema": "e009-pilot-amendment-v1", "parent_plan_sha256": plan_hash,
                 "parent_binding_sha256": plan["_execution_binding_sha256"], "reason": reason,
                 "start_assignment": start, "frozen_receipts": receipts, "execution": execution,
                 "created": time.time(), "assigned_outcomes_replayed": False}
    path = directory / "amendments" / f"amendment-{number:03}.json"
    write_once(path, {"amendment": amendment, "sha256": sha(amendment)})
    load_plan(directory)
    return {"path": str(path), "sha256": digest(path), "next_assignment": assigned["id"],
            "prior_outcomes_preserved": len(receipts), "model_calls": 0}


def verify_model(directory, *, authorize=False, retry_failed=False):
    directory, plan, plan_hash = load_plan(directory)
    output = directory / "availability"
    previous = sorted(output.glob("attempt-*/RESULT.json")) if output.exists() else []
    attempts = sorted(output.glob("attempt-*")) if output.exists() else []
    if len(previous) != len(attempts):
        raise ValueError("orphan availability attempt; inspect before any retry")
    if previous:
        last = json.loads(previous[-1].read_text())
        if last["status"] == "completed":
            # Repair only the final pointer after a crash, never submit the successful request again.
            pointer = {"result": str(previous[-1]), "sha256": digest(previous[-1]), "plan_sha256": plan_hash}
            verified = output / "VERIFIED.json"
            if verified.exists():
                if json.loads(verified.read_text()) != pointer:
                    raise ValueError("availability pointer changed")
            else:
                write_once(verified, pointer)
            return last
        if not retry_failed:
            return last
        if time.time() - last["finished"] < 60:
            raise ValueError("wait at least 60 seconds before a new failed-availability round")
    provider = HTTPSProvider(plan["base_url"], plan["primary_model_candidate"], output / "transport", authorize=authorize)
    context = "availability:" + plan_hash + ":" + str(len(previous) + 1)
    attempt_dir = output / f"attempt-{len(previous) + 1:03}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    request = {"model": plan["primary_model_candidate"], "store": False, "max_output_tokens": 4096,
               "input": [{"role": "user", "content": "Reply with READY. This request checks API availability only."}]}
    write_once(attempt_dir / "request.json", request)
    status, reason = "failed", None
    try:
        response = provider.respond(context, request, timeout=180)
        write_once(attempt_dir / "response.json", response)
        status = "completed"
    except ProviderFailure as error:
        reason = error.reason
    result = {"status": status, "reason": reason, "plan_sha256": plan_hash,
              "assigned_model": plan["primary_model_candidate"], "attempts": provider.ledger.records(context),
              "accounting": provider.accounting(context), "finished": time.time(),
              "scope": "gateway-reported model availability, not independent weight identity or research success"}
    write_once(attempt_dir / "RESULT.json", result)
    if status == "completed":
        write_once(output / "VERIFIED.json", {"result": str(attempt_dir / "RESULT.json"),
                    "sha256": digest(attempt_dir / "RESULT.json"), "plan_sha256": plan_hash})
    return result


def next_assignment(directory, plan):
    completed = []
    for assignment in plan["assignments"]:
        target = directory / "runs" / assignment["id"]
        receipt = directory / "receipts" / (assignment["id"] + ".json")
        if receipt.exists():
            record = json.loads(receipt.read_text())
            if (not target.exists() or digest(target / "MANIFEST.json") != record["manifest_sha256"]
                    or sha(record["assignment"]) != sha(assignment)
                    or Path(record["directory"]).resolve() != target.resolve()
                    or record["plan_sha256"] != digest(directory / "PLAN.json")
                    or record.get("execution_binding_sha256", record["plan_sha256"]) !=
                    plan["_assignment_bindings"][assignment["id"]]):
                raise ValueError("assigned outcome binding broken")
            completed.append(record)
            continue
        if target.exists():
            raise ValueError("orphan assignment exists; independently recover, never silently repeat")
        if len(completed) >= 3 and all("completed" not in r["statuses"] for r in completed[-3:]):
            raise ValueError("three assignments without a completed stage; diagnose provider/protocol before more calls")
        return assignment
    return None


def pilot_next(directory, *, authorize=False):
    directory, plan, plan_hash = load_plan(directory)
    if (directory / "STOP").exists():
        raise ValueError("operator stop before new assignment")
    pointer = json.loads((directory / "availability/VERIFIED.json").read_text())
    result_path = Path(pointer["result"]).resolve()
    if not result_path.is_relative_to(directory / "availability") or digest(result_path) != pointer["sha256"]:
        raise ValueError("availability outcome binding broken")
    available = json.loads(result_path.read_text())
    if available["status"] != "completed" or available["plan_sha256"] != plan_hash:
        raise ValueError("assigned model availability not confirmed")
    assignment = next_assignment(directory, plan)
    if assignment is None:
        return {"status": "pilot_assignments_complete", "research_complete": False}
    if time.time() < plan.get("transport_not_before", 0):
        raise ValueError("pre-amendment provider cooldown still active")
    provider = HTTPSProvider(plan["base_url"], plan["primary_model_candidate"],
                             directory / plan.get("transport_directory", "transport"),
                             authorize=authorize, stop_path=directory / "STOP",
                             protocol_version=plan.get("protocol_version", 1),
                             attempt_seconds=plan["limits"].get("attempt_seconds", 40))
    episode = make_episode(assignment["world"], "e009-pilot-world-" + str(assignment["world"]))
    result = run_chain(directory / "runs" / assignment["id"], episode, assignment["condition"], assignment["track"],
                       provider, plan["image"], limits=plan["limits"], protocol_version=plan.get("protocol_version", 1))
    write_once(directory / "receipts" / (assignment["id"] + ".json"), {
        **result, "assignment": assignment, "plan_sha256": plan_hash,
        "execution_binding_sha256": plan["_execution_binding_sha256"]})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["plan", "amend", "verify-model", "pilot-next"])
    parser.add_argument("--directory", required=True)
    parser.add_argument("--image")
    parser.add_argument("--reason")
    parser.add_argument("--attempt-seconds", type=float)
    parser.add_argument("--request-seconds", type=float)
    parser.add_argument("--stage-seconds", type=float)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--retry-failed-availability", action="store_true")
    args = parser.parse_args()
    if args.mode == "plan":
        if not args.image: parser.error("--image required for plan")
        result = create_plan(args.directory, args.image)
    elif args.mode == "amend":
        if not args.reason: parser.error("--reason required for amendment")
        deadlines = {key: getattr(args, key) for key in DEADLINE_FIELDS if getattr(args, key) is not None}
        result = amend_plan(args.directory, args.reason, deadlines=deadlines)
    elif args.mode == "verify-model": result = verify_model(args.directory, authorize=args.authorize,
                                                          retry_failed=args.retry_failed_availability)
    else: result = pilot_next(args.directory, authorize=args.authorize)
    print(json.dumps(result), flush=True)
