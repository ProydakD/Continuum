"""Independent finite-SCM oracle by satisfying structural constraints.

No imports of the environment simulator, its forward evaluator or scoring code.
Identifiability is relative to all supplied candidate models, not hidden truth.
"""
from fractions import Fraction
import itertools


def census(equations, intervention=()):
    names = sorted(equations)
    if len(names) != 5:
        raise ValueError("expected five measured variables")
    clamps = {}
    for name, value in intervention:
        if name not in equations or name in clamps or type(value) is not int or value not in (0, 1):
            raise ValueError("invalid do assignment")
        clamps[name] = value
    free = [v for v in names if v not in clamps]
    counts = [0] * 32
    for hidden in itertools.product((0, 1), repeat=2):
        solutions = []
        for assignment in itertools.product((0, 1), repeat=len(free)):
            state = dict(zip(free, assignment))
            state.update(clamps)
            state.update(zip(("U", "W"), hidden))
            valid = True
            for name in free:
                equation = equations[name]
                values = [state[p] for p in equation["inputs"]]
                operation = equation["op"]
                if operation == "copy" and len(values) == 1:
                    expected = values[0]
                elif operation == "and" and len(values) == 2:
                    expected = int(all(values))
                elif operation == "or" and len(values) == 2:
                    expected = int(any(values))
                elif operation == "xor" and len(values) == 2:
                    expected = int(values[0] != values[1])
                else:
                    raise ValueError("unknown mechanism")
                if equation["flip"] not in (0, 1):
                    raise ValueError("invalid polarity")
                if equation["flip"]:
                    expected = 1 - expected
                if state[name] != expected:
                    valid = False
                    break
            if valid:
                solutions.append(int("".join(str(state[v]) for v in names), 2))
        if len(solutions) != 1:
            raise ValueError("SCM does not have a unique solution for every exogenous state")
        counts[solutions[0]] += 1
    return tuple(counts)


def record_table(record):
    names = ["V0", "V1", "V2", "V3", "V4"]
    if record["variables"] != names or record["total"] != 4:
        raise ValueError("invalid evidence population")
    if record["kind"] != ("interventional" if record["do"] else "observational"):
        raise ValueError("observation/do mismatch")
    rows = {}
    for bits, count in record["counts"]:
        if not isinstance(bits, str) or len(bits) != 5 or any(b not in "01" for b in bits) or bits in rows:
            raise ValueError("invalid or duplicate evidence row")
        if type(count) is not int or count < 1 or count > 4:
            raise ValueError("invalid population count")
        rows[bits] = count
    if sum(rows.values()) != 4:
        raise ValueError("incorrect population mass")
    return tuple(rows.get(format(i, "05b"), 0) for i in range(32))


def compatible_models(models, records):
    tables = [(record["do"], record_table(record)) for record in records]
    return [i for i, model in enumerate(models) if all(census(model["equations"], do) == table for do, table in tables)]


def answer(model, query):
    equations = model["equations"]
    names = sorted(equations)
    kind, target = query["kind"], query["target"]
    if target not in names:
        raise ValueError("unknown target")
    if kind in ("edge", "path"):
        source = query["source"]
        if source not in names or source == target:
            raise ValueError("invalid graph query")
        edges = {(parent, child) for child, eq in equations.items() for parent in eq["inputs"] if parent in names}
        if kind == "edge":
            return (source, target) in edges
        # Transitive closure, independently of the simulator's ancestor walk.
        closure = set(edges)
        for middle in names:
            closure |= {(a, b) for a in names for b in names if (a, middle) in closure and (middle, b) in closure}
        return (source, target) in closure
    if kind not in ("probability", "conditional"):
        raise ValueError("unknown query kind")
    intervention = query["do"] if kind == "probability" else []
    table = census(equations, intervention)
    numerator = denominator = 0
    given = query["given"] if kind == "conditional" else []
    if len(dict(given)) != len(given) or any(v not in names or type(x) is not int or x not in (0, 1) for v, x in given):
        raise ValueError("invalid condition")
    for i, count in enumerate(table):
        bits = dict(zip(names, map(int, format(i, "05b"))))
        if all(bits[name] == value for name, value in given):
            denominator += count
            if bits[target] == 1:
                numerator += count
    return Fraction(numerator, denominator) if denominator else None


def identify(models, indices, query):
    if not indices:
        raise ValueError("inconsistent evidence; not a non-identifiable model class")
    values = {answer(models[i], query) for i in indices}
    return {"identified": len(values) == 1 and None not in values,
            "value": next(iter(values)) if len(values) == 1 else None, "possibilities": values}
