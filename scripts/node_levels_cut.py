"""PROTOTYPE of "Approach B plus cutting" (docs/design/node_levels.md): solve the interval model with the overpass pairs as hard
constraints; for every conflict, cut the LOWER road of a pair that has to be released into pieces at its crossing with the upper
road, and solve again, until it is feasible.

    NL_RANGE=20 PYTHONPATH=<ortools dir> python scripts/node_levels_cut.py DB
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import node_levels_opt as no  # noqa: E402


def run(db, rounds=6):
    import duckdb
    from shapely import wkb
    from shapely.ops import substring

    import node_levels as nl
    from mapstyle.levels import CLEARANCE_M, HALF_WIDTH_M
    from mapstyle.map import _roads_union

    edges, pairs = no.load(db)
    lk = no.link_map(db)
    roads = {r: edges[r] for r in set(lk.values()) if r in edges}      # the edge whose id names the road: nodes and line agree
    rp = sorted({(lk.get(u, u), lk.get(l, l)) for u, l in pairs if lk.get(u, u) != lk.get(l, l)})
    con = duckdb.connect(str(db), read_only=True)
    nl.edge_table(con, _roads_union(con, db))
    geom = {str(e): wkb.loads(bytes(g)) for e, g in con.execute("SELECT eid, ST_AsWKB(g) FROM lv").fetchall()}
    hw = {str(e): h for e, h in con.execute("SELECT edge_id, first(highway) FROM (" + _roads_union(con, db) + ") GROUP BY edge_id").fetchall()}
    con.close()
    import os
    from shapely.geometry import Point
    eps = float(os.environ.get("NL_EPS", "0.3"))        # a crossing this close (m) to an end node of either road is a junction missing a node, not an overpass
    def near_node(u, l):
        x = geom[u].intersection(geom[l])
        pts = [] if x.is_empty else (list(x.geoms) if hasattr(x, "geoms") else [x])
        return any(min(Point(gg.coords[0]).distance(q), Point(gg.coords[-1]).distance(q)) * 95000 < eps for gg in (geom[u], geom[l]) for q in pts)
    dropped = [(u, l) for u, l in rp if near_node(u, l)]
    rp = [(u, l) for u, l in rp if (u, l) not in set(dropped)]
    print(f"pairs whose crossing is within {eps} m of an end node: {len(dropped)} removed, {len(rp)} kept", flush=True)
    items = dict(roads)
    pairs_now = list(rp)
    g = {r: geom[r] for r in roads}
    new_node = [-1]
    history = []
    tried = set()
    for rnd in range(rounds):
        status, cores, released, out = no.solve_hard(items, pairs_now, [], 60)
        history.append((status[0], len(items), len(pairs_now), len(released)))
        for c in cores:
            print("   conflict:", [(k, u[-8:], l[-8:]) for k, u, l in c], flush=True)
        print(f"round {rnd}: {status[0]} ({status[1]} s); items {len(items)}, overpass pairs {len(pairs_now)}, to release {len(released)}", flush=True)
        if out is not None and not released:
            return items, pairs_now, out, history
        # for each conflict: cut the edge that changes level along itself: the lower road of a pair of the conflict that is
        # joined (shares a node) to an edge whose level differs by 2 or more; at its crossing with the upper roads
        todo = {}
        for core in cores:
            lowers = {}
            for _, u, l in core:
                lowers.setdefault(l, []).append(u)
            def vertical(e):
                ns = set(items[e][:2])
                return any(abs(items[o][2] - items[e][2]) >= 2 for o in items if o != e and ns & set(items[o][:2]))
            cand = [l for l in lowers if vertical(l)] or list(lowers)[:1]
            l = cand[0]
            todo.setdefault(l, [])
            todo[l] += [u for u in lowers[l] if u not in todo[l]]
        for l, ups in todo.items():
            root = l.split('#')[0]
            if root in tried:                       # one cut per road: a crossing at the node cannot be separated
                print(f"   road {root[-8:]} already cut: a crossing within 0.3 m of a node cannot be separated", flush=True)
                continue
            tried.add(root)
            s, t, lv, ln = items[l]
            line = g[l]
            deg_to_m = 95000.0
            ts = []
            for u in ups:
                near = line.intersection(g[u])
                pts = [] if near.is_empty else [q for q in (near.geoms if hasattr(near, "geoms") else [near])]
                ts += [line.project(q) * deg_to_m for q in pts]
            length = line.length * deg_to_m
            d = 6.0                                          # the wanted clearance (m), but never into the node or past a crossing
            t_min, t_max = min(ts), max(ts)
            cuts = []
            if t_min - 0.3 > 0.3:
                cuts.append(t_min - min(d, t_min - 0.3))
            if length - t_max - 0.3 > 0.3:
                cuts.append(t_max + min(d, length - t_max - 0.3))
            if not cuts:
                continue
            nodes = [s] + [new_node.append(new_node[-1] - 1) or new_node[-1] for _ in cuts] + [t]
            bounds = [0.0] + cuts + [line.length * deg_to_m]
            pieces = []
            for i in range(len(bounds) - 1):
                pid = f"{l}#{i}"
                pieces.append((pid, substring(line, bounds[i] / deg_to_m, bounds[i + 1] / deg_to_m)))
                items[pid] = (nodes[i], nodes[i + 1], lv, bounds[i + 1] - bounds[i])
                g[pid] = pieces[-1][1]
            del items[l]
            # pairs of the cut road go to the pieces they cross
            new_pairs = []
            for (u, x) in pairs_now:
                if x == l:
                    new_pairs += [(u, pid) for pid, pg in pieces if g[u].crosses(pg)]
                elif u == l:
                    new_pairs += [(pid, x) for pid, pg in pieces if g[x].crosses(pg)]
                else:
                    new_pairs.append((u, x))
            pairs_now = sorted(set(new_pairs))
            print(f"   cut road {l[-8:]} ({hw.get(l)}) into {len(pieces)} pieces at {[round(c, 1) for c in cuts]} m", flush=True)
    return items, pairs_now, None, history


if __name__ == "__main__":
    items, pairs_now, out, history = run(sys.argv[1])
    print("final:", "FEASIBLE: every overpass pair satisfied" if out is not None else "still infeasible", history)
