#!/usr/bin/env python3
"""Render Tartu (or any area) as mapstyle's merged viewer with base-map feature layers +
SVG category icons — via render_merge (the one mapstyle viewer).

Roads (driving/walking/cycling, names, oneway arrows, per-zoom widths) and the base-map feature
layers (land / water / buildings / rail + parking / transit / crossings) come from a duckmap
basemap db. The river POLYGON needs a duckOSM smart-clip features db (duckmap's water lacks it),
so pass one as the optional 2nd arg to use it for the water layer.

Usage:
    python render_tartu.py <duckmap_basemap.duckdb> [duckosm_features.duckdb] [out_dir]
Then: python <out_dir>/serve.py 8080   ->  http://localhost:8080/index.html
"""
import sys

import duckdb
import geopandas as gpd
import shapely.wkt as wkt

from mapstyle import merge_modes, render_merge
from mapstyle.layers import Layer

DUCKMAP = sys.argv[1] if len(sys.argv) > 1 else "../duckmap/data/db/tartu_basemap.duckdb"
FEAT = sys.argv[2] if len(sys.argv) > 2 else None    # optional duckOSM features db (for the river polygon)
OUT = sys.argv[3] if len(sys.argv) > 3 else "render/tartu"


def load(db, table, name, kind, where=None, schema="basemap", centroid=False, bearing=False):
    col = "kind" if schema == "features" else "class"           # duckOSM features use `kind`, duckmap `class`
    g = "ST_Centroid(geom)" if centroid else "geom"
    be = ", bearing" if bearing else ""
    con = duckdb.connect(db, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    w = f" AND ({where})" if where else ""
    rows = con.execute(f"SELECT {col}{be}, ST_AsText({g}) FROM {schema}.{table} "
                       f"WHERE geom IS NOT NULL{w}").fetchall()
    con.close()
    d = {"class": [r[0] for r in rows], "highway": [r[0] for r in rows]}
    if bearing:
        d["bearing"] = [r[1] for r in rows]
    gdf = gpd.GeoDataFrame(d, geometry=[wkt.loads(r[-1]) for r in rows], crs="EPSG:4326")
    if len(gdf) and kind != "point":
        gdf["geometry"] = gdf.geometry.simplify(2e-5, preserve_topology=False)
    return Layer(name, gdf, kind)


merged = merge_modes(DUCKMAP)                                    # roads: names / arrows / per-zoom widths
water = (load(FEAT, "water_polygons", "water", "polygon", schema="features")
         if FEAT else load(DUCKMAP, "water", "water", "polygon"))   # river polygon needs the duckOSM features db
feats = [
    load(DUCKMAP, "landcover", "landcover", "polygon"), water,
    load(DUCKMAP, "waterways", "waterways", "line"),
    load(DUCKMAP, "buildings", "buildings", "polygon"),
    load(DUCKMAP, "railways", "railways", "line"),
    load(DUCKMAP, "parking", "parking", "point", centroid=True),
    load(DUCKMAP, "pois", "traffic_signals", "point", where="class='traffic_signals'"),
    load(DUCKMAP, "pois", "bus_stations", "point", where="class IN ('bus_stop','bus_station')"),
    load(DUCKMAP, "pois", "bicycle", "point", where="class IN ('bicycle_parking','bicycle_rental')"),
    load(DUCKMAP, "pois", "train_stations", "point", where="class IN ('station','halt','tram_stop')"),
    load(DUCKMAP, "pois", "crossings", "point", where="class='crossing'", bearing=True),  # bearing -> icon orientation
]
render_merge(merged, OUT, basemap="none", overlays=("names", "arrows"), feature_layers=feats)
print(f"rendered -> {OUT}/index.html   (serve: python {OUT}/serve.py)")
