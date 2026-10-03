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


if __name__ == "__main__" and "--intervals" not in sys.argv and "--pure" not in sys.argv and "--compact" not in sys.argv and "--all" not in sys.argv and "--links" not in sys.argv:
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


# ---------------------------------------------------------------------------------------------------------------
# Kaveh's formulation (2026-10-02): a free interval [a_e, b_e] for each edge, large integer ends, no node variables.
# a_e: the time of the casing, b_e: the time of the fill (in units where casing = 2a, fill = 2b + 1).
#   edges that share a node                : the intervals intersect          a_x <= b_y  and  a_y <= b_x
#   overpass (U over L, no shared node)    : disjoint, U later                b_L + 1 <= a_U    (may be given up, v_q)
#   same-level crossing                    : disjoint in either order         b_a < a_b  or  b_b < a_a   (may be given up)
#   other pairs                            : free
# The node levels of the heuristic are only the starting hint.
# ---------------------------------------------------------------------------------------------------------------
import os
R_ = int(os.environ.get("NL_RANGE", "10"))
LO, HI = -R_, R_       # the ends are integers in [LO, HI]  (environment NL_RANGE, default 10)
GROUND = 0             # the value the tags suggest for level 0


def join_pairs(edges):
    """``[(x, y)]``: every two edges that share a node."""
    at = defaultdict(list)
    for e, (s, t, *_) in edges.items():
        at[s].append(e)
        if t != s:
            at[t].append(e)
    seen = set()
    for es in at.values():
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                seen.add((es[i], es[j]) if es[i] < es[j] else (es[j], es[i]))
    return sorted(seen)


def solve_intervals(edges, pairs, same=(), time_limit=120.0, workers=8, init=None, init_dropped=()):
    """``edges``: ``{eid: (s, t, lvl, length_m)}``. Returns ``({eid: (a, b)}, violated overpass pairs, info)``."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    a = {e: m.NewIntVar(LO, HI, "") for e in edges}
    b = {e: m.NewIntVar(LO, HI, "") for e in edges}
    for e in edges:
        m.Add(a[e] <= b[e])
    joins = join_pairs(edges)
    for x, y in joins:
        m.Add(a[x] <= b[y])
        m.Add(a[y] <= b[x])
    terms, v = [], []
    for i, (u, l) in enumerate(pairs):
        q = m.NewBoolVar(f"v{i}")
        v.append(q)
        m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q.Not())
        terms.append(W1 * q)
    vs = []
    for i, (x, y) in enumerate(same):
        q, o = m.NewBoolVar(f"w{i}"), m.NewBoolVar(f"o{i}")
        vs.append((q, o))
        m.Add(b[y] + 1 <= a[x]).OnlyEnforceIf([q.Not(), o])
        m.Add(b[x] + 1 <= a[y]).OnlyEnforceIf([q.Not(), o.Not()])
        terms.append(W1S * q)
    top, bottom = m.NewIntVar(LO, HI, "top"), m.NewIntVar(LO, HI, "bottom")
    for e, (s, t, lv, ln) in edges.items():
        m.Add(b[e] <= top)
        m.Add(a[e] >= bottom)
        terms.append(max(1, round(ln / 5)) * W2 * (b[e] - a[e]))
        g = GROUND + max(-K, min(K, lv))
        for var in (a[e], b[e]):
            d = m.NewIntVar(0, HI - LO, "")
            m.AddAbsEquality(d, var - g)
            terms.append(W3 * d)
    terms.append(5 * (top - bottom))                      # few levels in all
    if init:                                              # the heuristic's node levels: the starting hint only
        for e, (s, t, *_) in edges.items():
            lo, hi = sorted((init.get(s, 0), init.get(t, 0)))
            m.AddHint(a[e], max(LO, min(HI, GROUND + lo)))
            m.AddHint(b[e], max(LO, min(HI, GROUND + hi)))
        gone = set(init_dropped)
        for q, pr in zip(v, pairs):
            m.AddHint(q, 1 if pr in gone else 0)
    m.Minimize(sum(terms))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = workers
    status = sv.Solve(m)
    info = {"status": sv.StatusName(status), "objective": sv.ObjectiveValue(), "bound": sv.BestObjectiveBound(),
            "seconds": round(sv.WallTime(), 1), "join_pairs": len(joins),
            "same_given_up": sum(sv.Value(q) for q, _ in vs)}
    out = {e: (sv.Value(a[e]) - GROUND, sv.Value(b[e]) - GROUND) for e in edges}
    return out, [pairs[i] for i, q in enumerate(v) if sv.Value(q)], info


def interval_stats(edges, out, violated, pairs, info):
    span = defaultdict(int)
    levels = set()
    for a_, b_ in out.values():
        span[b_ - a_] += 1
        levels.update((a_, b_))
    print(f"intervals: pairs {len(pairs)}, given up {len(violated)}; solver {info}")
    print(f"distinct level numbers used: {len(levels)} (range {min(levels)} .. {max(levels)})")
    print("edges by interval length (b - a):", dict(sorted(span.items())))


def run_intervals(db, near=False, with_same=True, time_limit=120.0):
    import node_levels as nl
    edges, pairs = load(db, near)
    same = load_same(db) if with_same else []
    p0, left0, dropped0 = nl.solve({e: v[:3] for e, v in edges.items()}, pairs)
    out, violated, info = solve_intervals(edges, pairs, same, time_limit, init=p0, init_dropped=dropped0 + left0)
    interval_stats(edges, out, violated, pairs, info)
    return edges, pairs, out, violated


if __name__ == "__main__" and "--intervals" in sys.argv and "--pure" not in sys.argv and "--compact" not in sys.argv and "--all" not in sys.argv and "--links" not in sys.argv:
    tl = float(sys.argv[sys.argv.index("--time") + 1]) if "--time" in sys.argv else 120.0
    run_intervals(sys.argv[1], near="--near" in sys.argv, with_same="--same" in sys.argv, time_limit=tl)


# ---------------------------------------------------------------------------------------------------------------
# Kaveh's model, nothing else (2026-10-02): "the only constraints are the range of the intervals and that the intervals
# intersect for all edges that share a node; the penalty is only on overpasses."
#   variables   a_e <= b_e in [LO, HI]  for every edge;  v_q in {0, 1} for every overpass pair
#   constraints edges sharing a node: a_x <= b_y and a_y <= b_x
#               overpass (U over L), unless v_q = 1:  b_L + 1 <= a_U
#   objective   minimise  sum_q v_q
# ---------------------------------------------------------------------------------------------------------------
def solve_pure(edges, pairs, time_limit=120.0, workers=8, init=None, init_dropped=()):
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    a = {e: m.NewIntVar(LO, HI, "") for e in edges}
    b = {e: m.NewIntVar(LO, HI, "") for e in edges}
    for e in edges:
        m.Add(a[e] <= b[e])
    joins = join_pairs(edges)
    for x, y in joins:
        m.Add(a[x] <= b[y])
        m.Add(a[y] <= b[x])
    v = []
    for i, (u, l) in enumerate(pairs):
        q = m.NewBoolVar(f"v{i}")
        v.append(q)
        m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q.Not())
    if init:
        for e, (s, t, *_) in edges.items():
            lo, hi = sorted((init.get(s, 0), init.get(t, 0)))
            m.AddHint(a[e], max(LO, min(HI, lo)))
            m.AddHint(b[e], max(LO, min(HI, hi)))
        gone = set(init_dropped)
        for q, pr in zip(v, pairs):
            m.AddHint(q, 1 if pr in gone else 0)
    m.Minimize(sum(v))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = workers
    status = sv.Solve(m)
    info = {"status": sv.StatusName(status), "objective": sv.ObjectiveValue(), "bound": sv.BestObjectiveBound(),
            "seconds": round(sv.WallTime(), 1), "join_pairs": len(joins)}
    return ({e: (sv.Value(a[e]), sv.Value(b[e])) for e in edges}, [pairs[i] for i, q in enumerate(v) if sv.Value(q)], info)


def run_pure(db, time_limit=120.0):
    import node_levels as nl
    edges, pairs = load(db)
    p0, left0, dropped0 = nl.solve({e: v[:3] for e, v in edges.items()}, pairs)
    out, violated, info = solve_pure(edges, pairs, time_limit, init=p0, init_dropped=dropped0 + left0)
    interval_stats(edges, out, violated, pairs, info)
    return edges, pairs, out, violated


if __name__ == "__main__" and "--pure" in sys.argv and "--compact" not in sys.argv and "--all" not in sys.argv and "--links" not in sys.argv:
    tl = float(sys.argv[sys.argv.index("--time") + 1]) if "--time" in sys.argv else 120.0
    run_pure(sys.argv[1], tl)


def solve_pure_compact(edges, pairs, best, time_limit=120.0, workers=8, init=None):
    """Second stage, NOT part of Kaveh's model (asked about, not decided): keep sum v_q <= ``best`` (the optimum of the
    first stage) and, among those solutions, make the intervals as short as possible (sum of b_e - a_e)."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    a = {e: m.NewIntVar(LO, HI, "") for e in edges}
    b = {e: m.NewIntVar(LO, HI, "") for e in edges}
    for e in edges:
        m.Add(a[e] <= b[e])
    for x, y in join_pairs(edges):
        m.Add(a[x] <= b[y])
        m.Add(a[y] <= b[x])
    v = []
    for i, (u, l) in enumerate(pairs):
        q = m.NewBoolVar(f"v{i}")
        v.append(q)
        m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q.Not())
    m.Add(sum(v) <= best)
    m.Minimize(sum(b[e] - a[e] for e in edges))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = workers
    status = sv.Solve(m)
    info = {"status": sv.StatusName(status), "objective": sv.ObjectiveValue(), "bound": sv.BestObjectiveBound(),
            "seconds": round(sv.WallTime(), 1)}
    return ({e: (sv.Value(a[e]), sv.Value(b[e])) for e in edges}, [pairs[i] for i, q in enumerate(v) if sv.Value(q)], info)


def run_pure_compact(db, time_limit=120.0):
    edges, pairs = load(db)
    out, violated, info = solve_pure_compact(edges, pairs, 8, time_limit)
    interval_stats(edges, out, violated, pairs, info)
    return edges, pairs, out, violated


if __name__ == "__main__" and "--compact" in sys.argv and "--all" not in sys.argv and "--links" not in sys.argv:
    run_pure_compact(sys.argv[1], float(sys.argv[sys.argv.index("--time") + 1]) if "--time" in sys.argv else 120.0)


def solve_pure_all(edges, pairs, same, time_limit=120.0, workers=8, init=None, init_dropped=(), best=None):
    """Kaveh's model with ALL the pairs that must not intersect: the overpass pairs (higher tag later), and the crossings of
    the same tag (either edge first). Every such pair that intersects costs 1. With ``best``: a second stage that keeps
    the penalty <= best and makes the intervals as short as possible."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    a = {e: m.NewIntVar(LO, HI, "") for e in edges}
    b = {e: m.NewIntVar(LO, HI, "") for e in edges}
    for e in edges:
        m.Add(a[e] <= b[e])
    for x, y in join_pairs(edges):
        m.Add(a[x] <= b[y])
        m.Add(a[y] <= b[x])
    v = []
    for i, (u, l) in enumerate(pairs):
        q = m.NewBoolVar(f"v{i}")
        v.append(q)
        m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q.Not())
    for i, (x, y) in enumerate(same):
        q, o = m.NewBoolVar(f"w{i}"), m.NewBoolVar(f"o{i}")
        v.append(q)
        m.Add(b[y] + 1 <= a[x]).OnlyEnforceIf([q.Not(), o])
        m.Add(b[x] + 1 <= a[y]).OnlyEnforceIf([q.Not(), o.Not()])
    if best is None:
        if init:
            for e, (s, t, *_) in edges.items():
                lo, hi = sorted((init.get(s, 0), init.get(t, 0)))
                m.AddHint(a[e], max(LO, min(HI, lo)))
                m.AddHint(b[e], max(LO, min(HI, hi)))
        m.Minimize(sum(v))
    else:
        m.Add(sum(v) <= best)
        m.Minimize(sum(b[e] - a[e] for e in edges))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = workers
    status = sv.Solve(m)
    info = {"status": sv.StatusName(status), "objective": sv.ObjectiveValue(), "bound": sv.BestObjectiveBound(),
            "seconds": round(sv.WallTime(), 1)}
    allq = list(pairs) + [tuple(x) for x in same]
    info["violated"] = [allq[i] for i, q in enumerate(v) if sv.Value(q)] if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else []
    return ({e: (sv.Value(a[e]), sv.Value(b[e])) for e in edges}, int(round(sum(sv.Value(q) for q in v))), info)


def run_pure_all(db, time_limit=120.0):
    import node_levels as nl
    edges, pairs = load(db, near=True)
    same = load_same(db)
    p0, left0, dropped0 = nl.solve({e: v[:3] for e, v in edges.items()}, pairs)
    out, given, info = solve_pure_all(edges, pairs, same, time_limit, init=p0)
    print(f"stage 1: overpass/near pairs {len(pairs)}, same-level crossings {len(same)}, given up {given}; {info}")
    out2, given2, info2 = solve_pure_all(edges, pairs, same, time_limit, best=given)
    print(f"stage 2: given up {given2}; {info2}")
    levels = sorted({v for ab in out2.values() for v in ab})
    print(f"distinct numbers {len(levels)}; edges by length:", dict(sorted(__import__('collections').Counter(b_ - a_ for a_, b_ in out2.values()).items())))
    return edges, pairs, out2, given2


if __name__ == "__main__" and "--all" in sys.argv and "--links" not in sys.argv:
    run_pure_all(sys.argv[1], float(sys.argv[sys.argv.index("--time") + 1]) if "--time" in sys.argv else 120.0)


def link_map(db):
    """``{eid: road id}``: a road is a segment with both of its directions (Kaveh allowed one interval per road). The two directed edges of a two-way road
    have the same two end nodes and the same line (reversed); the link id is the smallest edge id of the group."""
    import duckdb

    import node_levels as nl
    from mapstyle.map import _roads_union
    con = duckdb.connect(str(db), read_only=True)
    try:
        nl.edge_table(con, _roads_union(con, db))
        rows = con.execute("""
            SELECT CAST(a.eid AS VARCHAR), CAST(min(o.eid) AS VARCHAR)
            FROM lv a JOIN lv o ON a.s IN (o.s, o.t) AND a.t IN (o.s, o.t) AND ST_Equals(a.g, o.g)
            GROUP BY a.eid""").fetchall()
    finally:
        con.close()
    return dict(rows)


def run_links(db, time_limit=60.0):
    import node_levels as nl
    edges, pairs = load(db, near=False)
    same = load_same(db)
    lk = link_map(db)
    links = {}
    for e, v in edges.items():
        links.setdefault(lk.get(e, e), v)
    lpairs = sorted({(lk.get(u, u), lk.get(l, l)) for u, l in pairs if lk.get(u, u) != lk.get(l, l)})
    lsame = sorted({tuple(sorted((lk.get(x, x), lk.get(y, y)))) for x, y in same if lk.get(x, x) != lk.get(y, y)})
    print(f"directed edges {len(edges)} -> links {len(links)}; overpass pairs {len(pairs)} -> {len(lpairs)}; "
          f"same-level crossings {len(same)} -> {len(lsame)}", flush=True)
    p0, left0, dropped0 = nl.solve({e: v[:3] for e, v in links.items()}, lpairs)
    out, given, info = solve_pure_all(links, lpairs, lsame, time_limit, init=p0)
    print("link level: given up", given, info)
    return edges, links, lk, out, given


if __name__ == "__main__" and "--links" in sys.argv:
    run_links(sys.argv[1])
