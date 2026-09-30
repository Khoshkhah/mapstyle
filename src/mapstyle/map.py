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

from mapstyle.style import load_style

MODES = ("driving", "walking", "cycling")          # duckOSM's networks: the roads' mode flags
LOOKS = ("all",) + MODES                           # render_map(mode=): "all" emphasises none (modes.yaml)
PATHS = "google"                                   # the default path style (styles/paths.yaml)
log = logging.getLogger(__name__)
_HERE = Path(__file__).parent
_OV_KIND = {"polygon": "fill", "line": "line", "point": "circle"}


def load_roads(db):
    """One row per ``edge_id`` over the db's mode networks, with ``driving`` / ``walking`` /
    ``cycling`` flags and duckOSM's ``walk_type`` (sidewalk, crossing, footpath, …; the walking
    network's, when the build has it). ``edge_id`` / ``osm_id`` are strings: the hashes can pass
    2**53."""
    import duckdb
    import geopandas as gpd

    con = duckdb.connect(str(db), read_only=True)
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        have = {r[0] for r in con.execute(
            "SELECT table_schema FROM information_schema.tables WHERE table_name = 'edges'").fetchall()}
        modes = [m for m in MODES if m in have]
        if not modes:
            raise ValueError(f"{db}: no <mode>.edges table (modes: {', '.join(MODES)})")
        wt = {m for (m,) in con.execute("SELECT table_schema FROM information_schema.columns "
                                        "WHERE table_name = 'edges' AND column_name = 'walk_type'").fetchall()}
        union = " UNION ALL ".join(
            f"SELECT edge_id, osm_id, highway, name, bridge, tunnel, layer, oneway, geometry, "
            f"{'walk_type' if m in wt else 'NULL'} AS walk_type, '{m}' AS mode FROM {m}.edges" for m in modes)
        df = con.execute(f"""
            SELECT CAST(edge_id AS VARCHAR) AS edge_id,
                   CAST(any_value(osm_id) AS VARCHAR) AS osm_id,
                   any_value(highway) AS highway, COALESCE(any_value(name), '') AS name,
                   any_value(bridge) AS bridge, any_value(tunnel) AS tunnel,
                   any_value(layer) AS layer, bool_or(oneway) AS oneway,
                   any_value(walk_type) AS walk_type,
                   {", ".join(f"bool_or(mode = '{m}') AS {m}" for m in MODES)},
                   ST_AsWKB(any_value(geometry)) AS wkb
            FROM ({union}) GROUP BY edge_id""").df()
    finally:
        con.close()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom)


def mode_settings(mode, paths=PATHS):
    """``(palette_name, settings)`` for ``rs.render_edges``: the palette (roadstyle's carto +
    osm_carto.yaml's colours + the path style's, paths.yaml) and the ``roads`` / ``config``
    settings (the mode's network in the path style's ``em`` width group, on top; modes.yaml)."""
    import roadstyle as rs

    if mode not in LOOKS:
        raise ValueError(f"unknown mode {mode!r}; choose from {LOOKS}")
    styles = load_style("paths")
    if paths not in styles:
        raise ValueError(f"unknown path style {paths!r}; choose from {tuple(styles)}")
    modes, st = load_style("modes"), styles[paths]
    spec = modes[mode] or {}
    base = rs.palette_to_dict("carto")
    colors = load_style()["roads"]["colors"]
    over = st.get("palette") or {}
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
                 "group": {**{c: "em" for c in spec.get("em", [])}, **(st.get("group") or {})}}.items():
        roads.setdefault(k, {}).update(v)
    config = {"minor_no_casing": st["minor_no_casing"]} if "minor_no_casing" in st else {}
    name = f"ms_{mode}_{paths}"
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


def _mix(a, b, t):
    """Hex colour ``a`` mixed ``t`` of the way to ``b``."""
    x, y = (bytes.fromhex(h.lstrip("#")) for h in (a, b))
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))


def _darker(hex_color, f=0.6):
    h = hex_color.lstrip("#")
    return "#" + "".join(f"{int(int(h[i:i + 2], 16) * f):02x}" for i in (0, 2, 4))


def _data_url(mime, data):
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def feature_overlays(fcs, interaction=None):
    """``(overlays, script_config)`` for ``load_layers`` output: one ``rs.Overlay`` per layer, and
    what layers.js adds on top (colour by kind, zoom ranges, dashes, textures, icons, each layer's
    opening ``{clickable, tooltip, popup}``: today's defaults updated by ``interaction``)."""
    import roadstyle as rs
    from mapstyle.patterns import pattern_png

    st = load_style()["features"]
    areas, lines, points, icon = st["areas"], st["lines"], st["points"], st["icon"]
    overlays, layers, images = [], [], {}
    for name, fc in fcs.items():
        kind = _kind(name)
        L = {"label": name, "kind": _OV_KIND[kind]}
        ov = dict(data=fc, kind=L["kind"], label=name, placement="over" if kind == "point" else "under")
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
        overlays.append(rs.Overlay(**ov, popup=["name", "kind"], tooltip=["name", "kind"]))
        layers.append(L)
    kinds = {n: dict(Counter(f["properties"]["kind"] for f in fc["features"]).most_common())
             for n, fc in fcs.items()}
    return overlays, {"layers": layers, "images": images, "kinds": kinds}


def _json(data):
    """JSON safe inside a ``<script>``."""
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def _inject(m, html):
    """Add ``html`` to a roadstyle page before ``</body>``, as roadstyle's own pages add their sidebar."""
    m._tpl = m._tpl.replace("</body>", html + "</body>", 1)
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
        k_of = {int(e): k for k, e in enumerate(roads["edge_id"])}
        ends = {}                                   # edge_id -> (source, target, length_m, junction)
        for m in MODES:
            if (m, "edges") in have:
                jn = "junction" if con.execute(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = ? "
                    "AND table_name = 'edges' AND column_name = 'junction'", [m]).fetchone()[0] else "NULL"
                for e, s, t, ln, j in con.execute(
                        f"SELECT edge_id, source, target, length_m, {jn} FROM {m}.edges").fetchall():
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


def render_map(db, mode=None, layers=True, planner=False, dashboard=False, interaction=None,
               paths=PATHS, **kwargs):
    """``rs.render_edges`` of the db's roads (all modes' edges) in the ``mode``'s style, over the
    ``features.*`` base map, with mapstyle's rs* functions (``rsSetModes``, ``rsSetKinds``,
    ``rsSetInteraction``: layers.js). ``layers``: True = every styles/layers.yaml layer, a list of
    names, or False = roads only. ``paths``: how walking / cycling paths look (styles/paths.yaml:
    komoot, osm, cyclosm, google). ``interaction``: a layer's opening ``{clickable, tooltip, popup}``,
    e.g. ``{"landcover": {"clickable": True}}``. ``planner=True`` adds the route planner
    (docs/design/route_planner.md); ``dashboard=True`` makes it roadstyle's report page with mode,
    kind and interaction filters (docs/design/dashboard.md). ``mode``: which network stands out
    (all, driving, walking, cycling); default all, walking with the planner (a walking leg shows).
    The base map is ``blank`` (duckOSM has no sea yet: PLAN step 3). ``kwargs`` go to roadstyle
    (``basemap``, ``tiles``, ``arrows``, ...)."""
    import roadstyle as rs

    mode = mode or ("walking" if planner else "all")
    if planner and kwargs.get("tiles"):
        raise ValueError("planner=True can't use tiles=True: the planner snaps to the roads in the page")
    if planner and dashboard:
        raise ValueError("planner=True and dashboard=True both use the right-hand panel: pick one")
    palette, settings = mode_settings(mode, paths)
    roads = load_roads(db)
    fcs = load_layers(db, None if layers is True else layers) if layers else {}
    unknown = set(interaction or {}) - set(fcs)
    if unknown:
        log.warning("interaction: no layer %s on this map", ", ".join(sorted(unknown)))
    overlays, config = feature_overlays(fcs, interaction)
    kw = {"name": f"{Path(db).stem} ({mode}, {paths})", "tooltip": ["edge_id", "osm_id", "highway", "name"],
          "copy_field": "edge_id", "overlays": overlays}
    if load_style("modes")[mode].get("lanes") is False:        # one centred line per road
        kw.update(offset_frac=0, width_frac=1)
    # blank: the map is the db's own (Kaveh, 2026-09-30); the raster maps stay in the switcher
    kw.update(basemap="blank", basemaps=["blank", "voyager_nolabels", "voyager", "positron", "osm", "satellite"])
    html = f"<script>{(_HERE / 'layers.js').read_text().replace('__MS__', _json(config))}</script>"
    if planner:
        roads["k"] = range(len(roads))                          # the feature index the graphs point to
        html += (_HERE / "planner.html").read_text().replace("__RM__", _json(planner_data(db, roads)))
        kw.update(name=f"{Path(db).stem}: route planner", filter_control=False)
    render = rs.render_edges
    if dashboard:
        n = roads[list(MODES)].sum(axis=1)
        roads["modes"] = ["all modes" if k == len(MODES) else " + ".join(m for m in MODES if r[m])
                          for k, (_, r) in zip(n, roads[list(MODES)].iterrows())]
        kw.pop("tooltip")                # the panel shows the clicked road: no road hover tooltip
        kw.update(name=f"{Path(db).stem}: dashboard", color_options={
            "Road class": {}, "Modes": {"color_by": "modes", "colors": load_style("modes")["mode_colors"]}})
        html += f"<script>{(_HERE / 'dashboard.js').read_text()}</script>"
        render = rs.render_report
    # a crossing (the zebra) draws over the street it crosses, a sidewalk under the street beside
    # it, casings included (roadstyle's band_col; roadstyle/docs/design/draw_order_per_edge.md)
    roads["band"] = roads["walk_type"].map({"crossing": 1, "sidewalk": -1})
    kw["band_col"] = "band"
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
                    help="which network stands out (default: all, walking with --planner)")
    ap.add_argument("--no-layers", action="store_true", help="roads only, no features.* layers")
    ap.add_argument("--paths", default=PATHS, choices=tuple(load_style("paths")),
                    help=f"how walking / cycling paths look (default: {PATHS})")
    ap.add_argument("--planner", action="store_true", help="add the route planner (drag start and end)")
    ap.add_argument("--dashboard", action="store_true", help="a dashboard: filter by mode, class, layer, kind")
    ap.add_argument("--tiles", action="store_true", help="roads as vector tiles in the page (large areas)")
    ap.add_argument("--basemap", help="a roadstyle base map key (e.g. blank, positron, satellite)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    kw = {"tiles": True} if a.tiles else {}
    if a.basemap:
        kw["basemap"] = a.basemap
    mode = a.mode or ("walking" if a.planner else "all")
    kind = "planner" if a.planner else "dashboard" if a.dashboard else mode
    out = a.out or f"{Path(a.db).stem}_{kind}.html"
    render_map(a.db, mode, layers=not a.no_layers, planner=a.planner, dashboard=a.dashboard,
               paths=a.paths, **kw).save(out)
    print(out)
