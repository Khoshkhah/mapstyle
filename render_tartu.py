#!/usr/bin/env python3
"""Render Tartu as mapstyle's merged viewer — roads + full base map — from a SINGLE duckOSM db.

Everything comes from one duckOSM db built with `options.build_features`: the routing modes
(driving / walking / cycling → names, oneway arrows, per-zoom widths) AND the `features.*`
base-map layers (water / land / buildings / rail + parking / transit / traffic signals / crossings).
No duckmap dependency.

Build the db once with:  (in duckOSM)  python main.py build --config config/tartu.yaml
Usage:
    python render_tartu.py [duckosm_db.duckdb] [out_dir]     # lean fast BASE map (default)
    python render_tartu.py --debug                           # full inspectable viewer (hover/click/info)
Then: python <out_dir>/serve.py 8080   ->  http://localhost:8080/index.html

Default out_dir: render/basemap (base) or render/debug_visualization (--debug).
"""
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import shapely.wkt as wkt
import yaml

from mapstyle import merge_modes, render_merge
from mapstyle.layers import Layer

_args = [a for a in sys.argv[1:] if not a.startswith("--")]
DEBUG = "--debug" in sys.argv    # --debug = full inspectable viewer (hover/click/info + toggles);
                                 # default = lean fast BASE map (base-layer selector only, no picking)
DB = _args[0] if len(_args) > 0 else "../duckOSM/data/db/tartu.duckdb"
OUT = _args[1] if len(_args) > 1 else ("render/debug_visualization" if DEBUG else "render/basemap")
LAYERS = Path(__file__).parent / "layers.yaml"   # WHICH feature layers to show (config, separate from style)


def load(table, name, kind, where=None, centroid=False, bearing=False):
    """Load one features.<table> layer from the duckOSM db as a styling Layer (Shortbread `kind`).
    Carries osm_id / name / full tags so the debug viewer can show every object's info on click.
    Polygon layers are NOT sorted here — feature_layers() sorts once, after any merge_into."""
    g = "ST_Centroid(geom)" if centroid else "geom"
    cols = "kind, osm_id, COALESCE(map_extract(tags,'name')[1], '') AS nm, to_json(tags) AS tg" \
           + (", bearing" if bearing else "")
    w = f" AND ({where})" if where else ""
    con = duckdb.connect(DB, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    rows = con.execute(f"SELECT {cols}, ST_AsText({g}) FROM features.{table} "
                       f"WHERE geom IS NOT NULL{w}").fetchall()
    con.close()
    d = {"class": [r[0] for r in rows], "highway": [r[0] for r in rows],
         "osm_id": [r[1] for r in rows], "name": [r[2] for r in rows], "tags": [r[3] for r in rows]}
    if bearing:
        d["bearing"] = [r[4] for r in rows]
    gdf = gpd.GeoDataFrame(d, geometry=[wkt.loads(r[-1]) for r in rows], crs="EPSG:4326")
    # NO simplification: simplifying polygons independently cut corners off features ("missed some
    # parts") and desynced shared borders between adjacent landcover (gaps/overlaps). Render full-res.
    return Layer(name, gdf, kind)


def add_construction(merged):
    """Inject `highway=construction` ways into the roads layer so they render as REAL roads
    (per-zoom width + casing), sized/shaped by their future class (`construction=<class>` tag) but
    drawn grey. They're excluded from the routing network, so they come from features.streets."""
    con = duckdb.connect(DB, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    rows = con.execute("""
        SELECT osm_id, COALESCE(map_extract(tags, 'construction')[1], 'residential') AS future,
               name, ST_AsText(geom)
        FROM features.streets WHERE kind = 'construction' AND geom IS NOT NULL
    """).fetchall()
    con.close()
    if not rows:
        return
    cols = ["edge_id", "highway", "name", "length_m", "layer", "bridge", "tunnel", "service",
            "oneway", "driving", "walking", "cycling", "combo", "is_construction"]
    rec = {c: [] for c in cols}
    geoms = []
    for osm_id, future, name, wkt_s in rows:
        vals = [int(osm_id), future, name, None, 0, False, False, None,
                False, True, True, True, "dwc", True]   # md/mw/mc True so it survives the mode filter
        for c, v in zip(cols, vals):
            rec[c].append(v)
        geoms.append(wkt.loads(wkt_s))
    extra = gpd.GeoDataFrame(rec, geometry=geoms, crs="EPSG:4326")
    extra["length_m"] = extra.to_crs(extra.estimate_utm_crs()).length.round()   # for name-label fit
    g = merged.gdf
    if "is_construction" not in g:
        g["is_construction"] = False
    merged.gdf = gpd.GeoDataFrame(pd.concat([g, extra], ignore_index=True), crs="EPSG:4326")


def feature_layers():
    """Build the feature Layers listed in layers.yaml, in draw order, skipping any with `show: false`.
    WHICH features appear is config-driven — edit layers.yaml (separate from the visual style), not
    this script.

    `merge_into: <name>` appends a layer's features INTO an already-built layer (must appear earlier)
    instead of adding a separate layer. Institutional site areas (school / university / hospital /
    sports_centre …) merge into `landcover` so ONE largest-first sort resolves all nesting — e.g. a
    school's own pitch/grass paints ON TOP of the school, not hidden under it."""
    specs = (yaml.safe_load(LAYERS.read_text()) or {}).get("layers") or []
    built, order = {}, []
    for s in specs:
        if not s.get("show", True):
            continue
        lyr = load(s["table"], s["name"], s["kind"], where=s.get("where"),
                   centroid=s.get("centroid", False), bearing=s.get("bearing", False))
        tgt = s.get("merge_into")
        if tgt and tgt in built:
            base = built[tgt]
            base.gdf = gpd.GeoDataFrame(pd.concat([base.gdf, lyr.gdf], ignore_index=True),
                                        crs="EPSG:4326")
        else:
            built[s["name"]] = lyr
            order.append(s["name"])
    out = []
    for nm in order:
        lyr = built[nm]
        g = lyr.gdf
        # draw LARGEST first (bottom): a big landuse=residential / school polygon must sit UNDER the
        # smaller, more-specific features nested in it (parks/grass/pitch), else it hides them.
        if len(g) > 1 and lyr.kind == "polygon":
            g = (g.assign(_a=g.geometry.area).sort_values("_a", ascending=False)
                   .drop(columns="_a").reset_index(drop=True))
            lyr = Layer(nm, g, lyr.kind)
        out.append(lyr)
    return out


merged = merge_modes(DB)                                    # roads: names / arrows / per-zoom widths
add_construction(merged)                                    # + highway=construction as grey real roads
feats = feature_layers()                                    # base-map layers — config-driven (features.layers)
render_merge(merged, OUT, basemap="none", overlays=("names", "arrows"), feature_layers=feats,
             interactive=DEBUG, title=("Debug Visualization" if DEBUG else "Map"))
print(f"rendered {'debug' if DEBUG else 'base'} map -> {OUT}/index.html   (serve: python {OUT}/serve.py)")
