"""The order in which each road's casing and fill are drawn (docs/design/node_levels.md).

Every road (both directions of a segment together) gets an interval ``[a, b]`` of integers: ``a`` is the position in the
drawing order where its casing is drawn and ``b`` where its fill is drawn; at each position all casings come before all fills.

* roads that share a node have intersecting intervals (so they merge cleanly);
* an overpass (two roads whose lines cross, no node in common, different level tags) has disjoint intervals, the upper one
  later, so the upper road is drawn over the lower one with its own casing; an overpass that cannot be satisfied is given up.

Found with OR-Tools CP-SAT (``pip install mapstyle[solver]``); without it a heuristic is used. Only the roads within a few hops
of an overpass are in the problem; every other road is at position 0 (``[0, 0]``).

Two conflict-driven fixes, applied only where a conflict is left (docs/design/node_levels.md): a pair whose crossing is within
``EPS_NODE_M`` of an end node of either road is not an overpass; otherwise the road that changes level along itself is cut
at its crossing.
"""
import logging
from collections import defaultdict

log = logging.getLogger(__name__)

LO, HI = -20, 20          # the ends of an interval are integers in [LO, HI]
EPS_NODE_M = 0.3          # a crossing this close to an end node of either road is a junction missing a node, not an overpass
HOPS = 4                  # roads this many nodes away from an overpass road are in the problem; the others are [0, 0]
M_PER_DEG = 95000.0       # rough: only used to compare distances along one road


def have_solver():
    try:
        import ortools  # noqa: F401
        return True
    except ImportError:
        return False


# ---- the data -------------------------------------------------------------------------------------------------------
def load(con, union):
    """``(roads, lk, pairs)``. ``roads``: ``{road id: (s, t, level, length_m)}``, a road being the directed edges with the same
    two end nodes and the same line; ``lk``: ``{edge id: road id}`` for the edges of a road with more than one; ``pairs``: the
    overpass pairs ``(upper, lower)`` as road ids. ``con`` has the spatial extension loaded."""
    t = lambda c: f"({c} IS NOT NULL AND lower(CAST({c} AS VARCHAR)) NOT IN ('', 'no', 'false', '0'))"  # noqa: E731
    o = "ORDER BY mode IS NULL, mode, pmode"
    con.execute(f"""CREATE TEMP TABLE nl_e0 AS SELECT edge_id AS eid, first(source {o}) AS s, first(target {o}) AS t,
        first(layer {o}) AS layer, first(bridge {o}) AS bridge, first(tunnel {o}) AS tunnel, first(geometry {o}) AS g
        FROM ({union}) GROUP BY edge_id""")
    con.execute(f"""CREATE TEMP TABLE nl_lv AS SELECT eid, s, t, g,
        COALESCE(NULLIF(TRY_CAST(layer AS INTEGER), 0), CASE WHEN {t('bridge')} THEN 1 WHEN {t('tunnel')} THEN -1 ELSE 0 END) AS l
        FROM nl_e0""")
    # candidate pairs through a grid (a spatial join over a whole county takes minutes), then the exact test
    cs = 0.001
    con.execute(f"""CREATE TEMP TABLE nl_bb AS SELECT eid, l, CAST(floor(ST_XMin(g)/{cs}) AS BIGINT) cx0, CAST(floor(ST_XMax(g)/{cs}) AS BIGINT) cx1,
        CAST(floor(ST_YMin(g)/{cs}) AS BIGINT) cy0, CAST(floor(ST_YMax(g)/{cs}) AS BIGINT) cy1 FROM nl_lv""")
    con.execute("CREATE TEMP TABLE nl_cx AS SELECT eid, l, unnest(range(cx0, cx1 + 1)) i, cy0, cy1 FROM nl_bb")
    con.execute("CREATE TEMP TABLE nl_cells AS SELECT eid, l, i, unnest(range(cy0, cy1 + 1)) j FROM nl_cx")
    con.execute("""CREATE TEMP TABLE nl_cand AS SELECT DISTINCT a.eid ea, o.eid eo FROM nl_cells a JOIN nl_cells o
        ON a.i = o.i AND a.j = o.j AND a.eid <> o.eid AND a.l <> 0 AND a.l <> o.l AND (o.l = 0 OR a.eid < o.eid)""")
    raw = con.execute("""SELECT CASE WHEN a.l > o.l THEN a.eid ELSE o.eid END, CASE WHEN a.l > o.l THEN o.eid ELSE a.eid END
        FROM nl_cand c JOIN nl_lv a ON a.eid = c.ea JOIN nl_lv o ON o.eid = c.eo
        WHERE a.s NOT IN (o.s, o.t) AND a.t NOT IN (o.s, o.t) AND ST_Crosses(a.g, o.g)""").fetchall()
    # roads: the two directions of a segment (same end nodes, same line reversed); the road id is the smallest edge id
    grp = con.execute("""SELECT a.eid, min(o.eid) FROM nl_lv a JOIN nl_lv o ON least(a.s, a.t) = least(o.s, o.t)
        AND greatest(a.s, a.t) = greatest(o.s, o.t) AND ST_Equals(a.g, o.g) GROUP BY a.eid""").fetchall()
    lk = {str(a): str(b) for a, b in grp if a != b}
    need = {str(x) for pr in raw for x in pr}
    need |= {lk.get(x, x) for x in need}
    roads = {}
    ids = ", ".join(sorted(need)) or "0"
    for e, s, t_, l, ln in con.execute(f"SELECT eid, s, t, l, ST_Length(g) FROM nl_lv WHERE eid IN ({ids})").fetchall():
        roads[str(e)] = (s, t_, int(l), ln * M_PER_DEG)
    pairs = sorted({(lk.get(str(u), str(u)), lk.get(str(l), str(l))) for u, l in raw} - {(x, x) for x in roads})
    return roads, lk, pairs


def _neighbourhood(con, seeds, hops, lk):
    """Roads (as representative edge ids) within ``hops`` nodes of the roads ``seeds``: ``{road: (s, t, level, length_m)}``."""
    rows = {}
    frontier = set()
    for e in seeds:
        r = con.execute(f"SELECT eid, s, t, l, ST_Length(g) FROM nl_lv WHERE eid = {e}").fetchone()
        rows[str(r[0])] = (r[1], r[2], int(r[3]), r[4] * M_PER_DEG)
        frontier |= {r[1], r[2]}
    seen = set(frontier)
    for _ in range(hops):
        if not frontier:
            break
        ns = ", ".join(str(n) for n in frontier)
        new = set()
        for e, s, t, l, ln in con.execute(f"SELECT eid, s, t, l, ST_Length(g) FROM nl_lv WHERE s IN ({ns}) OR t IN ({ns})").fetchall():
            if str(e) not in lk:                    # the other direction of a road is not a road of its own
                rows[str(e)] = (s, t, int(l), ln * M_PER_DEG)
            new |= {s, t}
        frontier = new - seen
        seen |= new
    return rows


def join_pairs(items):
    at = defaultdict(list)
    for e, (s, t, *_) in items.items():
        at[s].append(e)
        if t != s:
            at[t].append(e)
    out = set()
    for es in at.values():
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                out.add((es[i], es[j]) if es[i] < es[j] else (es[j], es[i]))
    return sorted(out)


# ---- the models -----------------------------------------------------------------------------------------------------
def _model(items, pairs, fixed, lits=False):
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    a = {e: m.NewIntVar(LO, HI, "") for e in items}
    b = {e: m.NewIntVar(LO, HI, "") for e in items}
    for e in items:
        m.Add(a[e] <= b[e])
    for e, (lo, hi) in fixed.items():
        m.Add(a[e] == lo)
        m.Add(b[e] == hi)
    for x, y in join_pairs(items):
        m.Add(a[x] <= b[y])
        m.Add(a[y] <= b[x])
    return m, a, b


def _solve(m, limit, workers=8):
    from ortools.sat.python import cp_model
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = limit
    sv.parameters.num_workers = workers
    return sv, sv.Solve(m), cp_model


def solve_penalty(items, pairs, boundary, limit=60.0, hint=None):
    """Minimise the number of overpass pairs given up. ``boundary``: roads that touch a road outside the problem must contain 0.
    Returns ``({road: (a, b)}, [pairs given up], status)``."""
    m, a, b = _model(items, pairs, {})
    for e in boundary:
        m.Add(a[e] <= 0)
        m.Add(b[e] >= 0)
    v = []
    for i, (u, l) in enumerate(pairs):
        q = m.NewBoolVar("")
        v.append(q)
        m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q.Not())
    if hint:
        for e, (lo, hi) in hint.items():
            m.AddHint(a[e], max(LO, min(HI, lo)))
            m.AddHint(b[e], max(LO, min(HI, hi)))
    m.Minimize(sum(v))
    sv, st, cp = _solve(m, limit)
    if st not in (cp.OPTIMAL, cp.FEASIBLE):
        return None, [], sv.StatusName(st)
    out = {e: (sv.Value(a[e]), sv.Value(b[e])) for e in items}
    return out, [pairs[i] for i, q in enumerate(v) if sv.Value(q)], sv.StatusName(st)


def solve_hard(items, pairs, boundary, limit=60.0, rounds=20):
    """The overpass pairs as hard constraints. Infeasible: the conflicting sets of pairs (unsatisfiable cores, through assumptions),
    one pair released per round until it is feasible. Returns ``(status of the first solve, [cores], [released pairs])``."""
    released, cores, first = [], [], None
    for _ in range(rounds):
        m, a, b = _model(items, pairs, {})
        for e in boundary:
            m.Add(a[e] <= 0)
            m.Add(b[e] >= 0)
        lits, names = [], []
        gone = set(released)
        for u, l in pairs:
            if (u, l) in gone:
                continue
            q = m.NewBoolVar("")
            m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q)
            lits.append(q)
            names.append((u, l))
        m.AddAssumptions(lits)
        sv, st, cp = _solve(m, limit)
        first = first or sv.StatusName(st)
        if st in (cp.OPTIMAL, cp.FEASIBLE):
            return first, cores, released
        idx = {lit.Index(): i for i, lit in enumerate(lits)}
        core = [names[idx[c]] for c in sv.SufficientAssumptionsForInfeasibility() if c in idx]
        if not core:
            return first, cores, released
        cores.append(core)
        released.append(core[0])
    return first, cores, released


def solve_fixed(items, pairs, fixed, boundary, limit=60.0):
    """A feasible assignment, hard pairs; roads in ``fixed`` keep their interval; the others as short as possible."""
    m, a, b = _model(items, pairs, fixed)
    for e in boundary:
        m.Add(a[e] <= 0)
        m.Add(b[e] >= 0)
    for u, l in pairs:
        m.Add(b[l] + 1 <= a[u])
    m.Minimize(sum(b[e] - a[e] for e in items if e not in fixed))
    sv, st, cp = _solve(m, limit)
    if st not in (cp.OPTIMAL, cp.FEASIBLE):
        return None
    return {e: (sv.Value(a[e]), sv.Value(b[e])) for e in items}


def compact(items, pairs, boundary, given_up, limit=60.0):
    """Keep at most ``given_up`` overpasses given up and make the intervals as short as possible (fewer distinct numbers)."""
    m, a, b = _model(items, pairs, {})
    for e in boundary:
        m.Add(a[e] <= 0)
        m.Add(b[e] >= 0)
    v = []
    for u, l in pairs:
        q = m.NewBoolVar("")
        v.append(q)
        m.Add(b[l] + 1 <= a[u]).OnlyEnforceIf(q.Not())
    m.Add(sum(v) <= given_up)
    m.Minimize(sum(b[e] - a[e] for e in items))
    sv, st, cp = _solve(m, limit)
    if st not in (cp.OPTIMAL, cp.FEASIBLE):
        return None, []
    return ({e: (sv.Value(a[e]), sv.Value(b[e])) for e in items}, [pairs[i] for i, q in enumerate(v) if sv.Value(q)])


def heuristic(items, pairs):
    """Without a solver: a level for each node (all start at 0; a raised road is lifted, any other road sunk, until every pair that
    is not in a cycle is satisfied); a road's interval is the lowest to the highest level of its two nodes."""
    sccs = _scc(pairs, items)
    keep = [(u, l) for u, l in pairs if not any(sccs.get(nl) == sccs.get(nu) for nu in items[u][:2] for nl in items[l][:2])]
    p = defaultdict(int)
    for _ in range(100):
        moved = False
        for u, l in keep:
            for nu in items[u][:2]:
                for nl in items[l][:2]:
                    if p[nu] > p[nl]:
                        continue
                    if items[u][2] > 0:
                        p[nu] = p[nl] + 1
                    else:
                        p[nl] = p[nu] - 1
                    moved = True
        if not moved:
            break
    out = {e: (max(LO, min(HI, min(p[s], p[t]))), max(LO, min(HI, max(p[s], p[t])))) for e, (s, t, *_ ) in items.items()}
    return out, [pr for pr in pairs if pr not in set(keep)]


def _scc(pairs, items):
    g = defaultdict(list)
    for u, l in pairs:
        for nu in items[u][:2]:
            for nl in items[l][:2]:
                g[nl].append(nu)
    nodes = set(g) | {x for vs in g.values() for x in vs}
    index, low, on, stack, comp, c = {}, {}, set(), [], {}, [0]
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(g.get(root, ())))]
        index[root] = low[root] = len(index)
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = len(index)
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(g.get(w, ()))))
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp[w] = c[0]
                        if w == v:
                            break
                    c[0] += 1
    return comp


# ---- the whole computation ------------------------------------------------------------------------------------------
class Levels:
    """``intervals``: ``{edge_id: (casing, fill)}`` for every directed edge that is not ``(0, 0)`` (anything missing is ``(0, 0)``);
    ``cuts``: ``{road id: {"bounds": [m...], "intervals": [(casing, fill)...], "edges": [edge ids]}}``, the roads to draw in pieces
    (piece i runs from ``bounds[i]`` to ``bounds[i + 1]`` metres along the road's line); ``info``: counts and timing."""

    def __init__(self, intervals, cuts, info):
        self.intervals, self.cuts, self.info = intervals, cuts, info


def _near_node(geom, u, l, eps=EPS_NODE_M):
    from shapely.geometry import Point
    x = geom[u].intersection(geom[l])
    pts = [] if x.is_empty else (list(x.geoms) if hasattr(x, "geoms") else [x])
    return any(min(Point(g.coords[0]).distance(q), Point(g.coords[-1]).distance(q)) * M_PER_DEG < eps
               for g in (geom[u], geom[l]) for q in pts)


def _cut_positions(line, uppers, geom, clear=6.0):
    """Where to cut ``line`` so that one piece (the one crossing the upper roads) is separate from the node ends: just before the
    first crossing and just after the last, never into a node and never past a crossing, as far as ``clear`` metres."""
    ts = []
    for u in uppers:
        x = line.intersection(geom[u])
        pts = [] if x.is_empty else (list(x.geoms) if hasattr(x, "geoms") else [x])
        ts += [line.project(q) * M_PER_DEG for q in pts]
    length = line.length * M_PER_DEG
    cuts = []
    if ts:
        t_min, t_max = min(ts), max(ts)
        if t_min - 0.3 > 0.3:
            cuts.append(t_min - min(clear, t_min - 0.3))
        if length - t_max - 0.3 > 0.3:
            cuts.append(t_max + min(clear, length - t_max - 0.3))
    return cuts, length


def _compress(values):
    """Order-preserving integers: negative values to -1, -2 ..., positive to 1, 2 ..., zero stays zero."""
    vs = sorted(set(values) | {0})
    neg = [v for v in vs if v < 0]
    pos = [v for v in vs if v > 0]
    m = {0: 0}
    m.update({v: -(len(neg) - i) for i, v in enumerate(neg)})
    m.update({v: i + 1 for i, v in enumerate(pos)})
    return m


def compute(db, hops=HOPS, limit=60.0, solver=None):
    """The drawing order of the roads of the duckOSM db ``db``: a ``Levels``. ``solver``: use OR-Tools (default: if it is installed)."""
    import time

    import duckdb
    from shapely import wkb
    from shapely.ops import substring

    from mapstyle.map import _roads_union
    t0 = time.time()
    use = have_solver() if solver is None else solver
    con = duckdb.connect(str(db), read_only=True)
    try:
        union = _roads_union(con, db)
        roads, lk, pairs = load(con, union)
        info = {"overpass_pairs": len(pairs), "solver": use, "given_up": 0, "dropped": 0, "cut": 0}
        if not pairs:
            info["seconds"] = round(time.time() - t0, 1)
            return Levels({}, {}, info)
        seeds = {x for pr in pairs for x in pr}
        items = _neighbourhood(con, seeds, hops, lk)
        items.update({r: roads[r] for r in seeds if r in roads})
        # roads at the edge of the problem touch roads outside it (at 0): they must contain 0
        nodes = {n for s, t, *_ in items.values() for n in (s, t)}
        ns = ", ".join(str(n) for n in nodes)
        outside = set()
        for e, s, t in con.execute(f"SELECT eid, s, t FROM nl_lv WHERE s IN ({ns}) OR t IN ({ns})").fetchall():
            if str(e) not in items and str(e) not in lk:
                outside |= {s, t}
        boundary = [r for r, (s, t, *_ ) in items.items() if s in outside or t in outside]
        info.update(roads_in_problem=len(items), boundary=len(boundary))
        base_h, dropped_h = heuristic(items, pairs)
        if not use:
            iv, given = base_h, dropped_h
            info["given_up"] = len(given)
            res, cuts, dropped = iv, {}, []
        else:
            out0, given, status = solve_penalty(items, pairs, boundary, limit, hint=base_h)
            if out0 is None:
                raise RuntimeError(f"node levels: the solver returned {status}")
            info["status"] = status
            base, _ = compact(items, pairs, boundary, len(given), limit)
            base = base or out0
            res, cuts, dropped = base, {}, []
            if given:
                res, cuts, dropped, pairs = _fix_conflicts(con, items, pairs, boundary, base, limit, wkb, substring)
            info["given_up"] = len(given)
            info["dropped"], info["cut"] = len(dropped), len(cuts)
    finally:
        con.close()
    # numbers: order-preserving, small
    vals = [v for ab in res.values() for v in ab] + [v for c in cuts.values() for ab in c["intervals"] for v in ab]
    cm = _compress(vals)
    members = defaultdict(list)
    for e, r in lk.items():
        members[r].append(e)
    intervals = {}
    for r, (a, b) in res.items():
        a, b = cm[a], cm[b]
        if r in cuts or (a, b) == (0, 0):
            continue
        for e in [r] + members.get(r, []):
            intervals[e] = (a, b)
    for r, c in cuts.items():
        c["intervals"] = [(cm[a], cm[b]) for a, b in c["intervals"]]
        c["edges"] = [r] + members.get(r, [])
    info["levels"] = len({v for ab in intervals.values() for v in ab} | {v for c in cuts.values() for ab in c["intervals"] for v in ab})
    info["seconds"] = round(time.time() - t0, 1)
    log.info("node levels: %s", info)
    return Levels(intervals, cuts, info)


def _fix_conflicts(con, items, pairs, boundary, base, limit, wkb, substring):
    """The conflicts that are left (docs/design/node_levels.md): drop a pair whose crossing is next to an end node; otherwise cut the
    road that changes level along itself. Every road outside the conflicts keeps its interval in ``base``."""
    ids = ", ".join(sorted({x for pr in pairs for x in pr}))
    geom = {str(e): wkb.loads(bytes(g)) for e, g in con.execute(f"SELECT eid, ST_AsWKB(g) FROM nl_lv WHERE eid IN ({ids})").fetchall()}
    items, pairs = dict(items), list(pairs)
    dropped, cut, affected, new_node = [], {}, set(), [-1]
    for rnd in range(5):
        status, cores, released = solve_hard(items, pairs, boundary, limit)
        if not cores:
            break
        todo = {}
        for core in cores:
            affected |= {x.split("#")[0] for pr in core for x in pr}
            near = [pr for pr in core if _near_node(geom, *pr)]
            if near:
                for pr in near:
                    if pr in pairs:
                        pairs.remove(pr)
                        dropped.append(pr)
                continue
            lowers = {}
            for u, l in core:
                lowers.setdefault(l, []).append(u)

            def vertical(e):
                ns = set(items[e][:2])
                return any(abs(items[o][2] - items[e][2]) >= 2 for o in items if o != e and ns & set(items[o][:2]))
            l = ([x for x in lowers if vertical(x)] or list(lowers))[0]
            todo.setdefault(l, [])
            todo[l] += [u for u in lowers[l] if u not in todo[l]]
        for l, ups in todo.items():
            root = l.split("#")[0]
            if root in cut:
                continue
            cuts_m, length = _cut_positions(geom[l], ups, geom)
            if not cuts_m:
                continue
            s_, t_, lv, ln = items[l]
            nodes = [s_] + [new_node.append(new_node[-1] - 1) or new_node[-1] for _ in cuts_m] + [t_]
            bounds = [0.0] + cuts_m + [length]
            names = []
            for i in range(len(bounds) - 1):
                pid = f"{l}#{i}"
                geom[pid] = substring(geom[l], bounds[i] / M_PER_DEG, bounds[i + 1] / M_PER_DEG)
                items[pid] = (nodes[i], nodes[i + 1], lv, bounds[i + 1] - bounds[i])
                names.append(pid)
            del items[l]
            newp = []
            for u2, x2 in pairs:
                if x2 == l:
                    newp += [(u2, pid) for pid in names if geom[u2].crosses(geom[pid])]
                elif u2 == l:
                    newp += [(pid, x2) for pid in names if geom[x2].crosses(geom[pid])]
                else:
                    newp.append((u2, x2))
            pairs = sorted(set(newp))
            cut[l] = {"bounds": bounds, "pieces": names}
    free = set(affected) | {p for c in cut.values() for p in c["pieces"]}
    for r in list(free):
        ns = set(items[r][:2]) if r in items else set()
        free |= {o for o in items if ns & set(items[o][:2])}
    fixed = {e: base[e] for e in items if e not in free and e in base}
    final = solve_fixed(items, pairs, fixed, boundary, limit) or solve_fixed(items, pairs, {}, boundary, limit)
    if final is None:
        raise RuntimeError("node levels: no feasible drawing order after the conflict fixes")
    cuts_out = {r: {"bounds": c["bounds"], "intervals": [final[p] for p in c["pieces"]]} for r, c in cut.items()}
    res = {e: iv for e, iv in final.items() if "#" not in e}
    return res, cuts_out, dropped, pairs
