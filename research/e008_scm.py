"""Finite binary SCMs: hidden structure, exact evidence and causal queries.

This module generates environments, not model answers. The independent oracle
uses constraint enumeration in e008_oracle.py instead of this forward simulator.
"""
from collections import defaultdict
from functools import lru_cache
from fractions import Fraction
import itertools
import random

VARIABLES = ("V0", "V1", "V2", "V3", "V4")
FAMILIES = ("relay", "fork", "confounded")
GATES = ("and", "or", "xor")
CLASS_DESCRIPTION = """There are five binary measured variables V0,V1,V2,V3,V4.
Two unmeasured independent fair binary variables U and W supply exogenous input.
The unknown roles R,S,T,Z,Y are a permutation of the five measured variables.
R=U; Z=W. Exactly one of these mechanism families applies:
relay: S=R XOR bS; T=S XOR bT.
fork: S=R XOR bS; T=R XOR bT.
confounded: S=U XOR bS; T=S XOR bT (R and S share a hidden cause, not an R->S edge).
Y=g(T,Z) XOR bY, with g one of AND, OR, XOR.
The three b values are unknown bits. Neither family, permutation, g nor bits
are supplied. All 3*120*3*8=8640 assignments belong to the allowed class.
The class may have observationally or interventionally equivalent assignments;
do not interpret multiplicities as posterior probabilities.
Each evidence table is an exact population census over the four equally likely
(U,W) assignments, NOT a sample of four random patients. A do operation replaces
the intervened variable's mechanism by its assigned value and leaves all other
mechanisms and the exogenous distribution unchanged. Conditioning is not do.
Use only the evidence you actually received. A query is identifiable only if
every allowed model consistent with that evidence gives the same answer.
Otherwise answer null, retaining supported alternatives and uncertainty.
"""


def model(family, order, gate, flips):
    if family not in FAMILIES or gate not in GATES or tuple(sorted(order)) != VARIABLES:
        raise ValueError("invalid finite SCM assignment")
    if len(flips) != 3 or any(type(v) is not int or v not in (0, 1) for v in flips):
        raise ValueError("three Boolean polarity bits required")
    r, s, t, z, y = order
    b_s, b_t, b_y = flips
    equations = {
        r: {"op": "copy", "inputs": ["U"], "flip": 0},
        z: {"op": "copy", "inputs": ["W"], "flip": 0},
        s: {"op": "copy", "inputs": ["U" if family == "confounded" else r], "flip": b_s},
        t: {"op": "copy", "inputs": [r if family == "fork" else s], "flip": b_t},
        y: {"op": gate, "inputs": [t, z], "flip": b_y},
    }
    return {"family": family, "order": list(order), "gate": gate, "flips": list(flips),
            "equations": equations}


@lru_cache(maxsize=1)
def candidates():
    return tuple(model(family, order, gate, flips)
                 for family in FAMILIES for order in itertools.permutations(VARIABLES)
                 for gate in GATES for flips in itertools.product((0, 1), repeat=3))


def intervention_map(intervention):
    result = {}
    for name, value in intervention:
        if name not in VARIABLES or type(value) is not int or value not in (0, 1) or name in result:
            raise ValueError("invalid intervention")
        result[name] = value
    return result


def distribution(scm, intervention=()):
    fixed = intervention_map(intervention)
    counts = [0] * 32
    for u, w in itertools.product((0, 1), repeat=2):
        values = {"U": u, "W": w, **fixed}

        def evaluate(name, visiting=frozenset()):
            if name in values:
                return values[name]
            if name in visiting or name not in scm["equations"]:
                raise ValueError("cyclic or incomplete SCM")
            equation = scm["equations"][name]
            operands = [evaluate(parent, visiting | {name}) for parent in equation["inputs"]]
            op = equation["op"]
            if op == "copy" and len(operands) == 1:
                value = operands[0]
            elif op in GATES and len(operands) == 2:
                a, b = operands
                value = a & b if op == "and" else a | b if op == "or" else a ^ b
            else:
                raise ValueError("unsupported mechanism")
            values[name] = value ^ equation["flip"]
            return values[name]

        index = sum(evaluate(name) << (4 - i) for i, name in enumerate(VARIABLES))
        counts[index] += 1
    return tuple(counts)


def evidence(scm, identity, intervention=()):
    counts = distribution(scm, intervention)
    return {"id": identity, "kind": "interventional" if intervention else "observational",
            "do": [list(item) for item in intervention], "variables": list(VARIABLES), "total": 4,
            "counts": [[format(i, "05b"), n] for i, n in enumerate(counts) if n]}


def evidence_counts(record):
    if record["variables"] != list(VARIABLES) or record["total"] != 4:
        raise ValueError("unexpected population/evidence axes")
    expected_kind = "interventional" if record["do"] else "observational"
    if record["kind"] != expected_kind:
        raise ValueError("do and observational labels disagree")
    intervention_map(record["do"])
    result = [0] * 32
    seen = set()
    for bits, count in record["counts"]:
        if not isinstance(bits, str) or len(bits) != 5 or set(bits) - {"0", "1"} or bits in seen:
            raise ValueError("duplicate or invalid population row")
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError("invalid count")
        seen.add(bits)
        result[int(bits, 2)] = count
    if sum(result) != 4:
        raise ValueError("population mass is not four")
    return tuple(result)


@lru_cache(maxsize=1)
def observational_index():
    groups = defaultdict(list)
    for index, scm in enumerate(candidates()):
        groups[distribution(scm)].append(index)
    return dict(groups)


def compatible(records):
    pool = range(len(candidates()))
    observational = next((r for r in records if not r["do"]), None)
    if observational:
        pool = observational_index().get(evidence_counts(observational), ())
    for record in records:
        counts = evidence_counts(record)
        pool = [i for i in pool if distribution(candidates()[i], record["do"]) == counts]
    return list(pool)


def quantity(scm, query):
    kind = query["kind"]
    if kind in ("edge", "path"):
        source, target = query["source"], query["target"]
        if source not in VARIABLES or target not in VARIABLES or source == target:
            raise ValueError("invalid structural query")
        parents = {v: {p for p in e["inputs"] if p in VARIABLES} for v, e in scm["equations"].items()}
        if kind == "edge":
            return source in parents[target]
        reachable, pending = set(), list(parents[target])
        while pending:
            name = pending.pop()
            if name not in reachable:
                reachable.add(name)
                pending.extend(parents[name])
        return source in reachable
    if query["target"] not in VARIABLES:
        raise ValueError("invalid probability target")
    target_bit = 4 - VARIABLES.index(query["target"])
    if kind == "probability":
        counts = distribution(scm, query["do"])
        return Fraction(sum(n for i, n in enumerate(counts) if (i >> target_bit) & 1), 4)
    if kind == "conditional":
        fixed = intervention_map(query["given"])
        counts = distribution(scm)
        eligible = [(i, n) for i, n in enumerate(counts)
                    if all((i >> (4 - VARIABLES.index(v))) & 1 == x for v, x in fixed.items())]
        denominator = sum(n for _, n in eligible)
        if not denominator:
            return None
        return Fraction(sum(n for i, n in eligible if (i >> target_bit) & 1), denominator)
    raise ValueError("unknown causal query")


def answer_set(indices, query):
    if not indices:
        raise ValueError("inconsistent evidence is not ordinary non-identifiability")
    return {quantity(candidates()[i], query) for i in indices}


def query_pool():
    questions = []
    for target in VARIABLES:
        other = [name for name in VARIABLES if name != target]
        for width in (1, 2):
            for names in itertools.combinations(other, width):
                for values in itertools.product((0, 1), repeat=width):
                    questions.append({"kind": "probability", "target": target, "do": [list(x) for x in zip(names, values)]})
        for source in other:
            questions += [{"kind": kind, "source": source, "target": target} for kind in ("edge", "path")]
            questions += [{"kind": "conditional", "target": target, "given": [[source, value]]} for value in (0, 1)]
    return questions


def revision_probe(initial, updated, panel):
    """A controlled false hypothesis and at least two falsified consequences.

    This is private control-design data, never an automatically supplied true
    model or part of the main unmodified chain. A natural model error is a
    different measurement from this deliberate injection.
    """
    final_answers = [answer_set(updated, q) for q in panel]
    survivors = set(updated)
    for index in initial:
        if index in survivors:
            continue
        premise = candidates()[index]
        falsified = [q["id"] for q, allowed in zip(panel, final_answers)
                     if quantity(premise, q) not in allowed]
        if len(falsified) >= 2:
            return {"hypothesis": premise, "dependent_question_ids": falsified,
                    "dependency": "The full asserted SCM hypothesis implies these predictions; their values are not independent evidence.",
                    "scope": "deliberately injected false claim group only; never pooled with spontaneous model errors"}
    return None


def design_world(rng, family, identity):
    """Rejection only by a public, deterministic information-feasibility rule.

    No LLM outcomes are involved. The final experiment must register sample sizes,
    splits and this rule before any model call. Each candidate draws its panel and
    two interventions independently of the hidden assignment.
    """
    pool = query_pool()
    for attempt in range(1, 2001):
        order = rng.sample(list(VARIABLES), 5)
        scm = model(family, order, rng.choice(GATES), [rng.randrange(2) for _ in range(3)])
        assignments = rng.sample([(v, x) for v in VARIABLES for x in (0, 1)], 2)
        if assignments[0][0] == assignments[1][0]:
            continue
        records = [evidence(scm, "EA"), evidence(scm, "EB", [assignments[0]]),
                   evidence(scm, "EC", [assignments[1]])]
        # Selection is on evidence-compatible sets, not the particular hidden truth.
        ab, abc = compatible(records[:2]), compatible(records)
        singles = [compatible([r]) for r in records]
        a = singles[0]
        if not abc or len(abc) >= len(ab) or len(ab) >= len(a):
            continue
        selected = rng.sample(pool, 16)
        panel, successor = selected[:6], selected[6:]
        states = [[answer_set(ids, q) for q in successor] for ids in (a, ab, abc, *singles)]
        integrated = [i for i in range(10) if len(states[2][i]) == 1 and all(len(s[i]) > 1 for s in states[3:])]
        unknown = [i for i, values in enumerate(states[2]) if len(values) > 1]
        # A null answer for undefined observational conditioning is not a causal ambiguity.
        integrated = [i for i in integrated if None not in states[2][i]]
        if len(integrated) < 2 or len(unknown) < 2:
            continue
        panel_sets = [[answer_set(ids, q) for q in panel] for ids in (a, ab, abc)]
        narrowed = [i for i in range(6) if len(panel_sets[2][i]) < len(panel_sets[0][i])]
        if len(narrowed) < 2:
            continue
        for i, query in enumerate(panel):
            query["id"] = f"P{i + 1:02}"
        for i, query in enumerate(successor):
            query["id"] = f"Q{i + 1:02}"
        probe = revision_probe(a, abc, panel)
        if probe is None:
            continue
        return {
            "id": identity, "truth": scm, "evidence": records, "panel": panel, "successor": successor,
            "revision_probe": probe,
            "design_audit": {"attempts": attempt, "candidate_counts_A_AB_ABC": [len(a), len(ab), len(abc)],
                             "single_candidate_counts": list(map(len, singles)),
                             "integrative_question_ids": [successor[i]["id"] for i in integrated],
                             "unidentifiable_question_ids": [successor[i]["id"] for i in unknown],
                             "panel_narrowed_ids": [panel[i]["id"] for i in narrowed]},
        }
    raise ValueError("information-feasibility rejection ceiling exceeded; no model experiment started")


def pilot_corpus(seed=2026102008, per_family=2):
    rng = random.Random(seed)
    return [design_world(rng, family, f"offline-{family}-{i + 1:02}")
            for family in FAMILIES for i in range(per_family)]


if __name__ == "__main__":
    import json
    import sys
    import time
    from pathlib import Path
    started = time.monotonic()
    worlds = pilot_corpus()
    output = {"scope": "offline design only; not registered or model-tested", "worlds": worlds,
              "candidate_assignments": len(candidates()), "seconds": time.monotonic() - started}
    Path(sys.argv[1]).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in output.items() if k != "worlds"}))
    print(json.dumps([{"id": w["id"], **w["design_audit"]} for w in worlds]))
