"""PROTOTYPE: Approach B (one interval per road, hard overpass constraints) with fixes for the failing conflicts ONLY
(docs/design/node_levels.md, "A way to solve all 3 failures"): a pair of a conflict whose crossing is within EPS of an end node is
dropped; otherwise the edge that changes level along itself is cut at its crossing. Every road outside the conflicts keeps the
interval of the baseline solution.

    NL_RANGE=20 PYTHONPATH=<ortools dir> python scripts/node_levels_final.py DB OUT_DIR
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import node_levels_opt as no  # noqa: E402

EPS = float(os.environ.get("NL_EPS", "0.3"))
DEG = 95000.0


def prepare(db):
    import duckdb
    from shapely import wkb

    import node_levels as nl
    from mapstyle.map import _roads_union
    edges, pairs = no.load(db)
    lk = no.link_map(db)
    roads = {r: edges[r] for r in set(lk.values()) if r in edges}
    rp = sorted({(lk.get(u, u), lk.get(l, l)) for u, l in pairs if lk.get(u, u) != lk.get(l, l)})
    con = duckdb.connect(str(db), read_only=True)
    nl.edge_table(con, _roads_union(con, db))
    geom = {str(e): wkb.loads(bytes(g)) for e, g in con.execute("SELECT eid, ST_AsWKB(g) FROM lv").fetchall()}
    hw = {str(e): h for e, h in con.execute("SELECT edge_id, first(highway) FROM (" + _roads_union(con, db) + ") GROUP BY edge_id").fetchall()}
    con.close()
    return edges, lk, roads, rp, geom, hw


def near_node(geom, u, l):
    from shapely.geometry import Point
    x = geom[u].intersection(geom[l])
    pts = [] if x.is_empty else (list(x.geoms) if hasattr(x, "geoms") else [x])
    return any(min(Point(g.coords[0]).distance(q), Point(g.coords[-1]).distance(q)) * DEG < EPS for g in (geom[u], geom[l]) for q in pts)


def solve_fixed(items, pairs, fixed, time_limit=60.0):
    """Feasibility with hard constraints; the roads in ``fixed`` ({road: (a, b)}) keep their intervals."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    a = {e: m.NewIntVar(no.LO, no.HI, "") for e in items}
    b = {e: m.NewIntVar(no.LO, no.HI, "") for e in items}
    for e in items:
        m.Add(a[e] <= b[e])
        if e in fixed:
            m.Add(a[e] == fixed[e][0])
            m.Add(b[e] == fixed[e][1])
    for x, y in no.join_pairs(items):
        m.Add(a[x] <= b[y])
        m.Add(a[y] <= b[x])
    for u, l in pairs:
        m.Add(b[l] + 1 <= a[u])
    m.Minimize(sum(b[e] - a[e] for e in items if e not in fixed))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = 8
    st = sv.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return sv.StatusName(st), None
    return sv.StatusName(st), {e: (sv.Value(a[e]), sv.Value(b[e])) for e in items}


def fix(db):
    from shapely.ops import substring

    import node_levels as nl
    from mapstyle.levels import HALF_WIDTH_M  # noqa: F401
    edges, lk, roads, rp, geom, hw = prepare(db)
    # the baseline: the solution with penalties (3 pairs given up), as before
    p0, _, d0 = nl.solve({e: v[:3] for e, v in roads.items()}, rp)
    base, given, info = no.solve_pure_all(roads, rp, [], 60, init=p0)
    print(f"baseline: {given} given up ({info['status']}); {len(rp)} pairs", flush=True)
    items, pairs = dict(roads), list(rp)
    g = {r: geom[r] for r in roads}
    dropped, cut, affected, new_node = [], {}, set(), [-1]
    for rnd in range(5):
        status, cores, released, out = no.solve_hard(items, pairs, [], 60)
        if out is not None and not released:
            break
        print(f"round {rnd}: {status[0]}, conflicts {len(cores)}", flush=True)
        todo = {}
        for core in cores:
            members = {x for _, u, l in core for x in (u, l)}
            affected |= {m.split("#")[0] for m in members}
            near = [(u, l) for _, u, l in core if near_node(g, u, l)]
            if near:
                for pr in near:
                    if pr in pairs:
                        pairs.remove(pr)
                        dropped.append(pr)
                print(f"   dropped {len(near)} pair(s) of a conflict, crossing within {EPS} m of an end node", flush=True)
                continue
            lowers = {}
            for _, u, l in core:
                lowers.setdefault(l, []).append(u)

            def vertical(e):
                ns = set(items[e][:2])
                return any(abs(items[o][2] - items[e][2]) >= 2 for o in items if o != e and ns & set(items[o][:2]))
            l = ([x for x in lowers if vertical(x)] or list(lowers))[0]
            todo.setdefault(l, [])
            todo[l] += [u for u in lowers[l] if u not in todo[l]]
        for l, ups in todo.items():
            if l.split("#")[0] in cut:
                continue
            s_, t_, lv, ln = items[l]
            line = g[l]
            ts = []
            for u in ups:
                near_x = line.intersection(g[u])
                pts = [] if near_x.is_empty else (list(near_x.geoms) if hasattr(near_x, "geoms") else [near_x])
                ts += [line.project(q) * DEG for q in pts]
            length = line.length * DEG
            t_min, t_max = min(ts), max(ts)
            cuts = []
            if t_min - 0.3 > 0.3:
                cuts.append(t_min - min(6.0, t_min - 0.3))
            if length - t_max - 0.3 > 0.3:
                cuts.append(t_max + min(6.0, length - t_max - 0.3))
            if not cuts:
                continue
            nodes = [s_] + [new_node.append(new_node[-1] - 1) or new_node[-1] for _ in cuts] + [t_]
            bounds = [0.0] + cuts + [length]
            names = []
            for i in range(len(bounds) - 1):
                pid = f"{l}#{i}"
                g[pid] = substring(line, bounds[i] / DEG, bounds[i + 1] / DEG)
                items[pid] = (nodes[i], nodes[i + 1], lv, bounds[i + 1] - bounds[i])
                names.append(pid)
            del items[l]
            newp = []
            for u2, x2 in pairs:
                if x2 == l:
                    newp += [(u2, pid) for pid in names if g[u2].crosses(g[pid])]
                elif u2 == l:
                    newp += [(pid, x2) for pid in names if g[x2].crosses(g[pid])]
                else:
                    newp.append((u2, x2))
            pairs = sorted(set(newp))
            cut[l] = {"bounds": bounds, "pieces": names}
            print(f"   cut road {l[-8:]} ({hw.get(l)}) into {len(names)} pieces at {[round(c, 1) for c in cuts]} m", flush=True)
    # final solve: everything outside the conflicts (plus their neighbours) keeps its baseline interval
    free = set()
    for r in affected | set(cut):
        free.add(r)
        for o in items:
            if set(items[o][:2]) & set(items.get(r, items.get(f"{r}#0", (0, 0)))[:2]):
                free.add(o)
    for r, c in cut.items():
        free |= set(c["pieces"])
    fixed = {e: base[e] for e in items if e not in free and e in base}
    status, final = solve_fixed(items, pairs, fixed)
    print(f"final: {status}; free roads {len(free)}, fixed roads {len(fixed)}, dropped pairs {len(dropped)}, cut roads {len(cut)}", flush=True)
    if final is None:                                   # widen: let everything vary
        status, final = solve_fixed(items, pairs, {})
        print("final with everything free:", status, flush=True)
    changed = [e for e in base if e in final and base[e] != final[e]]
    print(f"roads whose interval changed against the baseline: {len(changed)} (of {len(base)}), {len(cut)} cut", flush=True)
    return dict(edges=edges, lk=lk, roads=roads, items=items, base=base, final=final, cut=cut, dropped=dropped, free=sorted(free), geom=geom)


if __name__ == "__main__":
    r = fix(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(exist_ok=True)
    json.dump({"dropped": r["dropped"], "cut": r["cut"], "free": r["free"]}, open(out / "fix.json", "w"), indent=1)
