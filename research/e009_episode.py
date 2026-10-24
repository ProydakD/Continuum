"""Multi-level belief graphs and repeated admissibility updates for E009.

Generator selection uses the forward simulator only. Independent checks use
Oracle and never alter a generated episode according to a model's performance.
"""
from copy import deepcopy
from functools import lru_cache
from itertools import permutations
import json
import random

from .e009_scm import NAMES, compatible, evidence, models, proposition, quantity


def query_key(query):
    return json.dumps(query, sort_keys=True, separators=(",", ":"))


def truth_set(oracle, predicate):
    return frozenset(i for i in range(len(oracle.models))
                     if oracle.quantity(i, predicate["query"]) == predicate["value"])


@lru_cache(maxsize=None)
def forward_truth(query_json, value):
    query = json.loads(query_json)
    return frozenset(i for i in range(len(models())) if quantity(i, query) == value)


def graph_queries():
    return [{"kind": kind, "source": source, "target": target}
            for kind in ("edge", "path") for source, target in permutations(NAMES, 2)]


def probability_queries():
    return [{"kind": "probability", "target": target, "do": [[source, value]]}
            for target, source in permutations(NAMES, 2) for value in (0, 1)]


def active_evidence(episode, stage):
    if stage not in tuple("ABCDE"):
        raise ValueError("invalid stage")
    records = {r["id"]: r for r in episode["evidence"]}
    if len(records) != len(episode["evidence"]):
        raise ValueError("duplicate immutable source ID")
    active, seen = set(), set()
    for update in episode["updates"]:
        for identity in update["revoke"]:
            if identity not in active:
                raise ValueError("cannot revoke absent/inactive source")
            active.remove(identity)
        for identity in update["add"]:
            if identity not in records or identity in seen:
                raise ValueError("source missing or immutable identity reused")
            active.add(identity)
            seen.add(identity)
        if update["stage"] == stage:
            return [deepcopy(records[i]) for i in sorted(active)]
    raise ValueError("missing stage update")


def select_graph(initial, revised):
    """Strict entailment H < D1 < D2 < D3 plus a nonredundant AND node."""
    universe = frozenset(range(len(models())))
    for wrong in sorted(initial - revised):
        predicates = {}
        for query in graph_queries():
            value = quantity(wrong, query)
            truths = forward_truth(query_key(query), value)
            if 1 < len(truths) < len(universe):
                predicates.setdefault(truths, proposition(query, value))
        ordered = sorted(predicates, key=lambda s: (len(s), tuple(sorted(s))))
        for first in ordered:
            if first & revised:
                continue
            for second in ordered:
                if not first < second or second & revised:
                    continue
                for third in ordered:
                    if not second < third:
                        continue
                    conjunction = first & initial
                    for query in probability_queries():
                        value = quantity(wrong, query)
                        truths = forward_truth(query_key(query), value)
                        if conjunction and conjunction <= truths and not first <= truths and not initial <= truths:
                            return wrong, [predicates[s] for s in (first, second, third)], proposition(query, value)
    raise ValueError("no strict three-level + necessary conjunction graph; preserve rejection")


def make_episode(index, identity):
    records = [evidence(index, "EA"), evidence(index, "EB", (("X", 0),)),
               evidence(index, "EC", (("Y", 0),)), evidence(index, "ED", (("X", 1),)),
               evidence(index, "EE", (("Y", 1),))]
    initial, revised = compatible(records[:1]), compatible(records[:3])
    wrong, chain, joined = select_graph(initial, revised)

    def claim(cid, predicate, bases):
        return {"id": cid, "version": 1, "origin": "prior-investigator",
                "proposition": predicate, "status": "supported", "bases": bases}

    census = {"kind": "census_match", "do": [], "counts": records[0]["counts"]}
    obs_q = {"kind": "probability", "target": "Q", "do": []}
    obs_v = {"kind": "probability", "target": "V", "do": []}
    claims = [claim("H", proposition({"kind": "model", "index": wrong}, 1), [["e:EA"]]),
              claim("D1", chain[0], [["c:H"]]),
              claim("D2", chain[1], [["c:D1"]]),
              claim("D3", chain[2], [["c:D2"]]),
              claim("J", proposition(census, 1), [["e:EA"]]),
              claim("D4", joined, [["c:D1", "c:J"]]),
              claim("K", proposition(obs_q, quantity(index, obs_q)), [["c:H"], ["e:EA"]]),
              claim("I", proposition(obs_v, quantity(index, obs_v)), [["e:EA"]])]
    updates = [{"stage": "A", "add": ["EA"], "revoke": [], "reason": "initial census"},
               {"stage": "B", "add": ["EB", "EC"], "revoke": [], "reason": "new interventions"},
               {"stage": "C", "add": [], "revoke": ["EB", "EC"],
                "reason": "sources withdrawn by evidence authority; their counts are no longer admissible"},
               {"stage": "D", "add": ["ED", "EE"], "revoke": [], "reason": "new independent intervention censuses"},
               {"stage": "E", "add": [], "revoke": [], "reason": "independent final reader"}]
    final = compatible([records[0], records[3], records[4]])
    used_queries = {query_key(c["proposition"]["query"]) for c in claims}
    novel = next((query for query in probability_queries()
                  if query_key(query) not in used_queries
                  and len({quantity(i, query) for i in final}) == 1
                  and quantity(wrong, query) not in {quantity(i, query) for i in final}), None)
    if novel is None:
        raise ValueError("no non-panel novel question")
    episode = {"id": identity, "split": "offline-development", "hidden_model": index,
               "evidence": records, "updates": updates, "claims": claims, "new_query": novel,
               "registered": {"roots": ["H"], "descendants": ["D1", "D2", "D3", "D4"],
                              "independent": ["I", "J", "K"], "stages": list("ABCD")}}
    episode["design_audit"] = {"candidate_counts": {s: len(compatible(active_evidence(episode, s))) for s in "ABCDE"},
                               "strict_implication_sizes": [1] + [len(forward_truth(query_key(p["query"]), p["value"])) for p in chain],
                               "conjunction_each_premise_necessary": True,
                               "scope": "finite class; no claim of arbitrary causal graph coverage"}
    return episode


def episode_corpus(count=12, seed=2026102409):
    if not 1 <= count <= len(models()):
        raise ValueError("invalid corpus size")
    order = list(range(len(models())))
    random.Random(seed).shuffle(order)
    episodes, rejected = [], []
    for index in order:
        try:
            episodes.append(make_episode(index, f"e009-episode-dev-{len(episodes) + 1:03}"))
        except ValueError as error:
            rejected.append({"model": index, "reason": str(error)})
        if len(episodes) == count:
            return {"episodes": episodes, "rejected": rejected, "seed": seed, "heldout": False,
                    "selection": "forward logical feasibility; independent oracle audits afterward"}
    raise ValueError("corpus feasibility exhausted")
