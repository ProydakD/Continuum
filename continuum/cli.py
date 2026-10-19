"""Human-facing debug console; not needed by model clients."""
import argparse
import json
import sys
from .store import Store, ConflictError


def out(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuum debug console")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create DB tables")
    sub.add_parser("bootstrap", help="load workspace state")
    demo = sub.add_parser("demo", help="simulate two separate processes sharing one store")
    demo.add_argument("--workspace", default="lab")
    events = sub.add_parser("events")
    events.add_argument("--after", type=int, default=0)
    tasks = sub.add_parser("tasks")
    tasks.add_argument("--status", default="")
    args = parser.parse_args()
    store = Store()
    if args.cmd == "init":
        out({"db": str(store.path), "initialized": True})
    elif args.cmd == "bootstrap":
        out(store.bootstrap())
    elif args.cmd == "events":
        out(store.changes(after_seq=args.after))
    elif args.cmd == "tasks":
        out(store.list_tasks(status=args.status))
    elif args.cmd == "demo":
        a = Store(store.path, actor="simulation:A")
        b = Store(store.path, actor="simulation:B")
        item = a.create_task("Explore common memory", "Demonstrate survival across instances",
                             "A second instance must claim and advance this task", args.workspace)
        a_claim = a.add_claim({"subject": item["id"], "predicate": "requires", "object": "durable-state"}, args.workspace)
        claimed = b.claim_task(item["id"], args.workspace, expected_revision=item["revision"])
        finished = b.checkpoint_task(item["id"], "Verify this from an actual fresh Codex session",
                                     "B discovered A's task and added a checkpoint",
                                     args.workspace, expected_revision=claimed["revision"])
        out({"task_id": item["id"], "claim_id": a_claim["id"], "other_actor": b.actor,
             "handoff_revision": finished["revision"], "bootstrap_new_instance": Store(store.path).bootstrap(args.workspace)})


if __name__ == "__main__":
    try:
        main()
    except (ConflictError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
