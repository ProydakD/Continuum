"""Cold deterministic reference: known SCM class plus supplied public tables only."""
import json
from pathlib import Path
import time

if __package__:
    from .e008_scm import answer_set, compatible
else:
    from e008_scm import answer_set, compatible


def solve(inputs):
    if not isinstance(inputs, dict) or set(inputs) != {"evidence", "questions"}:
        raise ValueError("reference accepts only public tables and queries")
    records, questions = inputs["evidence"], inputs["questions"]
    if (not isinstance(records, list) or not 1 <= len(records) <= 3
            or any(not isinstance(r, dict) or set(r) != {"id", "kind", "do", "variables", "total", "counts"}
                   for r in records) or len({r["id"] for r in records}) != len(records)
            or not {r["id"] for r in records} <= {"EA", "EB", "EC"}):
        raise ValueError("distinct allowed primary records required")
    if (not isinstance(questions, list) or not questions
            or any(not isinstance(q, dict) or not isinstance(q.get("id"), str) for q in questions)
            or len({q["id"] for q in questions}) != len(questions)):
        raise ValueError("unique public question IDs required")
    indices = compatible(records)
    if not indices:
        raise ValueError("inconsistent primary tables are not ordinary uncertainty")
    answers = []
    for query in questions:
        fields = ({"id", "kind", "source", "target"} if query["kind"] in ("edge", "path") else
                  {"id", "kind", "target", "do"} if query["kind"] == "probability" else
                  {"id", "kind", "target", "given"} if query["kind"] == "conditional" else None)
        if fields is None or set(query) != fields:
            raise ValueError("unexpected reference query field")
        possibilities = answer_set(indices, query)
        value = next(iter(possibilities)) if len(possibilities) == 1 else None
        encoded = value if value is None or type(value) is bool else str(value)
        answers.append({"id": query["id"], "value": encoded, "identified": value is not None})
    return {"answers": answers, "compatible_parameter_assignments": len(indices),
            "scope": "finite class enumeration, no oracle truth or probabilistic weighting of aliases"}


def main():
    import resource  # The actual worker is the pinned Linux container.
    started = time.monotonic()
    result = solve(json.loads(Path("input.json").read_text(encoding="utf-8")))
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result["resources"] = {"solve_wall_seconds": time.monotonic() - started,
                           "process_cpu_seconds": usage.ru_utime + usage.ru_stime,
                           "peak_resident_bytes": usage.ru_maxrss * 1024}
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
