"""A duckOSM db as a roadstyle map: roads styled for one travel mode (docs/design/mode_styles.md)
and the base map from ``features.*`` (docs/design/feature_layers.md).

roadstyle is not changed: a mode is a roadstyle ``palette`` + ``settings=`` (styles/modes.yaml); a
feature layer is an ``rs.Overlay`` plus mapstyle's page script (layers.js) for what overlays can't draw.
"""

import base64
import json
from collections import Counter
import logging
from pathlib import Path

from mapstyle.style import _walk, load_style, load_theme, themes

MODES = ("driving", "walking", "cycling")          # duckOSM's networks: the roads' mode flags
LOOKS = ("all",) + MODES                           # render_map(mode=): "all" emphasises none (modes.yaml)
PATHS = "google"                                   # the default path style (styles/paths.yaml)
# the ways that are paths, not roads (duckOSM's own list: global_junctions._NON_ROAD_HIGHWAYS)
PATH_CLASSES = ("footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor")
log = logging.getLogger(__name__)
_HERE = Path(__file__).parent
OPTIONAL_COLS = ("walk_type", "junction", "edge_ref", "lanes")   # roadstyle reads junction: a roundabout is on top where roads meet
_OV_KIND = {"polygon": "fill", "line": "line", "point": "circle"}


def _roads_union(con, db):
    """The SQL that stacks every mode's ``edges`` (and ``private_edges``) with ``walk_type`` / ``mode`` / ``pmode`` /
    ``access`` columns; loads the spatial extension on ``con``."""
    con.execute("INSTALL spatial; LOAD spatial;")
    have = {r[0] for r in con.execute(
        "SELECT table_schema FROM information_schema.tables WHERE table_name = 'edges'").fetchall()}
    modes = [m for m in MODES if m in have]
    if not modes:
        raise ValueError(f"{db}: no <mode>.edges table (modes: {', '.join(MODES)})")
    has = {(s, t, c) for s, t, c in con.execute("SELECT table_schema, table_name, column_name FROM information_schema.columns").fetchall()}
    cols = "edge_id, source, target, osm_id, highway, name, bridge, tunnel, layer, oneway, geometry"
    priv = {r[0] for r in con.execute("SELECT table_schema FROM information_schema.tables "
                                      "WHERE table_name = 'private_edges'").fetchall()} & set(modes)

    def optional(m, t, skip=()):                     # a column an older file may not have: NULL there (edge_ref a text NULL: a bare NULL comes back as pandas NA, which roadstyle 0.18's edge_ref read cannot test)
        return ", ".join(f"{c if (m, t, c) in has and c not in skip else ('CAST(NULL AS VARCHAR)' if c == 'edge_ref' else 'NULL')} AS {c}" for c in OPTIONAL_COLS)
    return " UNION ALL ".join(
        [f"SELECT {cols}, {optional(m, 'edges')}, '{m}' AS mode, "
         f"NULL AS pmode, NULL AS access FROM {m}.edges" for m in modes]
        + [f"SELECT {cols}, {optional(m, 'private_edges', ('walk_type',))}, NULL AS mode, '{m}' AS pmode, access "
           f"FROM {m}.private_edges" for m in sorted(priv)])


def load_roads(db):
    """One row per ``edge_id`` over the db's mode networks, with ``driving`` / ``walking`` /
    ``cycling`` flags (the mode can use it) and duckOSM's ``walk_type`` (sidewalk, crossing,
    footpath, …; the walking network's, when the build has it). The roads a mode may not use
    (``<mode>.private_edges``) are rows too, with ``access_driving`` / ``access_walking`` /
    ``access_cycling``: ``private`` or ``bus`` where that mode keeps it there, else null
    (docs/design/private_and_bus.md). ``edge_id`` / ``osm_id`` are strings: the hashes can pass
    2**53. Rows are in ``edge_id`` order (a one-way street's walking-only reverse edges first), so a page's feature ids are the same on every render."""
    import duckdb
    import geopandas as gpd

    con = duckdb.connect(str(db), read_only=True)
    try:
        union = _roads_union(con, db)
        # several rows per edge (modes, private_edges): a usable mode's first, so the same every time
        con.execute(f"""
            CREATE TEMP TABLE r AS
            SELECT CAST(edge_id AS VARCHAR) AS edge_id, edge_id AS eid,
                   any_value(source) AS s, any_value(target) AS t,
                   CAST(first(osm_id ORDER BY mode IS NULL, mode, pmode) AS VARCHAR) AS osm_id,
                   first(highway ORDER BY mode IS NULL, mode, pmode) AS highway, COALESCE(first(name ORDER BY mode IS NULL, mode, pmode), '') AS name,
                   first(bridge ORDER BY mode IS NULL, mode, pmode) AS bridge, first(tunnel ORDER BY mode IS NULL, mode, pmode) AS tunnel,
                   first(layer ORDER BY mode IS NULL, mode, pmode) AS layer, bool_or(oneway) AS oneway,
                   any_value(walk_type) AS walk_type,
                   {", ".join(f"first({c} ORDER BY mode IS NULL, mode, pmode) AS {c}" for c in OPTIONAL_COLS[1:])},
                   {", ".join(f"COALESCE(bool_or(mode = '{m}'), false) AS {m}" for m in MODES)},
                   {", ".join(f"max(CASE WHEN pmode = '{m}' THEN access END) AS access_{m}" for m in MODES)},
                   first(geometry ORDER BY mode IS NULL, mode, pmode) AS geom
            FROM ({union}) GROUP BY edge_id""")
        df = con.execute("""
            SELECT r.* EXCLUDE (eid, s, t, geom), ST_AsWKB(r.geom) AS wkb FROM r ORDER BY r.eid""").df()   # stable rows: the page's ids
    finally:
        con.close()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    roads = gpd.GeoDataFrame(df, geometry=geom)
    # an undirected edge (a one-way street's walking-only reverse) lies on the street's own directed edge: it goes first, so it is
    # drawn under it and the click (and Street View) get the directed edge
    und = ~roads["driving"] & ~roads["cycling"] & ~roads["highway"].isin(PATH_CLASSES) \
        & roads["osm_id"].isin(roads.loc[roads["driving"] | roads["cycling"], "osm_id"])
    return roads.iloc[(~und).to_numpy().argsort(kind="stable")].reset_index(drop=True)


def mode_settings(mode, paths=PATHS, theme="osm"):
    """``(palette_name, settings)`` for ``rs.render_edges``: the palette (roadstyle's carto +
    osm_carto.yaml's colours + the path style's, paths.yaml, all in the ``theme``'s colours) and the
    ``roads`` / ``config`` settings (the mode's network in the path style's ``em`` width group, on
    top; modes.yaml; plus the theme's roadstyle settings)."""
    import roadstyle as rs

    if mode not in LOOKS:
        raise ValueError(f"unknown mode {mode!r}; choose from {LOOKS}")
    styles = load_style("paths")
    if paths not in styles:
        raise ValueError(f"unknown path style {paths!r}; choose from {tuple(styles)}")
    modes, st = load_style("modes"), styles[paths]
    spec = modes[mode] or {}
    style, th, color = load_theme(theme)
    base = _walk(rs.palette_to_dict("carto"), color)
    colors = style["roads"]["colors"]
    over = {c: {**v, **(th.get("paths") or {}).get(c, {})}
            for c, v in _walk(st.get("palette") or {}, color).items()}
    # a class the base lacks (pedestrian, steps, platform, …) starts from footway's entry without
    # its dash: osm_carto.yaml gives the dash where a class has one
    new = {**base["footway"], "dash": None}
    palette = {c: {**base.get(c, new), **colors.get(c, {}), **over.get(c, {})}
               for c in {*base, *colors, *over}}
    if spec.get("fade") and st.get("fade"):
        for c in modes["cars"]:
            for k in ("fill", "casing"):
                if palette[c].get(k):
                    palette[c][k] = _mix(palette[c][k], "#ffffff", st["fade"])
    roads = {k: dict(v) for k, v in (spec.get("roads") or {}).items()}
    for k, v in {"width": {"em": st["em"]["width"]}, "width_zoom_rate": {"em": 1.3},
                 "casing_ratio": {"em": st["em"]["casing_ratio"]},
                 "group": {"ferry": "path", **{c: "em" for c in spec.get("em", [])}, **(st.get("group") or {})}}.items():   # a ferry line: path width
        roads.setdefault(k, {}).update(v)
    config = {"minor_no_casing": st["minor_no_casing"]} if "minor_no_casing" in st else {}
    config.update(th.get("roadstyle") or {})
    name = f"ms_{mode}_{paths}" + ("" if theme in (None, "osm") else f"_{theme}")
    # json round trip: zoom keys as strings, like roadstyle's own width tables
    return name, json.loads(json.dumps({"palettes": {name: palette}, "roads": roads, "config": config}))


def load_layers(db, names=None):
    """``{name: FeatureCollection}`` for the ``styles/layers.yaml`` layers (``names``: a subset),
    in draw order. A missing ``features.*`` table or column skips the layer with a logged hint."""
    import duckdb

    specs = [s for s in load_style("layers")["layers"] if s.get("show", True)
             and (names is None or s["name"] in names or s.get("merge_into") in names)]
    out, area = {}, {}
    con = duckdb.connect(str(db), read_only=True)
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables "
                                          "WHERE table_schema = 'features'").fetchall()}
        if not have:
            log.warning("%s has no features.* (build it with duckOSM's build_features: true): "
                        "roads only", db)
        for s in specs:
            if s["table"] not in have:
                if have:
                    log.warning("features.%s missing: layer %r skipped", s["table"], s["name"])
                continue
            g = "ST_Centroid(geom)" if s.get("centroid") else "geom"
            try:
                rows = con.execute(
                    f"SELECT CAST(osm_id AS VARCHAR), kind, COALESCE(name, ''), "
                    f"{'bearing' if s.get('bearing') else 'NULL'}, ST_Area(geom), ST_AsGeoJSON({g}) "
                    f"FROM features.{s['table']} WHERE geom IS NOT NULL"
                    + (f" AND ({s['where']})" if s.get("where") else "")).fetchall()
            except duckdb.Error as e:
                log.warning("layer %r skipped: %s", s["name"], e)
                continue
            name = s.get("merge_into") or s["name"]
            for osm_id, kind, nm, bearing, a, gj in rows:
                props = {"osm_id": osm_id, "kind": kind, "name": nm}
                if bearing is not None:
                    props["bearing"] = bearing
                out.setdefault(name, []).append(
                    {"type": "Feature", "properties": props, "geometry": json.loads(gj)})
                area.setdefault(name, []).append(a or 0)
    finally:
        con.close()
    # largest first (bottom): a school's pitch draws over the school, a park over the residential area
    return {n: {"type": "FeatureCollection",
                "features": [f for _, f in sorted(zip(area[n], fs), key=lambda p: -p[0])]
                if _kind(n) == "polygon" else fs}
            for n, fs in out.items()}


def _kind(name):
    return next(s["kind"] for s in load_style("layers")["layers"] if s["name"] == name)


def _access(roads, mode):
    """The page's ``access`` per road (docs/design/private_and_bus.md): in one mode, its
    restriction there (``private`` / ``bus``) when that mode can't use it; on the ``all`` map,
    ``bus`` for a bus road or lane for cars (though bikes may use it), ``private`` when no mode
    can use it; else null."""
    if mode in MODES:
        return roads[f"access_{mode}"].where(~roads[mode])
    acc = roads[[f"access_{m}" for m in MODES]]
    nobody = ~roads[list(MODES)].any(axis=1) & acc.notna().any(axis=1)
    first = acc.iloc[:, 0]                                       # the first restriction of the modes in order (a back-fill of the table is slow on big areas)
    for k in range(1, acc.shape[1]):
        first = first.combine_first(acc.iloc[:, k])
    return roads["access_driving"].where(roads["access_driving"] == "bus", first.where(nobody))


def _is_directed(roads):
    """Per edge: a direction of travel of its own, i.e. a road (not a path) open to cars or bikes.
    False = undirected: a footway stored both ways, a one-way street's walking-only reverse edge."""
    return (roads["driving"] | roads["cycling"]) & ~roads["highway"].isin(PATH_CLASSES)


def _mix(a, b, t):
    """Hex colour ``a`` mixed ``t`` of the way to ``b``."""
    x, y = (bytes.fromhex(h.lstrip("#")) for h in (a, b))
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))


def _darker(hex_color, f=0.6):
    h = hex_color.lstrip("#")
    return "#" + "".join(f"{int(int(h[i:i + 2], 16) * f):02x}" for i in (0, 2, 4))


def _data_url(mime, data):
    return f"data:{mime};base64," + base64.b64encode(data).decode()


EDGE_ATTACHED = ("crossings", "traffic_signals")     # point layers that sit on a road: drawn at the level of their road (docs/design/edge_features.md)


_CLASS_RANK = {c: r for r, c in enumerate(("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"), 1)}


def edge_attach(fcs, roads, names=EDGE_ATTACHED, near=1e-5, far=3e-5):
    """Put ``edge_id`` (text: it can pass 2**53) on every feature of the layers ``names`` in ``fcs``: the **street** it is on, not the footpath, so that the point is drawn at the
    level of that street, over its fill and under every road above it. Of the streets (not a path class) within ``near`` degrees (about 1 m) of the point, the one drawn on top: the
    highest ``fill_level`` if ``roads`` has the stored levels, then the highest band, then the highest class (a link as its parent), so that no street the point overlaps covers it.
    With no street that close: the nearest street within ``far`` (about 3 m: a signal stands beside its road), else the nearest road. (A crossing's own edge is no good: duckOSM's levels
    put 562 of Monaco's 1,292 crossing edges below the street they cross, because a short road is never stacked over another; docs/design/edge_features.md.)
    Returns the names of the layers that got one (an empty layer stays a plain overlay)."""
    import numpy as np
    import shapely
    from shapely import STRtree
    from shapely.geometry import shape

    klass = roads["highway"].fillna("").str.removesuffix("_link").map(_CLASS_RANK).fillna(99)
    fill = roads["fill_level"].to_numpy() if "fill_level" in roads else np.zeros(len(roads))
    top = np.lexsort(((-klass).to_numpy(), _band(roads), fill))[::-1]       # roads from the one drawn on top to the one under
    rank = np.empty(len(roads), int)
    rank[top] = np.arange(len(roads))
    geoms = roads.geometry.to_numpy()
    tree = STRtree(geoms)
    street = ~roads["highway"].isin(PATH_CLASSES).to_numpy()
    ids = roads["edge_id"].to_numpy()
    done = []
    for name in names:
        feats = (fcs.get(name) or {}).get("features")
        if not feats:
            continue
        for f in feats:
            pt = shape(f["geometry"])
            hits = tree.query(pt, predicate="dwithin", distance=near)
            hits = hits[street[hits]]
            if not len(hits):
                hits = tree.query(pt, predicate="dwithin", distance=far)
                hits = hits[street[hits]] if street[hits].any() else hits
                if len(hits):
                    d = shapely.distance(pt, geoms[hits])
                    hits = hits[d <= d.min() + 2e-6]                       # the nearest (about 0.2 m)
            j = hits[np.argmin(rank[hits])] if len(hits) else tree.query_nearest(pt)[0]
            f["properties"]["edge_id"] = str(ids[j])
        done.append(name)
    return done


def feature_overlays(fcs, interaction=None, style=None, edge_attached=()):
    """``(overlays, script_config)`` for ``load_layers`` output: one ``rs.Overlay`` per layer, and
    what layers.js adds on top (colour by kind, zoom ranges, dashes, textures, icons, each layer's
    opening ``{clickable, tooltip, popup}``: today's defaults updated by ``interaction``)."""
    import roadstyle as rs
    from mapstyle.patterns import pattern_png

    st = (style or load_style())["features"]
    areas, lines, points, icon = st["areas"], st["lines"], st["points"], st["icon"]
    overlays, layers, images = [], [], {}
    for name, fc in fcs.items():
        kind = _kind(name)
        L = {"label": name, "kind": _OV_KIND[kind]}
        ov = dict(data=fc, kind=L["kind"], label=name, placement="over" if kind == "point" else "under")
        if name in edge_attached:             # drawn at the fill number of its edge (roadstyle's edge_col): layers.js puts the icon there too
            ov["edge_col"] = "edge_id"
        if name == "landcover":               # colour, outline and texture by kind
            fills = dict(areas["landcover"])
            default = fills.pop("default")
            ov.update(color=default, opacity=1.0, width=1)
            L["color_by"] = {"map": fills, "default": default}
            L["outline_by"] = {"map": st["landcover_outline"], "default": "rgba(0,0,0,0)"}
            L["patterns"] = {}
            for k, pat in st["landcover_pattern"].items():
                images[f"ms-pat-{k}"] = _data_url(
                    "image/png", pattern_png(pat, _darker(fills.get(k, default))))
                L["patterns"][k] = f"ms-pat-{k}"
        elif kind == "polygon":
            a = areas.get(name, {})
            ov.update(color=a.get("fill"), outline=a.get("outline"), opacity=a.get("opacity", 1.0),
                      width=0.5)
            L["min_zoom"] = a.get("min_zoom")
        elif kind == "line":
            ln = lines.get(name, {})
            ov.update(color=ln.get("color"), width=ln.get("width"))
            L["dash"] = ln.get("dash")
        else:
            p = {**points["default"], **points.get(name, {})}
            ov.update(color=p["color"], radius=4)
            L["min_zoom"] = p.get("min_zoom")
            if p.get("icon"):
                svg = (_HERE / "icons" / p["icon"]).read_text()
                images[f"ms-icon-{name}"] = _data_url(
                    "image/svg+xml", svg.replace("<svg ", f'<svg fill="{p["color"]}" ', 1).encode())
                # the SVGs are 48 px: icon-size = px / 48, scaled by the category's size
                L["icon"] = {"image": f"ms-icon-{name}", "opacity": icon["opacity"],
                             "size": [[z, px * p["size"] / 48] for z, px in icon["size"].items()]}
        # built clickable with a tooltip so rsSetInteraction can switch both ways (layers.js);
        # decoration (landcover, water, lines) opens not clickable, so a click reaches the road
        L["interaction"] = {"clickable": not (name in ("landcover", "water") or kind == "line"),
                            "tooltip": False, "popup": True, **(interaction or {}).get(name, {})}
        # starts hidden: layers.js shows it once styled (icons, zoom range, colours), so the page
        # never flashes plain dots / every building first (Kaveh: "it shows all POI and then removes them")
        overlays.append(rs.Overlay(**ov, popup=["name", "kind"], tooltip=["name", "kind"], visible=False))
        layers.append(L)
    kinds = {n: dict(Counter(f["properties"]["kind"] for f in fc["features"]).most_common())
             for n, fc in fcs.items()}
    return overlays, {"layers": layers, "images": images, "kinds": kinds}


def _json(data):
    """JSON safe inside a ``<script>``."""
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


# the Roads / Layers boxes stay unseen until layers.js has folded and placed them (data-ms)
_BOX_CSS = "<style>.flt-ctrl:not([data-ms]),.ov-ctrl:not([data-ms]){visibility:hidden}</style>"


def _inject(m, html):
    """Add ``html`` to a roadstyle page before ``</body>``, as roadstyle's own pages add their sidebar
    (and ``_BOX_CSS`` to its head, so it applies from the first paint)."""
    m._tpl = m._tpl.replace("</head>", _BOX_CSS + "</head>", 1).replace("</body>", html + "</body>", 1)
    return m


def planner_data(db, roads):
    """The route planner's graphs (the page's ``RM``), as duckOSM's route_map.py builds them: per mode
    its turn graph (``edge_graph``) over the feature indices of ``roads`` (``load_roads``), and
    walk + drive from ``mm.*`` when the db has it. Node ids become small integers (some pass 2**53)."""
    import duckdb

    con = duckdb.connect(str(db), read_only=True)
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        have = {tuple(r) for r in con.execute(
            "SELECT table_schema, table_name FROM information_schema.tables").fetchall()}
        modes = [m for m in MODES if (m, "edges") in have and (m, "edge_graph") in have]
        if not modes:
            raise ValueError(f"{db}: no mode with edges + edge_graph to route on")
        k_of = {}                                   # a road cut into pieces has several rows: the first one is the road
        for k, e in enumerate(roads["edge_id"]):
            k_of.setdefault(int(e), k)
        ends = {}                                   # edge_id -> (source, target, length_m, junction)
        for tb in ("edges", "private_edges"):          # private_edges: drawn, never routed
            for m in MODES:
                if (m, tb) not in have:
                    continue
                jn = "junction" if con.execute(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = ? "
                    "AND table_name = ? AND column_name = 'junction'", [m, tb]).fetchone()[0] else "NULL"
                for e, s, t, ln, j in con.execute(
                        f"SELECT edge_id, source, target, length_m, {jn} FROM {m}.{tb}").fetchall():
                    ends.setdefault(e, (s, t, ln, j))
        node_ids = sorted({x for s, t, *_ in ends.values() for x in (s, t)})
        n_of = {n: i for i, n in enumerate(node_ids)}
        row = [ends[int(e)] for e in roads["edge_id"]]
        data = {"modes": modes, "n": len(roads), "src": [n_of[r[0]] for r in row],
                "tgt": [n_of[r[1]] for r in row], "name": list(roads["name"]),
                "len": [round(r[2] or 0.0, 1) for r in row],
                "hw": [h or "" for h in roads["highway"]],       # for the turn-by-turn directions
                "rb": [k for k, r in enumerate(row) if r[3] in ("roundabout", "circular")],
                "graphs": {}, "mm": None}
        for m in modes:                                        # edge-based graph of legal turns
            es = con.execute(f"SELECT edge_id, cost_s, length_m FROM {m}.edges ORDER BY edge_id").fetchall()
            nxt = {}
            for f, t in con.execute(f"SELECT from_edge, to_edge FROM {m}.edge_graph").fetchall():
                if f in k_of and t in k_of:
                    nxt.setdefault(k_of[f], []).append(k_of[t])
            data["graphs"][m] = {"k": [k_of[e] for e, _, _ in es],
                                 "cost": [round(c or 0.0, 3) for _, c, _ in es],
                                 "len": [round(ln or 0.0, 2) for _, _, ln in es],
                                 "next": [nxt.get(k_of[e], []) for e, _, _ in es]}
        # walk + drive over duckOSM's intermodal graph (`duckosm multimodal`), when it's there;
        # walk + cycle needs bike stations to mean anything (bike anywhere), so not offered
        if {"walking", "driving"} <= set(modes) and ("mm", "edges") in have and ("mm", "transfers") in have:
            mi = {m: i for i, m in enumerate(modes) if m in ("walking", "driving")}
            mm_edges = [[mi[md], n_of[s], n_of[t], k_of[e], round(c or 0.0, 3)]
                        for md, s, t, e, c in con.execute(
                            "SELECT mode, source, target, edge_id, cost_s FROM mm.edges").fetchall()
                        if md in mi and e in k_of and s in n_of and t in n_of]
            mm_tr = [[n_of[n], mi[fm], mi[tm], round(c or 0.0, 3)]
                     for n, fm, tm, c in con.execute(
                         "SELECT node_id, from_mode, to_mode, cost_s FROM mm.transfers").fetchall()
                     if fm in mi and tm in mi and n in n_of]
            data["mm"] = {"edges": mm_edges, "transfers": mm_tr, "nodes": len(node_ids)}
        # the page opens with a route: markers on the roads nearest 30 % and 70 % along the diagonal
        x0, y0, x1, y1 = con.execute(
            f"SELECT min(ST_XMin(geometry)), min(ST_YMin(geometry)), max(ST_XMax(geometry)), "
            f"max(ST_YMax(geometry)) FROM {modes[0]}.edges").fetchone()
        near = (f"SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_LineInterpolatePoint(geometry, 0.5) AS p "
                f"FROM {modes[0]}.edges ORDER BY ST_Distance(ST_Centroid(geometry), ST_Point(?, ?)) LIMIT 1)")
        data["start"], data["end"] = (list(con.execute(near, [x0 + (x1 - x0) * f, y0 + (y1 - y0) * f]).fetchone())
                                      for f in (0.3, 0.7))
    finally:
        con.close()
    return data


def _band(roads):
    """The band of every road: below (-1 ...), on (0) or over (1 ...) the ground (docs/design/stored_levels.md). It is complete, because roadstyle's ``band_col``
    replaces the level from the tags: the OSM ``layer`` if that is a number, else 1 for a bridge, -1 for a tunnel, else 0. A sidewalk and a crossing have the band of their tags too: they
    are on the ground like their street, which the class order paints over them (docs/design/crossing_band.md). The same as duckOSM's (``duckosm levels``)."""
    import numpy as np
    import pandas as pd

    layer = pd.to_numeric(roads["layer"], errors="coerce").fillna(0).astype(int).to_numpy()

    def yes(col):
        return (roads[col].notna() & ~roads[col].astype(str).isin(["", "no", "None", "nan"])).to_numpy()
    return np.where(layer != 0, layer, np.where(yes("bridge"), 1, np.where(yes("tunnel"), -1, 0))).astype(int)


def stored_levels(db, roads):
    """``roads`` with the drawing order stored in the file by ``duckosm levels`` (its level area: the four numbers and each edge's ends),
    or None when the file has none. A ``ValueError`` if it was solved for other roads (the file was rebuilt): run ``duckosm levels`` again.
    Nothing is recomputed (docs/design/stored_levels.md)."""
    import duckdb
    import roadstyle as rs

    con = duckdb.connect(str(db), read_only=True)
    try:
        if not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'visualization' AND table_name = 'edge_levels'").fetchone()[0]:
            return None
        try:
            return rs.load_area_levels(con, roads)
        except ValueError as e:
            raise ValueError(f"{e}; run `duckosm levels {db}` again") from None
    finally:
        con.close()


LEVEL_COLS = dict(casing_start_col="casing_start", casing_level_col="casing_level", casing_end_col="casing_end", fill_level_col="fill_level")


def render_map(db, mode=None, layers=True, planner=False, dashboard=False, interaction=None,
               paths=PATHS, theme="osm", **kwargs):
    """``rs.render_edges`` of the db's roads (all modes' edges) in the ``mode``'s style, over the
    ``features.*`` base map, with mapstyle's rs* functions (``rsSetModes``, ``rsSetKinds``,
    ``rsSetInteraction``: layers.js). ``layers``: True = every styles/layers.yaml layer, a list of
    names, or False = roads only. ``paths``: how walking / cycling paths look (styles/paths.yaml:
    komoot, osm, cyclosm, google). ``interaction``: a layer's opening ``{clickable, tooltip, popup}``,
    e.g. ``{"landcover": {"clickable": True}}``. ``planner=True`` adds the route planner
    (docs/design/route_planner.md); ``dashboard=True`` makes it roadstyle's report page with mode,
    kind and interaction filters (docs/design/dashboard.md). ``mode``: which network stands out
    (all, driving, walking, cycling); default all (the planner too: in the walking look a road's two directions are one line, so only one can be clicked).
    ``theme``: the whole map's colours, ``osm`` (default) or a styles/themes/*.yaml
    (docs/design/themes.md). The drawing order of the roads is roadstyle's (docs/design/stored_levels.md): every road has a casing number and a fill number, so that connected
    roads merge cleanly and a road that passes over another is drawn over it. They are read from ``visualization.edge_levels`` when the file has them (``duckosm levels``),
    else roadstyle computes them while it renders. The base map is ``blank``: the db's own layers are the map (the sea is ``features.ocean``).
    ``kwargs`` go to roadstyle
    (``basemap``, ``tiles``, ``arrows``, ...)."""
    import roadstyle as rs

    if "order" in kwargs:
        raise ValueError("render_map(order=...) is removed: the drawing order is roadstyle's (docs/design/stored_levels.md)")
    if "pieces" in kwargs:
        raise ValueError("render_map(pieces=...) is removed: the drawing order is the file's level area (duckosm levels), fixable by hand")
    mode = mode or "all"
    if planner and kwargs.get("tiles"):
        raise ValueError("planner=True can't use tiles=True: the planner snaps to the roads in the page")
    if planner and dashboard:
        raise ValueError("planner=True and dashboard=True both use the right-hand panel: pick one")
    palette, settings = mode_settings(mode, paths, theme)
    style, th, _ = load_theme(theme)
    roads = load_roads(db)
    fcs = load_layers(db, None if layers is True else layers) if layers else {}
    unknown = set(interaction or {}) - set(fcs)
    if unknown:
        log.warning("interaction: no layer %s on this map", ", ".join(sorted(unknown)))
    # a point on a road is drawn at its road's level; the roads must be the ones roadstyle draws
    # (the levels are read again below, with the columns added to the roads since: they are cheap)
    levels = stored_levels(db, roads)
    overlays, config = feature_overlays(fcs, interaction, style, edge_attached=edge_attach(fcs, roads if levels is None else levels))
    roads["access"] = _access(roads, mode)
    roads = roads.drop(columns=[f"access_{m}" for m in MODES])
    kw = {"name": f"{Path(db).stem} ({mode}, {paths}" + ("" if theme in (None, "osm") else f", {theme}") + ")",
          "tooltip": ["edge_id", "osm_id", "highway", "name", "access"],
          "copy_field": "edge_id", "overlays": overlays}
    if load_style("modes")[mode].get("lanes") is False:        # one centred line per road
        kw.update(offset_frac=0, width_frac=1)
    # blank: the map is the db's own (Kaveh, 2026-09-30); the raster maps stay in the switcher
    bg = "blank"
    if th.get("background"):                   # the theme's land colour: a plain base map of its own
        bg = f"blank_{theme}"
        rs.register_basemap(rs.Basemap(bg, f"Blank ({theme})", "", "", bg=th["background"]))
    kw.update(basemap=bg, basemaps=[bg, "voyager_nolabels", "voyager", "positron", "osm", "satellite"])
    html = f"<script>{(_HERE / 'layers.js').read_text().replace('__MS__', _json(config))}</script>"
    if planner:
        roads["k"] = range(len(roads))                          # the feature index the graphs point to
        html += (_HERE / "planner.html").read_text().replace("__RM__", _json(planner_data(db, roads)))
        kw.update(name=f"{Path(db).stem}: route planner")
    render = rs.render_edges
    if dashboard:
        flags = [roads[m].to_numpy() for m in MODES]
        roads["modes"] = ["all modes" if sum(f) == len(MODES) else " + ".join(m for m, x in zip(MODES, f, strict=True) if x) for f in zip(*flags, strict=True)]
        kw.pop("tooltip")                # the panel shows the clicked road: no road hover tooltip
        kw.update(name=f"{Path(db).stem}: dashboard", color_options={
            "Road class": {}, "Modes": {"color_by": "modes", "colors": load_style("modes")["mode_colors"]}})
        html += f"<script>{(_HERE / 'dashboard.js').read_text()}</script>"
        render = rs.render_report
    # the drawing order: the file's level area (duckosm levels), else roadstyle computes it while drawing (docs/design/stored_levels.md)
    stored = stored_levels(db, roads)
    if stored is not None:
        roads = stored
        kw.update(LEVEL_COLS, head_start_m_col="head_start_m", head_end_m_col="head_end_m", cap_start_col="cap_start", cap_end_col="cap_end")
    # duckOSM stores every path, and a one-way street's walking-only reverse, as a reverse edge too:
    # roadstyle draws a pair as two lanes only when both edges are directed (directed_col,
    # twin_ends.md)
    roads["is_directed"] = _is_directed(roads)
    kw["directed_col"] = "is_directed"
    kw["driving_col"] = "driving"                          # arrows only on cars' one-ways (roadstyle 0.18.1): never on a bus / bike-only reverse
    m = render(roads, palette=palette, settings=settings, **{**kw, **kwargs})
    return _inject(m, html)


def main(argv=None):
    """``mapstyle db.duckdb [-o map.html] [--mode walking] [--no-layers] [--planner | --dashboard]
    [--tiles] [--basemap KEY]``"""
    import argparse

    ap = argparse.ArgumentParser(prog="mapstyle", description="A duckOSM db as one interactive HTML map.")
    ap.add_argument("db", help="a duckOSM .duckdb")
    ap.add_argument("-o", "--out", help="output HTML (default: <db name>_<mode>.html)")
    ap.add_argument("--mode", choices=LOOKS,
                    help="which network stands out (default: all)")
    ap.add_argument("--no-layers", action="store_true", help="roads only, no features.* layers")
    ap.add_argument("--paths", default=PATHS, choices=tuple(load_style("paths")),
                    help=f"how walking / cycling paths look (default: {PATHS})")
    ap.add_argument("--theme", default="osm", choices=themes(),
                    help="the whole map's colours (default: osm; grey: a quiet map for data)")
    ap.add_argument("--planner", action="store_true", help="add the route planner (drag start and end)")
    ap.add_argument("--dashboard", action="store_true", help="a dashboard: filter by mode, class, layer, kind")
    ap.add_argument("--tiles", action="store_true", help="roads as vector tiles in the page (large areas)")
    ap.add_argument("--basemap", help="a roadstyle base map key (e.g. blank, positron, satellite)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    kw = {"tiles": True} if a.tiles else {}
    if a.basemap:
        kw["basemap"] = a.basemap
    mode = a.mode or "all"
    kind = "planner" if a.planner else "dashboard" if a.dashboard else mode
    out = a.out or f"{Path(a.db).stem}_{kind}.html"
    render_map(a.db, mode, layers=not a.no_layers, planner=a.planner, dashboard=a.dashboard,
               paths=a.paths, theme=a.theme, **kw).save(out)
    print(out)
