#!/usr/bin/env python3
"""Render Tartu as mapstyle's merged viewer — roads + full base map — from a SINGLE duckOSM db.

Everything comes from one duckOSM db built with `options.build_features`: the routing modes
(driving / walking / cycling → names, oneway arrows, per-zoom widths) AND the `features.*`
base-map layers (water / land / buildings / rail + parking / transit / traffic signals / crossings).
No duckmap dependency.

Build the db once with:  (in duckOSM)  python main.py build --config config/tartu.yaml
Usage:
    python render_tartu.py [duckosm_db.duckdb] [out_dir]
Then: python <out_dir>/serve.py 8080   ->  http://localhost:8080/index.html
"""
import sys

import duckdb
import geopandas as gpd
import shapely.wkt as wkt

from mapstyle import merge_modes, render_merge
from mapstyle.layers import Layer

DB = sys.argv[1] if len(sys.argv) > 1 else "../duckOSM/data/db/tartu.duckdb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "render/tartu"

RAIL = "('rail','tram','light_rail','subway','narrow_gauge','funicular','monorail')"


def load(table, name, kind, where=None, centroid=False, bearing=False):
    """Load one features.<table> layer from the duckOSM db as a styling Layer (Shortbread `kind`)."""
    g = "ST_Centroid(geom)" if centroid else "geom"
    cols = "kind" + (", bearing" if bearing else "")
    w = f" AND ({where})" if where else ""
    con = duckdb.connect(DB, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    rows = con.execute(f"SELECT {cols}, ST_AsText({g}) FROM features.{table} "
                       f"WHERE geom IS NOT NULL{w}").fetchall()
    con.close()
    d = {"class": [r[0] for r in rows], "highway": [r[0] for r in rows]}
    if bearing:
        d["bearing"] = [r[1] for r in rows]
    gdf = gpd.GeoDataFrame(d, geometry=[wkt.loads(r[-1]) for r in rows], crs="EPSG:4326")
    if len(gdf) and kind != "point":
        gdf["geometry"] = gdf.geometry.simplify(2e-5, preserve_topology=False)
    return Layer(name, gdf, kind)


merged = merge_modes(DB)                                    # roads: names / arrows / per-zoom widths
feats = [
    load("land",            "landcover",       "polygon"),
    load("water_polygons",  "water",           "polygon"),    # incl. the Emajõgi river (smart clip)
    load("water_lines",     "waterways",       "line"),
    load("buildings",       "buildings",       "polygon"),
    load("streets",         "railways",        "line",    where=f"kind IN {RAIL}"),
    load("sites",           "parking",         "polygon", where="kind = 'parking'"),         # parking AREA
    load("sites",           "parking_p",       "point",   where="kind = 'parking'", centroid=True),  # P sign
    load("sites",           "bus_station",     "polygon", where="kind = 'bus_station'"),      # bus terminal footprint
    load("sites",           "platform",        "polygon", where="kind = 'platform'"),         # transit platform footprints
    load("traffic",         "traffic_signals", "point",   where="kind = 'traffic_signals'"),
    load("traffic",         "crossings",       "point",   where="kind = 'crossing'", bearing=True),
    load("public_transport", "bus_stations",   "point",   where="kind = 'bus_stop'"),
    load("public_transport", "train_stations", "point",   where="kind IN ('station','halt')"),
    load("pois",            "bicycle",         "point",   where="kind = 'bicycle_rental'"),
]
render_merge(merged, OUT, basemap="none", overlays=("names", "arrows"), feature_layers=feats)
print(f"rendered -> {OUT}/index.html   (serve: python {OUT}/serve.py)")
