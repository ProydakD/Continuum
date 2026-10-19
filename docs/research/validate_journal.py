"""Validate journal structure and lineage; never evaluate scientific truth."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re


FIELDS = {"event_id", "entity_id", "kind", "at_utc", "status", "evidence_tier",
          "summary", "details", "refs", "provenance", "supersedes"}
KINDS = {
    "hypothesis": ("H", {"competitor", "prediction", "falsifier"}),
    "experiment": ("E", {"design", "inputs", "evaluation", "conditions", "outcome", "limitations"}),
    "decision": ("D", {"reason", "alternatives", "revisit_when"}),
    "question": ("Q", {"unknown", "next_test"}),
}
TIERS = {"proposal", "historical_engineering", "observed_engineering", "observed_model", "replicated_model"}


def validate(records):
    seen, entities = {}, {}
    if not records:
        raise ValueError("empty journal")
    for row in records:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("journal fields differ from contract")
        if row["kind"] not in KINDS or row["evidence_tier"] not in TIERS:
            raise ValueError("unknown kind or evidence tier")
        prefix, required = KINDS[row["kind"]]
        entity, event = row["entity_id"], row["event_id"]
        if not isinstance(entity, str) or not re.fullmatch(prefix + r"-\d{3}", entity):
            raise ValueError("invalid entity ID")
        if not isinstance(event, str) or event in seen or not event.startswith(entity + "/"):
            raise ValueError("invalid or duplicate event ID")
        for field in ("at_utc", "status", "summary"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError("missing " + field)
        if not row["at_utc"].endswith("Z"):
            raise ValueError("UTC timestamp required")
        datetime.fromisoformat(row["at_utc"].replace("Z", "+00:00"))
        if not isinstance(row["details"], dict) or not required <= row["details"].keys():
            raise ValueError("missing kind-specific details")
        if not isinstance(row["refs"], list) or not all(isinstance(r, str) and r for r in row["refs"]):
            raise ValueError("refs must be nonempty strings")
        if not isinstance(row["provenance"], dict) or not {"actor", "model_actual", "source_snapshot"} <= row["provenance"].keys():
            raise ValueError("missing provenance")
        previous = row["supersedes"]
        if entity in entities:
            if previous != entities[entity]:
                raise ValueError("revision must supersede previous event of same entity")
        elif previous is not None:
            raise ValueError("first event cannot supersede another entity")
        seen[event] = row
        entities[entity] = event
    for row in records:
        refs = list(row["refs"])
        if row["kind"] == "hypothesis":
            refs.append(row["details"]["competitor"])
        for ref in refs:
            if isinstance(ref, str) and re.fullmatch(r"[HEDQ]-\d{3}", ref) and ref not in entities:
                raise ValueError("dangling entity reference: " + ref)
    return {"events": len(records), "entities": len(entities), "truth_verified": False}


def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path(__file__).with_name("journal.jsonl"))
    args = parser.parse_args()
    print(json.dumps(validate(read(args.path)), sort_keys=True))
