"""PROTOTYPE: Approach B as an optimization problem (docs/design/node_levels.md, "Optimization version"), solved with
OR-Tools CP-SAT. Not imported by the library.

    PYTHONPATH=<dir with ortools> python scripts/node_levels_opt.py DB [--near] [--time 60]

Model. Variables: an integer level p_n in [-K, K] for each node, and a boolean v_q for each overpass pair q = (U over L).
Constraints: if v_q is false, p_nu >= p_nl + 1 for every node nu of U and nl of L.
Minimise  W1 * sum v_q  +  W2 * sum_e len_e * |p_s - p_t|  +  W3 * sum_n |p_n - pref_n|
(violated overpasses, then level steps on long edges, then distance from the level the tags suggest).
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

W1, W1S, W2, W3, K = 1000, 300, 10, 1, 4      # W1S: a same-level crossing (either may be on top)


def preferences(edges):
    """The level the tags suggest for a node: 0 if a ground road touches it, else the level nearest 0 among its edges."""
    near, pref = defaultdict(lambda: 99), {}
    for s, t, lv, *_ in edges.values():
        for n in (s, t):
            if abs(lv) < near[n]:
                near[n], pref[n] = abs(lv), max(-K, min(K, lv))
    return pref


def solve_opt(edges, pairs, time_limit=60.0, workers=8, init=None, init_dropped=(), same=()):
    """``edges``: ``{eid: (s, t, lvl, length_m)}``; ``pairs``: ``[(upper, lower)]``. ``init``: node levels to start from
    (the heuristic's, ``node_levels.solve``) and ``init_dropped`` its dropped pairs. Returns ``(p, violated, info)``."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    nodes = sorted({n for s, t, *_ in edges.values() for n in (s, t)})
    p = {n: m.NewIntVar(-K, K, f"p{n}") for n in nodes}
    pref = preferences(edges)
    terms = []
    v = []
    for i, (u, l) in enumerate(pairs):
        q = m.NewBoolVar(f"v{i}")
        v.append(q)
        for nu in edges[u][:2]:
            for nl in edges[l][:2]:
                m.Add(p[nu] - p[nl] >= 1).OnlyEnforceIf(q.Not())
        terms.append(W1 * q)
    vs = []                       # same-level crossings: disjoint in either order, o_q picks which edge is on top
    for i, (a, b) in enumerate(same):
        q, o = m.NewBoolVar(f"w{i}"), m.NewBoolVar(f"o{i}")
        vs.append((q, o))
        for na in edges[a][:2]:
            for nb in edges[b][:2]:
                m.Add(p[na] - p[nb] >= 1).OnlyEnforceIf([q.Not(), o])
                m.Add(p[nb] - p[na] >= 1).OnlyEnforceIf([q.Not(), o.Not()])
        terms.append(W1S * q)
    for e, (s, t, lv, ln) in edges.items():
        if s == t:
            continue
        d = m.NewIntVar(0, 2 * K, "")
        m.AddAbsEquality(d, p[s] - p[t])
        terms.append(max(1, round(ln / 5)) * W2 * d)
    for n in nodes:
        d = m.NewIntVar(0, 2 * K, "")
        m.AddAbsEquality(d, p[n] - pref.get(n, 0))
        terms.append(W3 * d)
    if init:                                                   # warm start: the heuristic's solution as a hint
        for n in nodes:
            m.AddHint(p[n], max(-K, min(K, init.get(n, 0))))
        gone = set(init_dropped)
        for q, pr in zip(v, pairs):
            m.AddHint(q, 1 if pr in gone else 0)
        for (q, o), (a, b) in zip(vs, same):
            up = all(init.get(x, 0) > init.get(y, 0) for x in edges[a][:2] for y in edges[b][:2])
            dn = all(init.get(y, 0) > init.get(x, 0) for x in edges[a][:2] for y in edges[b][:2])
            m.AddHint(q, 0 if (up or dn) else 1)
            m.AddHint(o, 1 if up else 0)
    m.Minimize(sum(terms))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = workers
    status = sv.Solve(m)
    info = {"status": sv.StatusName(status), "objective": sv.ObjectiveValue(), "bound": sv.BestObjectiveBound(),
            "seconds": round(sv.WallTime(), 1)}
    levels = {n: sv.Value(p[n]) for n in nodes}
    violated = [pairs[i] for i, q in enumerate(v) if sv.Value(q)]
    info["same_given_up"] = sum(sv.Value(q) for q, _ in vs)
    return levels, violated, info


def load_same(db):
    """The crossings with no shared node and the SAME level tag (a zebra, a missing junction): either edge may be on top."""
    import duckdb

    import node_levels as nl
    from mapstyle.map import _roads_union
    con = duckdb.connect(str(db), read_only=True)
    try:
        nl.edge_table(con, _roads_union(con, db))
        return [(str(a), str(b)) for a, b in con.execute("""
            SELECT a.eid, o.eid FROM lv a JOIN lv o ON a.eid < o.eid AND ST_Intersects(a.g, o.g) AND a.l = o.l
                 AND a.s NOT IN (o.s, o.t) AND a.t NOT IN (o.s, o.t) AND ST_Crosses(a.g, o.g)""").fetchall()]
    finally:
        con.close()


def load(db, near=False):
    """``(edges, pairs)`` of a duckOSM db: crossing pairs, and with ``near`` also the pairs whose drawn widths overlap."""
    import duckdb

    import node_levels as nl
    from mapstyle.levels import HALF_WIDTH_M
    from mapstyle.map import _roads_union
    con = duckdb.connect(str(db), read_only=True)
    try:
        union = _roads_union(con, db)
        nl.edge_table(con, union)
        hw = dict(con.execute("SELECT edge_id, any_value(highway) FROM (" + union + ") GROUP BY edge_id").fetchall())
        edges = {str(e): (s, t, int(l), g * 95000.0) for e, s, t, l, g in
                 con.execute("SELECT eid, s, t, l, ST_Length(g) FROM lv").fetchall()}
        pairs = [(str(a), str(b)) for a, b in nl.crossings(con)]
        if near:
            have = set(pairs) | {(b, a) for a, b in pairs}
            for a, b, la, lb, d in con.execute("""
                    SELECT CAST(a.eid AS VARCHAR), CAST(o.eid AS VARCHAR), a.l, o.l, ST_Distance(a.g, o.g) * 95000
                    FROM lv a JOIN lv o ON a.eid < o.eid AND a.l <> o.l AND ST_DWithin(a.g, o.g, 0.0002)
                         AND a.s NOT IN (o.s, o.t) AND a.t NOT IN (o.s, o.t)""").fetchall():
                if (a, b) in have or d >= HALF_WIDTH_M.get(hw.get(int(a)), 3) + HALF_WIDTH_M.get(hw.get(int(b)), 3):
                    continue
                pairs.append((a, b) if la > lb else (b, a))
    finally:
        con.close()
    return edges, pairs


def stats(edges, p, violated, pairs, info):
    span = defaultdict(int)
    for s, t, *_ in edges.values():
        span[abs(p[s] - p[t])] += 1
    lv = defaultdict(int)
    for x in p.values():
        lv[x] += 1
    print(f"pairs {len(pairs)}, violated {len(violated)}; solver {info}")
    print("node levels:", dict(sorted(lv.items())))
    print("edges by level span:", dict(sorted(span.items())))


if __name__ == "__main__":
    near = "--near" in sys.argv
    tl = float(sys.argv[sys.argv.index("--time") + 1]) if "--time" in sys.argv else 60.0
    edges, pairs = load(sys.argv[1], near)
    import node_levels as nl
    p0, left0, dropped0 = nl.solve({e: v[:3] for e, v in edges.items()}, pairs)
    print(f"heuristic start: dropped {len(dropped0)}, violated {len(left0)}")
    same = load_same(sys.argv[1]) if "--same" in sys.argv else []
    p, violated, info = solve_opt(edges, pairs, tl, init=p0, init_dropped=dropped0 + left0, same=same)
    print(f"same-level crossings given: {len(same)}, given up: {info.get('same_given_up')}")
    stats(edges, p, violated, pairs, info)
