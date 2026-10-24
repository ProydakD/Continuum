"""Новый конечный causal corpus E009; не читает исходы или миры E008."""
from functools import lru_cache
from itertools import product
import random

NAMES = ("X", "Y", "Z", "W", "V", "Q")
FAMILIES = ("chain", "fork", "confounded", "common-source")
GATES = ("and", "or", "xor")


@lru_cache(maxsize=1)
def models():
    return tuple((family, g, h, bits) for family, g, h, bits in
                 product(FAMILIES, GATES, GATES, tuple(product((0, 1), repeat=4))))


def intervention(items):
    fixed = dict(items)
    if len(fixed) != len(items) or any(k not in NAMES or type(v) is not int or v not in (0, 1)
                                     for k, v in items):
        raise ValueError("invalid intervention")
    return fixed


def gate(name, a, b):
    return {"and": a & b, "or": a | b, "xor": a ^ b}[name]


@lru_cache(maxsize=None)
def distribution(index, do=()):
    family, g, h, bits = models()[index]
    fixed = intervention(do)
    counts = [0] * 64
    for u0, u1, u2 in product((0, 1), repeat=3):
        x = fixed.get("X", u0)
        y = fixed.get("Y", (u0 if family == "confounded" else x) ^ bits[0])
        parent = x if family == "fork" else u0 if family == "common-source" else y
        z = fixed.get("Z", parent ^ bits[1])
        w = fixed.get("W", u1)
        v = fixed.get("V", gate(g, z, w) ^ bits[2])
        q = fixed.get("Q", gate(h, v, u2) ^ bits[3])
        counts[x * 32 + y * 16 + z * 8 + w * 4 + v * 2 + q] += 1
    return tuple(counts)


def evidence(index, identity, do=()):
    return {"id": identity, "kind": "interventional" if do else "observational",
            "do": [list(p) for p in do], "total": 8, "counts": list(distribution(index, do))}


def compatible(records):
    return frozenset(i for i in range(len(models())) if all(
        distribution(i, tuple(map(tuple, r["do"]))) == tuple(r["counts"]) for r in records))


def edges(index):
    family = models()[index][0]
    links = {("Z", "V"), ("W", "V"), ("V", "Q")}
    if family != "confounded":
        links.add(("X", "Y"))
    if family in ("chain", "confounded"):
        links.add(("Y", "Z"))
    elif family == "fork":
        links.add(("X", "Z"))
    return links


def quantity(index, query):
    kind = query["kind"]
    if kind == "model":
        return int(index == query["index"])
    if kind in ("edge", "path"):
        links = edges(index)
        if kind == "edge":
            return int((query["source"], query["target"]) in links)
        reached, pending = set(), [query["source"]]
        while pending:
            node = pending.pop()
            for a, b in links:
                if a == node and b not in reached:
                    reached.add(b)
                    pending.append(b)
        return int(query["target"] in reached)
    if kind != "probability":
        raise ValueError("unknown query kind")
    counts = distribution(index, tuple(map(tuple, query.get("do", []))))
    bit = 5 - NAMES.index(query["target"])
    # Целый числитель при знаменателе 8; никаких сравнений float.
    return sum(n for row, n in enumerate(counts) if row & (1 << bit))


def proposition(query, value):
    return {"query": query, "value": value}


def make_world(index, identity):
    records = [evidence(index, "EA"), evidence(index, "EB", (("X", 0),)),
               evidence(index, "EC", (("Y", 0),)), evidence(index, "ED", (("Z", 1),))]
    initial, revised = compatible(records[:1]), compatible(records[:3])
    edge = {"kind": "edge", "source": "Y", "target": "Z"}
    path = {"kind": "path", "source": "Y", "target": "Q"}
    wrong = next((i for i in sorted(initial - revised)
                  if all(quantity(i, edge) != quantity(j, edge) for j in revised)), None)
    if wrong is None:
        raise ValueError("no registered dependency-refutation opportunity")
    # Edge Y->Z and path Y->Q are equivalent only in this finite class.
    # This is a valid depth-two fixture, not proof of general graph complexity.
    assert all(quantity(i, edge) == quantity(i, path) for i in range(len(models())))

    def claim(cid, query, value, bases):
        return {"id": cid, "version": 1, "origin": "synthetic-prior-investigator",
                "proposition": proposition(query, value), "status": "supported", "bases": bases}

    obs_q = {"kind": "probability", "target": "Q", "do": []}
    obs_v = {"kind": "probability", "target": "V", "do": []}
    claims = [claim("H", {"kind": "model", "index": wrong}, 1, [["e:EA"]]),
              claim("D1", edge, quantity(wrong, edge), [["c:H"]]),
              claim("D2", path, quantity(wrong, path), [["c:D1"]]),
              claim("K", obs_q, quantity(index, obs_q), [["c:H"], ["e:EA"]]),
              claim("I", obs_v, quantity(index, obs_v), [["e:EA"]])]
    queries = [{"kind": "probability", "target": target, "do": [[source, value]]}
               for target in ("Y", "Z", "V", "Q") for source in ("X", "Y", "Z")
               for value in (0, 1) if source != target]
    new_query = next((q for q in queries if len({quantity(j, q) for j in revised}) == 1
                      and quantity(wrong, q) not in {quantity(j, q) for j in revised}), None)
    if new_query is None:
        raise ValueError("no novel causal query")
    after_b = compatible(records[:2])
    withdrawal_query = next((q for q in queries if len({quantity(j, q) for j in after_b}) == 1
                             and len({quantity(j, q) for j in initial}) > 1), None)
    if withdrawal_query is None:
        raise ValueError("no source-withdrawal opportunity")
    return {"id": identity, "split": "offline-development", "hidden_model": index,
            "evidence": records, "claims": claims, "new_query": new_query,
            "withdrawal": {"query": withdrawal_query,
                           "value": quantity(index, withdrawal_query), "revoke": "EB"},
            "candidate_counts": [len(compatible(records[:n])) for n in range(1, 5)]}


def development_corpus(count=12, seed=2026102409):
    if not 1 <= count <= len(models()):
        raise ValueError("invalid corpus size")
    order = list(range(len(models())))
    random.Random(seed).shuffle(order)
    worlds, rejected = [], []
    for index in order:
        try:
            worlds.append(make_world(index, f"e009-dev-{len(worlds) + 1:03}"))
        except ValueError as error:
            rejected.append({"model": index, "reason": str(error)})
        if len(worlds) == count:
            return {"worlds": worlds, "rejected": rejected, "seed": seed,
                    "heldout": False, "selection": "oracle feasibility only; no model outcomes"}
    raise ValueError("feasibility exhausted; do not silently reduce N")
