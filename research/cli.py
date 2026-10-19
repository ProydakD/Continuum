import argparse
import json
from pathlib import Path
from .profiles import prepare, CONDITIONS
from .preflight import preflight
from .supervisor import run_worker
from .evaluator import evaluate


def main():
    parser = argparse.ArgumentParser(description="Continuum Research: offline infrastructure first")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("prepare")
    create.add_argument("--run-id", required=True)
    create.add_argument("--image", default="python:3.11-slim-bookworm")
    create.add_argument("--condition", choices=CONDITIONS, default="none")
    create.add_argument("--control", choices=["handoff", "empty", "injection"], default="handoff")
    create.add_argument("--model", default="")
    for name in ["preflight", "run", "evaluate"]:
        child = sub.add_parser(name)
        child.add_argument("--run", required=True, type=Path)
        if name == "run":
            child.add_argument("--stage", choices=list("ABC"), required=True)
            child.add_argument("--mode", choices=["fixture", "codex"], default="fixture")
            child.add_argument("--authorize-model-run", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        value = {"run": str(prepare(args.run_id, args.image, args.condition, args.control, args.model))}
    elif args.action == "preflight":
        value = preflight(args.run)
    elif args.action == "run":
        value = run_worker(args.run, args.stage, args.mode, args.authorize_model_run)
    else:
        value = evaluate(args.run)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    if value.get("status") == "failed" or value.get("pass") is False or value.get("infrastructure_pass") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
