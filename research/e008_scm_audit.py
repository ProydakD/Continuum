"""Independent finite-world gate; outputs stay outside Git and outside workers."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import time

from . import e008_oracle as oracle
from .e008_scm import VARIABLES, answer_set, candidates, compatible, distribution, quantity


def serialized_values(values):
    def convert(value):
        if value is None or type(value) is bool:
            return value
        return str(value)
    return sorted((convert(v) for v in values), key=lambda v: json.dumps(v))


def inspect_world(world):
    models, records = candidates(), world["evidence"]
    groups = {"A": records[:1], "AB": records[:2], "ABC": records,
              "B_only": records[1:2], "C_only": records[2:]}
    compatible_sets = {}
    for name, subset in groups.items():
        independent = oracle.compatible_models(models, subset)
        if independent != compatible(subset):
            raise ValueError("independent model set mismatch: " + world["id"] + "/" + name)
        if not independent or world["truth"] not in [models[i] for i in independent]:
            raise ValueError("true SCM excluded or inconsistent corpus")
        compatible_sets[name] = independent
    if not (set(compatible_sets["ABC"]) < set(compatible_sets["AB"]) < set(compatible_sets["A"])):
        raise ValueError("new evidence must strictly exclude previously allowed explanations")
    scored = {}
    for group, indices in compatible_sets.items():
        scored[group] = {}
        for question in world["panel"] + world["successor"]:
            result = oracle.identify(models, indices, question)
            if result["possibilities"] != answer_set(indices, question):
                raise ValueError("independent identifiability mismatch")
            actual = oracle.answer(world["truth"], question)
            if actual != quantity(world["truth"], question) or actual not in result["possibilities"]:
                raise ValueError("hidden truth inconsistent with answer set")
            scored[group][question["id"]] = {"identified": result["identified"],
                "possibilities": serialized_values(result["possibilities"])}
    integrated, unknown = [], []
    for q in world["successor"]:
        identity = q["id"]
        full = scored["ABC"][identity]
        if full["identified"] and all(not scored[g][identity]["identified"] for g in ("A", "B_only", "C_only")):
            integrated.append(identity)
        if len(full["possibilities"]) > 1:
            unknown.append(identity)
    narrowed = [q["id"] for q in world["panel"]
                if len(scored["ABC"][q["id"]]["possibilities"]) < len(scored["A"][q["id"]]["possibilities"])]
    if len(integrated) < 2 or len(unknown) < 2 or len(narrowed) < 2:
        raise ValueError("insufficient integration, honest abstention or revision opportunities")
    declared = world["design_audit"]
    if (declared["integrative_question_ids"] != integrated or declared["unidentifiable_question_ids"] != unknown
            or declared["panel_narrowed_ids"] != narrowed):
        raise ValueError("generator metadata contradicts independent oracle")
    probe = world["revision_probe"]
    hypothesis = probe["hypothesis"]
    if not oracle.compatible_models([hypothesis], records[:1]) or oracle.compatible_models([hypothesis], records):
        raise ValueError("controlled hypothesis must be initially permissible and later excluded")
    falsified = [q["id"] for q in world["panel"]
                 if oracle.answer(hypothesis, q) not in oracle.identify(models, compatible_sets["ABC"], q)["possibilities"]]
    if len(falsified) < 2 or falsified != probe["dependent_question_ids"]:
        raise ValueError("dependent consequences not independently falsified")
    return {"world": world["id"], "pass": True, "candidate_counts": {k: len(v) for k, v in compatible_sets.items()},
            "integrative_question_ids": integrated, "unidentifiable_question_ids": unknown,
            "panel_narrowed_ids": narrowed, "controlled_falsified_dependents": falsified, "gold_by_evidence_group": scored}


def exhaustive():
    """Every permitted parameter assignment, every do of zero/one/two variables."""
    started = time.monotonic()
    interventions = [()]
    for width in (1, 2):
        interventions += [tuple(zip(names, values)) for names in itertools.combinations(VARIABLES, width)
                          for values in itertools.product((0, 1), repeat=width)]
    checked, counts, stream = 0, Counter(), hashlib.sha256()
    identities = set()
    for scm in candidates():
        identity = (scm["family"], tuple(scm["order"]), scm["gate"], tuple(scm["flips"]))
        if identity in identities:
            raise ValueError("duplicate class parameter assignment")
        identities.add(identity)
        for do in interventions:
            expected = oracle.census(scm["equations"], do)
            if distribution(scm, do) != expected or sum(expected) != 4:
                raise ValueError("forward simulator / constraint oracle counterexample")
            stream.update(bytes(expected))
            checked += 1
        counts[scm["family"]] += 1
    if counts != {"relay": 2880, "fork": 2880, "confounded": 2880} or checked != 440640:
        raise ValueError("incomplete finite-space check")
    return {"pass": True, "parameter_assignments": len(identities), "per_family": dict(counts),
            "do_settings_per_assignment": len(interventions), "verified_distributions": checked,
            "distribution_stream_sha256": stream.hexdigest(), "seconds": time.monotonic() - started,
            "scope": "Complete allowed finite SCM class, all interventions of at most two measured variables; not arbitrary causal models or LLM competence."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--exhaustive", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"pass": True}
    if args.exhaustive:
        result["exhaustive"] = exhaustive()
    if args.corpus:
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
        result["corpus_sha256"] = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
        result["worlds"] = [inspect_world(w) for w in corpus["worlds"]]
    if not (args.exhaustive or args.corpus):
        parser.error("choose a corpus or exhaustive verification")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "worlds"}))
    if "worlds" in result:
        print(json.dumps({"independently_verified_worlds": len(result["worlds"]),
                          "integrative_questions": sum(len(w["integrative_question_ids"]) for w in result["worlds"]),
                          "nonidentifiable_questions": sum(len(w["unidentifiable_question_ids"]) for w in result["worlds"]),
                          "controlled_falsified_dependents": sum(len(w["controlled_falsified_dependents"]) for w in result["worlds"])}))
