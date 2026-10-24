"""Write-once raw episode fixture and read-only replay bound to an external digest."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .e009_episode_eval import score_chain, score_natural_chain
from .e009_revision import canonical, sha
from .e009_sources import EvidenceRegistry, evidence_catalog, episode_input


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(canonical(value) + b"\n")


def record_fixture(directory, episode, trace, condition="S1", track="controlled"):
    """Deterministic fixture only; no claim that these records came from a model."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    catalog = evidence_catalog(episode)
    registry = EvidenceRegistry(catalog, sha(catalog))
    binding = {"schema": "e009-episode-fixture-v1", "condition": condition, "track": track,
               "episode_sha256": sha(episode), "catalog_sha256": sha(catalog),
               "assigned_stages": list("ABCDE"), "model": "deterministic-reference-fixture",
               "live": False, "no_response_history": True}
    write_once(directory / "private/episode.json", episode)
    write_once(directory / "private/evidence.json", catalog)
    write_once(directory / "binding.json", binding)
    memory, journal, previous_hash = None, [], None
    for record in trace:
        stage = record["stage"]
        public = episode_input(episode, registry, stage, condition, memory, track, journal)
        write_once(directory / f"public/{stage}.json", public)
        event = {"stage": stage, "binding_sha256": sha(binding), "previous_event_sha256": previous_hash,
                 "public_input_sha256": sha(public), "record": deepcopy(record),
                 "origin": {"actor": record["instance_id"], "model": "deterministic-reference-fixture"}}
        previous_hash = sha(event)
        write_once(directory / f"raw/{stage}.json", event)
        if stage != "E":
            # Only the explicit publication, never an automatic measurement->memory conversion.
            memory = deepcopy(record.get("published_memory"))
            journal.append({"stage": stage, "claims": deepcopy(record.get("claims", []))})
    manifest = {p.relative_to(directory).as_posix(): file_hash(p) for p in sorted(directory.rglob("*")) if p.is_file()}
    write_once(directory / "MANIFEST.json", manifest)
    return {"directory": str(directory), "manifest_sha256": file_hash(directory / "MANIFEST.json"),
            "fixture": True, "model_calls": 0}


def replay(directory, expected_manifest_sha256, oracle):
    directory = Path(directory).resolve(strict=True)
    if file_hash(directory / "MANIFEST.json") != expected_manifest_sha256:
        raise ValueError("manifest not equal to externally bound digest")
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    inventory = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if inventory != set(manifest) | {"MANIFEST.json"}:
        raise ValueError("raw inventory changed")
    for name, digest in manifest.items():
        path = (directory / name).resolve(strict=True)
        if not path.is_relative_to(directory) or file_hash(path) != digest:
            raise ValueError("raw file changed or escaped directory")
    read = lambda name: json.loads((directory / name).read_text(encoding="utf-8"))
    binding, episode, catalog = read("binding.json"), read("private/episode.json"), read("private/evidence.json")
    if sha(episode) != binding["episode_sha256"]:
        raise ValueError("episode binding changed")
    registry = EvidenceRegistry(catalog, binding["catalog_sha256"])
    previous_hash, trace, memory, journal = None, [], None, []
    for stage in binding["assigned_stages"]:
        event, public = read(f"raw/{stage}.json"), read(f"public/{stage}.json")
        expected_public = episode_input(episode, registry, stage, binding["condition"], memory, binding["track"], journal)
        if not (event["stage"] == stage == public["stage"] == event["record"]["stage"]
                and event["binding_sha256"] == sha(binding)
                and event["previous_event_sha256"] == previous_hash
                and event["public_input_sha256"] == sha(public)
                and canonical(public) == canonical(expected_public)
                and event["origin"]["actor"] == event["record"]["instance_id"]):
            raise ValueError("event, public input or origin binding broken")
        previous_hash = sha(event)
        trace.append(event["record"])
        if stage != "E":
            memory = deepcopy(event["record"].get("published_memory"))
            journal.append({"stage": stage, "claims": deepcopy(event["record"].get("claims", []))})
    result = (score_natural_chain(episode, trace, oracle) if binding["track"] == "natural"
              else score_chain(episode, trace, oracle, binding["condition"]))
    # Reopen every file after evaluation. No SQLite reader is used against raw artifacts.
    if any(file_hash(directory / name) != digest for name, digest in manifest.items()):
        raise ValueError("evaluation mutated raw files")
    return {"score": result, "raw_files_verified": len(manifest), "raw_unchanged": True,
            "binding": binding, "resource_bytes": {"public_inputs": sum((directory / f"public/{s}.json").stat().st_size
                                                                         for s in binding["assigned_stages"]),
                                                    "raw_records": sum((directory / f"raw/{s}.json").stat().st_size
                                                                       for s in binding["assigned_stages"])},
            "api_usage": None, "wire_transport_measured": False}
