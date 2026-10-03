"""PROTOTYPE of Approach B (docs/design/node_levels.md): a level for each node, from which every edge gets a
casing time and a fill time. Not imported by the library; it only tests the idea.

    python scripts/node_levels.py DB            # statistics on a duckOSM db
"""
import sys
from collections import defaultdict


def edge_table(con, union):
    """One row per edge: ``(eid, s, t, lvl)`` with roadstyle's level rule (the layer, else a bridge 1, a tunnel -1)."""
    t = lambda c: f"({c} IS NOT NULL AND lower(CAST({c} AS VARCHAR)) NOT IN ('', 'no', 'false', '0'))"  # noqa: E731
    con.execute(f"""
        CREATE TEMP TABLE e0 AS
        SELECT edge_id AS eid, any_value(source) AS s, any_value(target) AS t, any_value(layer) AS layer,
               any_value(bridge) AS bridge, any_value(tunnel) AS tunnel, any_value(geometry) AS g
        FROM ({union}) GROUP BY edge_id""")
    con.execute(f"""
        CREATE TEMP TABLE lv AS
        SELECT eid, s, t, g, COALESCE(NULLIF(TRY_CAST(layer AS INTEGER), 0),
               CASE WHEN {t('bridge')} THEN 1 WHEN {t('tunnel')} THEN -1 ELSE 0 END) AS l FROM e0""")


def crossings(con):
    """``[(upper eid, lower eid)]``: the lines cross, no node in common, the levels differ."""
    return con.execute("""
        SELECT CASE WHEN a.l > o.l THEN a.eid ELSE o.eid END, CASE WHEN a.l > o.l THEN o.eid ELSE a.eid END
        FROM lv a JOIN lv o ON a.eid < o.eid AND ST_Intersects(a.g, o.g) AND a.l <> o.l
             AND a.s NOT IN (o.s, o.t) AND a.t NOT IN (o.s, o.t) AND ST_Crosses(a.g, o.g)""").fetchall()


def tangled(edges, pairs):
    """The pairs that cannot be satisfied together: build "this node must be above that node" for every pair and
    drop the pairs whose two nodes lie in one strongly connected component (a cycle, e.g. a spiral ramp).
    Returns ``(kept, dropped)``."""
    import networkx as nx
    g = nx.DiGraph()
    for u, l in pairs:
        for nu in edges[u][:2]:
            for nl in edges[l][:2]:
                g.add_edge(nl, nu)
    comp = {}
    for i, c in enumerate(nx.strongly_connected_components(g)):
        for n in c:
            comp[n] = i
    kept, dropped = [], []
    for u, l in pairs:
        bad = any(comp[nl] == comp[nu] for nu in edges[u][:2] for nl in edges[l][:2])
        (dropped if bad else kept).append((u, l))
    return kept, dropped


def solve(edges, pairs):
    """``edges``: ``{eid: (s, t, lvl)}``; ``pairs``: ``[(upper, lower)]``. Returns ``(p, left, dropped)``: a level for
    every node, the pairs still violated, and the pairs dropped as unsatisfiable (cycles).

    1. Drop the pairs that sit in a cycle (``tangled``): what is left is a DAG of "this node above that node".
    2. Rank the nodes of it by the longest chain below them (every node of the upper edge above every node of the
       lower edge, one level apart at least).
    3. Shift each connected piece of the DAG as a whole to the offset that keeps most nodes near the level their
       edges' tags suggest (a node touching a ground road: 0; else the level nearest to 0 among its edges).
    Every node outside the DAG stays at 0."""
    import networkx as nx
    pairs, dropped = tangled(edges, pairs)
    g = nx.DiGraph()
    for u, l in pairs:
        for nu in edges[u][:2]:
            for nl in edges[l][:2]:
                g.add_edge(nl, nu)
    rank = {}
    for n in nx.topological_sort(g):
        rank[n] = max((rank[q] + 1 for q in g.predecessors(n)), default=0)
    near = defaultdict(lambda: 99)
    pref = {}
    for s_, t_, lv in edges.values():
        for n in (s_, t_):
            if abs(lv) < near[n]:
                near[n], pref[n] = abs(lv), lv
    p = defaultdict(int)
    for s_, t_, _ in edges.values():
        p[s_], p[t_]
    for comp in nx.weakly_connected_components(g):
        best = min(range(-5, 6), key=lambda o: (sum(abs(rank[n] + o - pref.get(n, 0)) for n in comp), abs(o)))
        for n in comp:
            p[n] = rank[n] + best
    left = [(u, l) for u, l in pairs
            if not all(p[nu] > p[nl] for nu in edges[u][:2] for nl in edges[l][:2])]
    return dict(p), left, dropped


def times(edges, p):
    """``{eid: (casing level, fill level)}``: the lowest and the highest level of the edge's two nodes."""
    return {e: (min(p[s], p[t]), max(p[s], p[t])) for e, (s, t, _) in edges.items()}


def report(db):
    import duckdb

    from mapstyle.map import _roads_union
    con = duckdb.connect(str(db), read_only=True)
    try:
        union = _roads_union(con, db)
        edge_table(con, union)
        edges = {str(e): (s, t, int(l)) for e, s, t, l in con.execute("SELECT eid, s, t, l FROM lv").fetchall()}
        pairs = [(str(a), str(b)) for a, b in crossings(con)]
    finally:
        con.close()
    p, left, dropped = solve(edges, pairs)
    ct = times(edges, p)
    span = defaultdict(int)
    for c, f in ct.values():
        span[f - c] += 1
    lv = defaultdict(int)
    for v in p.values():
        lv[v] += 1
    print(f"edges {len(edges)}, nodes {len(p)}, crossing pairs with different levels {len(pairs)}")
    print("node levels:", dict(sorted(lv.items())))
    print("edges by (fill level - casing level):", dict(sorted(span.items())))
    print(f"pairs dropped as unsatisfiable (cycles): {len(dropped)}; still violated after solving: {len(left)}")
    return edges, pairs, p, left, ct, dropped


if __name__ == "__main__":
    report(sys.argv[1])
