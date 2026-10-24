"""Независимый constraint oracle: не импортирует forward simulator E009."""
from functools import lru_cache
from itertools import product

VARIABLES = ("X", "Y", "Z", "W", "V", "Q")


def freeze_model(model):
    family, first, second, bits = model
    if family not in {"chain", "fork", "confounded", "common-source"}:
        raise ValueError("invalid family")
    if first not in {"and", "or", "xor"} or second not in {"and", "or", "xor"}:
        raise ValueError("invalid gate")
    if len(bits) != 4 or any(type(b) is not int or b not in (0, 1) for b in bits):
        raise ValueError("invalid polarities")
    return family, first, second, tuple(bits)


def fixed_values(do):
    result = {}
    for name, value in do:
        if name not in VARIABLES or name in result or type(value) is not int or value not in (0, 1):
            raise ValueError("invalid do")
        result[name] = value
    return result


@lru_cache(maxsize=None)
def solve(model, do=()):
    family, g, h, bits = freeze_model(model)
    fixed = fixed_values(do)
    truth_tables = {"and": (0, 0, 0, 1), "or": (0, 1, 1, 1), "xor": (0, 1, 1, 0)}
    counts = [0] * 64
    for u in product((0, 1), repeat=3):
        satisfying = []
        for number, row in enumerate(product((0, 1), repeat=6)):
            x, y, z, w, v, q = row
            y_parent = u[0] if family == "confounded" else x
            z_parent = {"chain": y, "fork": x, "confounded": y, "common-source": u[0]}[family]
            rhs = (u[0], y_parent ^ bits[0], z_parent ^ bits[1], u[1],
                   truth_tables[g][z * 2 + w] ^ bits[2], truth_tables[h][v * 2 + u[2]] ^ bits[3])
            if all(value == (fixed[name] if name in fixed else expected)
                   for name, value, expected in zip(VARIABLES, row, rhs)):
                satisfying.append(number)
        if len(satisfying) != 1:
            raise ValueError("SCM constraint system not uniquely solvable")
        counts[satisfying[0]] += 1
    return tuple(counts)


def validate_evidence(record):
    do = tuple(map(tuple, record["do"]))
    fixed_values(do)
    counts = record["counts"]
    if record["kind"] != ("interventional" if do else "observational"):
        raise ValueError("kind/do mismatch")
    if record["total"] != 8 or len(counts) != 64 or sum(counts) != 8:
        raise ValueError("invalid population table")
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValueError("invalid population counts")
    return do


class Oracle:
    def __init__(self, models):
        self.models = tuple(freeze_model(m) for m in models)

    def compatible(self, records):
        if len({r["id"] for r in records}) != len(records):
            raise ValueError("duplicate evidence ID")
        validated = [(validate_evidence(r), tuple(r["counts"])) for r in records]
        return frozenset(i for i, model in enumerate(self.models)
                         if all(solve(model, do) == counts for do, counts in validated))

    def quantity(self, index, query):
        if query["kind"] == "model":
            if type(query["index"]) is not int or not 0 <= query["index"] < len(self.models):
                raise ValueError("invalid model ID")
            return int(index == query["index"])
        if query["kind"] in ("edge", "path"):
            source, target = query["source"], query["target"]
            if source not in VARIABLES or target not in VARIABLES or source == target:
                raise ValueError("invalid graph query")
            family = self.models[index][0]
            parents = {"X": (), "Y": () if family == "confounded" else ("X",),
                       "Z": ("Y",) if family in ("chain", "confounded") else
                       ("X",) if family == "fork" else (),
                       "W": (), "V": ("Z", "W"), "Q": ("V",)}
            if query["kind"] == "edge":
                return int(source in parents[target])
            def ancestor(node):
                return any(p == source or ancestor(p) for p in parents[node])
            return int(ancestor(target))
        if query["kind"] != "probability" or query["target"] not in VARIABLES:
            raise ValueError("invalid probability query")
        counts = solve(self.models[index], tuple(map(tuple, query.get("do", []))))
        column = VARIABLES.index(query["target"])
        return sum(counts[i] for i, row in enumerate(product((0, 1), repeat=6)) if row[column])

    def status(self, candidates, proposition):
        if not candidates:
            return "conflicted"
        values = {self.quantity(i, proposition["query"]) == proposition["value"] for i in candidates}
        return "supported" if values == {True} else "refuted" if values == {False} else "undetermined"

    def answer(self, candidates, query):
        if not candidates:
            raise ValueError("conflicted evidence has no ordinary unknown answer")
        values = {self.quantity(i, query) for i in candidates}
        return next(iter(values)) if len(values) == 1 else None
