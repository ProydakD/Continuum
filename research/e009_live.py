"""Locked availability/pilot execution. Credentials are process memory only; never CLI arguments."""
import argparse
import json
from pathlib import Path
import random
import time

from .common import PROJECT, digest
from .e009_episode import episode_corpus, make_episode
from .e009_execute import run_chain
from .e009_provider import HTTPSProvider, ProviderFailure
from .e009_raw import write_once
from .e009_revision import sha


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


def load_plan(directory):
    directory = Path(directory).resolve()
    expected = json.loads((directory / "PLAN-SHA256.json").read_text())["sha256"]
    if digest(directory / "PLAN.json") != expected:
        raise ValueError("pilot plan hash changed")
    plan = json.loads((directory / "PLAN.json").read_text(encoding="utf-8"))
    if execution_sources() != plan["source_hashes"]:
        raise ValueError("pilot execution source binding changed; do not silently refreeze")
    return directory, plan, expected


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
                    or record["plan_sha256"] != digest(directory / "PLAN.json")):
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
    provider = HTTPSProvider(plan["base_url"], plan["primary_model_candidate"], directory / "transport",
                             authorize=authorize, stop_path=directory / "STOP")
    episode = make_episode(assignment["world"], "e009-pilot-world-" + str(assignment["world"]))
    result = run_chain(directory / "runs" / assignment["id"], episode, assignment["condition"], assignment["track"],
                       provider, plan["image"], limits=plan["limits"])
    write_once(directory / "receipts" / (assignment["id"] + ".json"), {**result, "assignment": assignment, "plan_sha256": plan_hash})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["plan", "verify-model", "pilot-next"])
    parser.add_argument("--directory", required=True)
    parser.add_argument("--image")
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--retry-failed-availability", action="store_true")
    args = parser.parse_args()
    if args.mode == "plan":
        if not args.image: parser.error("--image required for plan")
        result = create_plan(args.directory, args.image)
    elif args.mode == "verify-model": result = verify_model(args.directory, authorize=args.authorize,
                                                          retry_failed=args.retry_failed_availability)
    else: result = pilot_next(args.directory, authorize=args.authorize)
    print(json.dumps(result), flush=True)
