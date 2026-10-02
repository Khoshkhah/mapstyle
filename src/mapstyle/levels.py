"""The level of a road, drawn only where it is needed (docs/design/levels_plan.md, rule R4).

A road with a ``layer`` tag (and no bridge tag) or a tunnel is drawn at ground level, except for the
stretch where it really passes over or under another road: lines that cross with no node in common,
at another level. That stretch, plus a clearance, is a **piece** of the edge drawn in its own band
(over / under the ground roads) with square ends; the rest of the edge is ground, so every joint is at
ground level and its casings merge. The database and the ``edge_id`` do not change: only the lines
sent to the map are cut. Bridges keep roadstyle's own rule.
"""
import math

import pandas as pd

# metres from a crossing road's edge to the cut, and the half width of a crossing road by class
CLEARANCE_M = 4.0
HALF_WIDTH_M = {"motorway": 6, "trunk": 5.5, "primary": 4.5, "secondary": 4, "tertiary": 3.5, "residential": 3,
                "unclassified": 3, "living_street": 3, "service": 2, "pedestrian": 2.5, "footway": 1,
                "path": 1, "cycleway": 1, "steps": 1, "corridor": 1}
MIN_PIECE_M = 2.0       # a ground piece shorter than this joins the stretch beside it
END_M = 4.0            # a joint end keeps a ground piece at least this long (the round end of the road meeting it needs it)
OVERLAP_M = 0.3         # neighbouring pieces overlap by this much each: two square ends that only touch leave a hairline

def _truthy(col):
    return f"({col} IS NOT NULL AND lower(CAST({col} AS VARCHAR)) NOT IN ('', 'no', 'false', '0'))"


def crossing_pairs(con, union):
    """``(a, b, highway of b)`` edge-id pairs: ``a`` is a road to cut (a plain ``layer`` road or a tunnel) and ``b`` a
    road at a level that makes ``a`` go over or under it, with no node in common and within about 20 m (``_pieces_of``
    keeps those whose drawn roads cross or overlap). Also the roads to cut, with their level."""
    con.execute(f"""
        CREATE TEMP TABLE e0 AS
        SELECT edge_id AS eid, any_value(source) AS s, any_value(target) AS t, any_value(layer) AS layer,
               any_value(bridge) AS bridge, any_value(tunnel) AS tunnel, any_value(highway) AS hw,
               any_value(geometry) AS g
        FROM ({union}) GROUP BY edge_id""")
    con.execute(f"""
        CREATE TEMP TABLE lv AS
        SELECT eid, s, t, hw, g, {_truthy('tunnel')} AS is_tunnel, {_truthy('bridge')} AS is_bridge,
               COALESCE(NULLIF(TRY_CAST(layer AS INTEGER), 0),
                        CASE WHEN {_truthy('bridge')} THEN 1 WHEN {_truthy('tunnel')} THEN -1 ELSE 0 END) AS l
        FROM e0""")
    pairs = con.execute("""
        SELECT CAST(a.eid AS VARCHAR) AS a, CAST(o.eid AS VARCHAR) AS b, o.hw AS hw
        FROM lv a JOIN lv o ON o.eid <> a.eid AND ST_DWithin(a.g, o.g, 0.0002)
             AND a.s NOT IN (o.s, o.t) AND a.t NOT IN (o.s, o.t)
        WHERE NOT a.is_bridge AND (a.is_tunnel OR a.l <> 0)
          AND CASE WHEN a.l > 0 THEN o.l >= 0 AND o.l < a.l ELSE o.l >= 0 END""").df()
    cut = con.execute("SELECT CAST(eid AS VARCHAR) AS eid, l, is_tunnel, s, t FROM lv "
                      "WHERE NOT is_bridge AND (is_tunnel OR l <> 0)").df()
    return pairs, cut


def _scales(geom):
    lat = math.radians(geom.centroid.y)
    return 111320.0 * math.cos(lat), 110574.0


def _metric(geom, sx, sy):
    from shapely import affinity
    return affinity.scale(geom, xfact=sx, yfact=sy, origin=(0, 0))


def _pieces_of(ga, others, band, highway=None, clearance=CLEARANCE_M):
    """``[(m0, m1, band)]`` in metres along ``ga`` (a lon/lat line of class ``highway``): ground except the stretches
    where its drawn road crosses or overlaps the drawn road of one of ``others`` (lon/lat lines with their class: no
    node in common, so they are not connected, only drawn over each other), plus the clearance."""
    sx, sy = _scales(ga)
    gm = _metric(ga, sx, sy)
    total = gm.length
    spans = []
    for gb, hw in others:
        near = gm.intersection(_metric(gb, sx, sy).buffer(HALF_WIDTH_M.get(hw, 3) + HALF_WIDTH_M.get(highway, 1)))
        if near.is_empty:
            continue
        pts = [p for g in getattr(near, "geoms", [near]) for p in (g.boundary.geoms if g.length else [g]) if not p.is_empty]
        ts = [gm.project(p) for p in pts if p.geom_type == "Point"]
        if not ts:
            continue
        spans.append((min(ts) - clearance, max(ts) + clearance, min(ts), max(ts)))
    spans.sort()
    merged = []
    for s0, s1, r0, r1 in spans:
        s0, s1 = max(0.0, s0), min(total, s1)
        if merged and s0 <= merged[-1][1] + MIN_PIECE_M:
            merged[-1][1] = max(merged[-1][1], s1)
            merged[-1][3] = max(merged[-1][3], r1)
        else:
            merged.append([s0, s1, r0, r1])
    if merged:                  # a road meeting the end keeps a ground piece there, unless the crossing is right at it
        first, last = merged[0], merged[-1]
        if first[0] < END_M:
            first[0] = max(first[0], min(END_M, first[2] - 0.5))
        if total - last[1] < END_M:
            last[1] = min(last[1], max(total - END_M, last[3] + 0.5))
    merged = [[a, b] for a, b, *_ in merged]
    out, at = [], 0.0
    for s0, s1 in merged:
        if s0 - at >= MIN_PIECE_M:
            out.append((at, s0, 0))
        else:
            s0 = at
        out.append((s0, s1, band))
        at = s1
    if total - at >= MIN_PIECE_M:
        out.append((at, total, 0))
    elif out:
        out[-1] = (out[-1][0], total, out[-1][2])
    return out or [(0.0, total, 0)]


def level_pieces(con, union, geoms, highways):
    """``({edge_id: [(m0, m1, band), ...]}, tunnel edge ids, edge ids to end square)`` for every road to cut, in order
    along the edge: ground pieces and the stretches that go over (band 1) or under (band -1) a road. ``geoms`` / ``highways``: ``{edge_id: ...}`` of the
    db's roads (lon/lat lines, classes). A road that crosses nothing is one ground piece."""
    pairs, cut = crossing_pairs(con, union)
    by_a = {a: [] for a in cut["eid"]}
    for a, b, hw in pairs.itertuples(index=False):
        if b in geoms:
            by_a[a].append((geoms[b], hw))
    out = {}
    for eid, lvl in zip(cut["eid"], cut["l"]):
        if eid not in geoms:
            continue
        out[eid] = _pieces_of(geoms[eid], by_a.get(eid, []), 1 if lvl > 0 else -1, highways.get(eid))
    # a stretch that reaches the node (a crossing right at the mouth) leaves no ground piece there: the roads that
    # meet it there end square, or their round end would show as a ring over the lower stretch
    nodes = set()
    for eid, sn, tn in zip(cut["eid"], cut["s"], cut["t"]):
        parts = out.get(eid)
        if parts and len(parts) and parts[0][2] != 0:
            nodes.add(int(sn))
        if parts and parts[-1][2] != 0:
            nodes.add(int(tn))
    square = set()
    if nodes:
        ids = ", ".join(str(n) for n in nodes)
        square = {str(e) for (e,) in con.execute(f"SELECT eid FROM lv WHERE s IN ({ids}) OR t IN ({ids})").fetchall()}
    return out, {eid for eid, t in zip(cut["eid"], cut["is_tunnel"]) if t}, square - set(out)


def with_pieces(roads, pieces, tunnels, square=()):
    """The roads as drawn: each edge in ``pieces`` becomes its first piece (same row, so the feature index the
    planner's graphs point to is unchanged) and its other pieces are appended after the last edge, with
    ``_piece`` set. Columns ``_band`` (the piece's band, else the edge's own) and ``_cap`` (square ends: a stretch
    that goes over or under, and every piece of a tunnel). ``tunnels``: the set of tunnel edge ids."""
    from shapely import affinity
    from shapely.ops import substring

    roads = roads.copy()
    roads["_piece"] = False
    roads["_cap"] = roads["edge_id"].isin(square)             # roads meeting a stretch at a node end square
    extra = []
    for i, eid in zip(roads.index, roads["edge_id"]):
        parts = pieces.get(eid)
        if not parts:
            continue
        ga = roads.at[i, "geometry"]
        sx, sy = _scales(ga)
        gm = _metric(ga, sx, sy)
        rows = []
        last = len(parts) - 1
        for n, (m0, m1, band) in enumerate(parts):
            a, b = max(0.0, m0 - OVERLAP_M) if n else m0, min(gm.length, m1 + OVERLAP_M) if n < last else m1
            line = affinity.scale(substring(gm, a, b), xfact=1 / sx, yfact=1 / sy, origin=(0, 0))
            rows.append((line, band))
        own = roads.at[i, "_band"]
        for n, (line, band) in enumerate(rows):
            cap = band != 0 or eid in tunnels
            b = band if pd.isna(own) else own
            if n == 0:
                roads.at[i, "geometry"], roads.at[i, "_band"], roads.at[i, "_cap"] = line, b, cap
            else:
                r = roads.loc[i].copy()
                r["geometry"], r["_band"], r["_cap"], r["_piece"] = line, b, cap, True
                if "k" in r.index:
                    r["k"] = float("nan")          # the planner's graphs point at the edge's first piece only
                extra.append(r)
    if extra:
        import geopandas as gpd
        roads = gpd.GeoDataFrame(pd.concat([roads, pd.DataFrame(extra)], ignore_index=True), geometry="geometry",
                                 crs=roads.crs)
    return roads
