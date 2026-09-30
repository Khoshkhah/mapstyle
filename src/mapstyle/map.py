"""A duckOSM db as a roadstyle map: roads styled for one travel mode (docs/design/mode_styles.md)
and the base map from ``features.*`` (docs/design/feature_layers.md).

roadstyle is not changed: a mode is a roadstyle ``palette`` + ``settings=`` (styles/modes.yaml); a
feature layer is an ``rs.Overlay`` plus mapstyle's page script (layers.js) for what overlays can't draw.
"""

import base64
import json
import logging
from pathlib import Path

from mapstyle.style import load_style

MODES = ("driving", "walking", "cycling")
log = logging.getLogger(__name__)
_HERE = Path(__file__).parent
_OV_KIND = {"polygon": "fill", "line": "line", "point": "circle"}


def load_roads(db):
    """One row per ``edge_id`` over the db's mode networks, with ``driving`` / ``walking`` /
    ``cycling`` flags. ``edge_id`` / ``osm_id`` are strings: the hashes can pass 2**53."""
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
        union = " UNION ALL ".join(
            f"SELECT edge_id, osm_id, highway, name, bridge, tunnel, layer, oneway, geometry, "
            f"'{m}' AS mode FROM {m}.edges" for m in modes)
        df = con.execute(f"""
            SELECT CAST(edge_id AS VARCHAR) AS edge_id,
                   CAST(any_value(osm_id) AS VARCHAR) AS osm_id,
                   any_value(highway) AS highway, COALESCE(any_value(name), '') AS name,
                   any_value(bridge) AS bridge, any_value(tunnel) AS tunnel,
                   any_value(layer) AS layer, bool_or(oneway) AS oneway,
                   {", ".join(f"bool_or(mode = '{m}') AS {m}" for m in MODES)},
                   ST_AsWKB(any_value(geometry)) AS wkb
            FROM ({union}) GROUP BY edge_id""").df()
    finally:
        con.close()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom)


def mode_settings(mode):
    """``(palette_name, settings)`` for ``rs.render_edges``: the mode's palette (roadstyle's
    carto + osm_carto.yaml's colours + the mode's overrides) and its ``roads`` settings."""
    import roadstyle as rs

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    spec = load_style("modes")[mode] or {}
    base = rs.palette_to_dict("carto")
    colors = load_style()["roads"]["colors"]
    over = spec.get("palette") or {}
    palette = {c: {**base.get(c, base["footway"]), **colors.get(c, {}), **over.get(c, {})}
               for c in {*base, *colors, *over}}
    name = f"ms_{mode}"
    # json round trip: zoom keys as strings, like roadstyle's own width tables
    return name, json.loads(json.dumps({"palettes": {name: palette}, "roads": spec.get("roads") or {}}))


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


def _darker(hex_color, f=0.6):
    h = hex_color.lstrip("#")
    return "#" + "".join(f"{int(int(h[i:i + 2], 16) * f):02x}" for i in (0, 2, 4))


def _data_url(mime, data):
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def feature_overlays(fcs):
    """``(overlays, script_config)`` for ``load_layers`` output: one ``rs.Overlay`` per layer, and
    what layers.js adds on top (colour by kind, zoom ranges, dashes, textures, icons)."""
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
            ov.update(color=default, opacity=1.0, width=1, popup=[])
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
                      width=0.5, popup=[] if name == "water" else ["name", "kind"])
            L["min_zoom"] = a.get("min_zoom")
        elif kind == "line":
            ln = lines.get(name, {})
            ov.update(color=ln.get("color"), width=ln.get("width"), popup=[])
            L["dash"] = ln.get("dash")
        else:
            p = {**points["default"], **points.get(name, {})}
            ov.update(color=p["color"], radius=4, popup=["name", "kind"])
            L["min_zoom"] = p.get("min_zoom")
            if p.get("icon"):
                svg = (_HERE / "icons" / p["icon"]).read_text()
                images[f"ms-icon-{name}"] = _data_url(
                    "image/svg+xml", svg.replace("<svg ", f'<svg fill="{p["color"]}" ', 1).encode())
                # the SVGs are 48 px: icon-size = px / 48, scaled by the category's size
                L["icon"] = {"image": f"ms-icon-{name}", "opacity": icon["opacity"],
                             "size": [[z, px * p["size"] / 48] for z, px in icon["size"].items()]}
        overlays.append(rs.Overlay(**ov))
        layers.append(L)
    return overlays, {"layers": layers, "images": images}


def _inject(m, config):
    """Add layers.js to a roadstyle page, before ``</body>`` as roadstyle's own pages add their sidebar."""
    js = (_HERE / "layers.js").read_text().replace("__MS__", json.dumps(config).replace("</", "<\\/"))
    m._tpl = m._tpl.replace("</body>", f"<script>{js}</script></body>", 1)
    return m


def render_map(db, mode="driving", layers=True, **kwargs):
    """``rs.render_edges`` of the db's roads (all modes' edges) in the ``mode``'s style, over the
    ``features.*`` base map. ``layers``: True = every styles/layers.yaml layer, a list of names, or
    False = roads only. ``kwargs`` go to roadstyle (``basemap``, ``tiles``, ``arrows``, ...)."""
    import roadstyle as rs

    palette, settings = mode_settings(mode)
    fcs = load_layers(db, None if layers is True else layers) if layers else {}
    overlays, config = feature_overlays(fcs)
    kw = {"name": f"{Path(db).stem} ({mode})", "tooltip": ["edge_id", "osm_id", "highway", "name"],
          "copy_field": "edge_id", "overlays": overlays}
    if fcs:     # a label-free raster under the features: duckOSM has no sea polygons (yet)
        kw.update(basemap="voyager_nolabels",
                  basemaps=["voyager_nolabels", "blank", "voyager", "positron", "osm", "satellite"])
    m = rs.render_edges(load_roads(db), palette=palette, settings=settings, **{**kw, **kwargs})
    return _inject(m, config) if fcs else m


def main(argv=None):
    """``mapstyle db.duckdb [-o map.html] [--mode walking] [--no-layers] [--tiles] [--basemap KEY]``"""
    import argparse

    ap = argparse.ArgumentParser(prog="mapstyle", description="A duckOSM db as one interactive HTML map.")
    ap.add_argument("db", help="a duckOSM .duckdb")
    ap.add_argument("-o", "--out", help="output HTML (default: <db name>_<mode>.html)")
    ap.add_argument("--mode", choices=MODES, default="driving", help="travel-mode style (default: driving)")
    ap.add_argument("--no-layers", action="store_true", help="roads only, no features.* layers")
    ap.add_argument("--tiles", action="store_true", help="roads as vector tiles in the page (large areas)")
    ap.add_argument("--basemap", help="a roadstyle base map key (e.g. blank, positron, satellite)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    kw = {"tiles": True} if a.tiles else {}
    if a.basemap:
        kw["basemap"] = a.basemap
    out = a.out or f"{Path(a.db).stem}_{a.mode}.html"
    render_map(a.db, a.mode, layers=not a.no_layers, **kw).save(out)
    print(out)
