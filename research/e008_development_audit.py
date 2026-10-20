"""Independent API -> tools -> durable protocol provenance, without evaluating superiority."""
import base64
import hashlib
import json

from .common import source_hashes
from .e003_audit import pairs
from .e008_audit import json_bytes, network_chain, rows, snapshot, verify_container
from .e008_development import DEVELOPMENT_TOOLS, development_prompt


def audit(study, job, expected_input, model, network=None, *, execution_study=None):
    run = study / "units" / job["id"]
    result = json.loads((run / "result.json").read_text())
    try:
        if result["status"] not in ("completed", "budget_rejected"):
            return {"pass": False, "executed_successfully": False, "reason": result["status"]}
        if result["job"] != job or result["exit_status"] != 0:
            raise ValueError("development job/exit mismatch")
        worker = run / "workers" / job["stage"]
        if source_hashes(worker) != json.loads((run / "context-manifest.json").read_text()):
            raise ValueError("developer inputs changed")
        if json.loads((worker / "repo/PROMPT.txt").read_text())["prompt"] != development_prompt(job):
            raise ValueError("hidden developer prompt input")
        registration = json.loads((study / "registration.json").read_text())
        events = rows(run / "supervisor/session.jsonl")
        verify_container(study, job, events, registration, execution_study=execution_study)
        receipts = network_chain(run, result, events, network if network is not None else rows(study / "provider.jsonl"),
                                 model, DEVELOPMENT_TOOLS[job["role"]], registration["limits"])
        calls = pairs(events)
        db, index, objects = snapshot(run / "state/continuum.sqlite3")
        input_sha = index["development_input"]
        if json.loads(objects[input_sha]["content"]) != expected_input:
            raise ValueError("development record differs from independently reconstructed permitted inputs")
        reads = [r for r in receipts if r["name"] == "read_development"]
        if len(reads) != 1 or reads[0]["arguments"] != {} or reads[0]["value"] != expected_input:
            raise ValueError("permitted development input not delivered exactly once")
        if not any(c["name"] == "continuum_get_object" and c["arguments"]["sha256"] == input_sha
                   and base64.b64decode(c["value"]["content_base64"]) == objects[input_sha]["content"] for c in calls):
            raise ValueError("development object not retrieved through MCP")
        expected_tool = "publish_protocol" if job["role"] == "designer" else "publish_review"
        slot = ("protocol:" if job["role"] == "designer" else "review:") + f'{job["lineage"]}-v{job["version"]}'
        publications = [r for r in receipts if r["name"] == expected_tool]
        if len(receipts) != len(publications) + 1 or not 1 <= len(publications) <= 2 or receipts[0] != reads[0]:
            raise ValueError("publication order/quota/tool set differs")
        accepted = []
        for attempt, receipt in enumerate(publications, 1):
            args = receipt["arguments"]
            if accepted:
                raise ValueError("publication continued after acceptance")
            if expected_tool == "publish_protocol":
                invalid = set(args) != {"body", "encoding", "reason"}
                if not invalid:
                    try:
                        invalid = (not isinstance(args["body"], str) or args["encoding"] not in ("utf8", "base64")
                                   or not isinstance(args["reason"], str) or not args["reason"].strip()
                                   or len(args["reason"].encode()) > 2048)
                        raw = args["body"].encode() if args["encoding"] == "utf8" else base64.b64decode(args["body"], validate=True)
                        invalid = invalid or not raw or len(raw) > 8192
                    except (ValueError, AttributeError, TypeError):
                        invalid = True
                record = {"version": f'{job["lineage"]}-v{job["version"]}', "author": run.name + ":" + job["stage"],
                          **{k: args.get(k) for k in ("body", "encoding", "reason")}}
                rejection = "invalid_or_oversized_proposal"
            else:
                invalid = (set(args) != {"content"} or not isinstance(args.get("content"), str)
                           or not args["content"] or len(args["content"].encode()) > 8192)
                record = {"version": f'{job["lineage"]}-v{job["version"]}', "author": run.name + ":" + job["stage"],
                          "content": args.get("content")}
                rejection = "invalid_or_oversized_review"
            if invalid:
                wanted = {"saved": False, "reason": rejection, "attempts_left": 2 - attempt}
            else:
                raw = json_bytes(record)
                sha = hashlib.sha256(raw).hexdigest()
                wanted = {"saved": True, "sha256": sha, "record_bytes": len(raw)}
                if index.get(slot) != sha or objects[sha]["content"] != raw:
                    raise ValueError("publication bytes not persisted")
                origin = json.loads(objects[sha]["origin"])
                if origin["actor"] != record["author"] or origin["model_declared"] != model:
                    raise ValueError("wrong publication author")
                put = next(c for c in calls if c["name"] == "continuum_put_object"
                           and base64.b64decode(c["arguments"]["content_base64"]) == raw and c["value"]["sha256"] == sha)
                if not any(c["name"] == "continuum_checkpoint_task" and c["start"] > put["end"]
                           and json.loads(c["value"]["result"]).get(slot) == sha for c in calls):
                    raise ValueError("publication missing durable checkpoint")
                accepted.append({"slot": slot, "sha256": sha, "record_bytes": len(raw)})
            if receipt["value"] != wanted:
                raise ValueError("publication acceptance differs")
        final = result["answer"]
        if (set(final) != {"save_status", "summary"} or not isinstance(final["summary"], str)
                or final["save_status"] != ("saved" if accepted else "not_saved")
                or bool(accepted) is not result["saved"] or len(publications) != result["save_attempts"]):
            raise ValueError("final publication state differs")
        if not accepted and slot in index:
            raise ValueError("rejected publication persisted")
        if set(index) != {"development_input"} | ({slot} if accepted else set()):
            raise ValueError("unexpected development archive slot")
        return {"pass": True, "accepted": accepted, "mcp_calls": len(calls), "authorship_only_not_model_superiority": True}
    except (ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
        return {"pass": False, "executed_successfully": True, "reason": type(exc).__name__ + ": " + str(exc)}
