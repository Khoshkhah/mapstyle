"""Checks of the interval model (docs/design/node_levels.md): (1) an independent re-check of a solver answer, in plain Python,
and (2) the solver against brute force on small random instances.

    NL_RANGE=1 PYTHONPATH=<ortools dir> python scripts/node_levels_check.py brute
    NL_RANGE=20 PYTHONPATH=<ortools dir> python scripts/node_levels_check.py monaco DB
"""
import itertools
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import node_levels_opt as no  # noqa: E402


def check(edges, pairs, same, out):
    """Count, in plain Python, what the intervals ``out`` violate: the range, the intersections of edges that share a node
    (must be 0), the overpass pairs (U's casing after L's fill) and the same-level crossings (disjoint, either order)."""
    lo, hi = no.LO, no.HI
    bad_range = sum(1 for a, b in out.values() if not (lo <= a <= b <= hi))
    bad_join = sum(1 for x, y in no.join_pairs(edges) if not (out[x][0] <= out[y][1] and out[y][0] <= out[x][1]))
    bad_over = sum(1 for u, l in pairs if not out[l][1] + 1 <= out[u][0])
    bad_same = sum(1 for x, y in same if not (out[y][1] + 1 <= out[x][0] or out[x][1] + 1 <= out[y][0]))
    return bad_range, bad_join, bad_over, bad_same


def brute(n_instances=300, seed=1):
    """Random tiny instances: the solver's minimum equals the minimum over ALL interval assignments."""
    rnd = random.Random(seed)
    opts = [(a, b) for a in range(no.LO, no.HI + 1) for b in range(a, no.HI + 1)]
    bad = 0
    for k in range(n_instances):
        ne = rnd.randint(3, 5)
        nn = rnd.randint(3, 6)
        edges = {}
        for i in range(ne):
            s, t = rnd.sample(range(nn), 2)
            edges[f"e{i}"] = (s, t, rnd.choice([-1, 0, 0, 1]), 10.0)
        names = list(edges)
        free = [(x, y) for x, y in itertools.combinations(names, 2)
                if not ({edges[x][0], edges[x][1]} & {edges[y][0], edges[y][1]})]
        pairs = [(x, y) if edges[x][2] > edges[y][2] else (y, x) for x, y in free if edges[x][2] != edges[y][2] and rnd.random() < 0.8]
        same = [(x, y) for x, y in free if edges[x][2] == edges[y][2] and rnd.random() < 0.8]
        best = None
        for combo in itertools.product(opts, repeat=ne):
            out = dict(zip(names, combo))
            if check(edges, [], [], out)[1]:
                continue
            _, _, bo, bs = check(edges, pairs, same, out)
            if best is None or bo + bs < best:
                best = bo + bs
        sol, given, info = no.solve_pure_all(edges, pairs, same, 20, workers=1)
        if best is None:
            continue
        if given != best or check(edges, pairs, same, sol)[:2] != (0, 0) or sum(check(edges, pairs, same, sol)[2:]) != given:
            bad += 1
            print("MISMATCH", k, "brute", best, "solver", given, info["status"])
    print(f"{n_instances} random instances: {bad} mismatches between the solver and brute force")


def monaco(db):
    import node_levels as nl
    edges, pairs = no.load(db)
    same = no.load_same(db)
    p0, left0, dropped0 = nl.solve({e: v[:3] for e, v in edges.items()}, pairs)
    out, given, info = no.solve_pure_all(edges, pairs, same, 60, init=p0)
    print("directed edges: solver says given up", given, info["status"])
    print("independent check (range, join, overpass, same-level violations):", check(edges, pairs, same, out))


if __name__ == "__main__":
    brute() if sys.argv[1] == "brute" else monaco(sys.argv[2])
