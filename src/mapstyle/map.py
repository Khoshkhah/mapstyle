"""A duckOSM db's roads as a roadstyle map, styled for one travel mode (docs/design/mode_styles.md).

roadstyle is not changed: a mode is a roadstyle ``palette`` + ``settings=`` (styles/modes.yaml).
"""

import json
from pathlib import Path

from mapstyle.style import load_style

MODES = ("driving", "walking", "cycling")


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


def render_map(db, mode="driving", **kwargs):
    """``rs.render_edges`` of the db's roads (all modes' edges) in the ``mode``'s style.
    ``kwargs`` go to roadstyle (``basemap``, ``tiles``, ``arrows``, ...)."""
    import roadstyle as rs

    palette, settings = mode_settings(mode)
    kw = {"name": f"{Path(db).stem} ({mode})", "tooltip": ["edge_id", "osm_id", "highway", "name"],
          "copy_field": "edge_id", **kwargs}
    return rs.render_edges(load_roads(db), palette=palette, settings=settings, **kw)
