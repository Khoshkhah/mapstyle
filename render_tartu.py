#!/usr/bin/env python3
"""Render a duckOSM `features.*` db as a filterable web map with per-zoom road widths,
street names and oneway arrows (mapstyle's render_web_features).

Usage:
    python render_tartu.py <duckosm_db_with_features.*> [out_dir] [port]
Then open the printed link (serve it if a port is given).

The db must have a `features.*` schema (build with duckOSM `options.build_features: true`,
which now clips with osmium `smart` so multipolygons like rivers come out as polygons).
"""
import sys

import duckdb
import geopandas as gpd
import shapely.wkt as wkt

from mapstyle.layers import Layer
from mapstyle.render_web_features import render_web_features, write_serve

DB = sys.argv[1] if len(sys.argv) > 1 else "../duckOSM/data/db/tartu.duckdb"
OUT = sys.argv[2] if len(sys.argv) > 2 else "render/tartu_features"
PORT = sys.argv[3] if len(sys.argv) > 3 else None

# features.<table>  ->  (mapstyle layer name the palette/z-order knows, geometry kind)
SPECS = [("land", "landcover", "polygon"), ("water_polygons", "water", "polygon"),
         ("water_lines", "waterways", "line"), ("sites", "parking", "polygon"),
         ("buildings", "buildings", "polygon"), ("streets", "roads", "line")]


def load_feat(table, name, kind):
    con = duckdb.connect(DB, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    if name == "roads":                                  # roads also need oneway (arrows) + name (labels)
        rows = con.execute(f"SELECT kind, name, map_extract(tags,'oneway')[1], ST_AsText(geom) "
                           f"FROM features.{table} WHERE geom IS NOT NULL").fetchall()
        con.close()
        gdf = gpd.GeoDataFrame(
            {"highway": [r[0] for r in rows], "class": [r[0] for r in rows], "name": [r[1] for r in rows],
             "oneway": [str(r[2]).lower() in ("yes", "1", "true", "-1") for r in rows]},
            geometry=[wkt.loads(r[3]) for r in rows], crs="EPSG:4326")
    else:
        rows = con.execute(f"SELECT kind, name, ST_AsText(geom) "
                           f"FROM features.{table} WHERE geom IS NOT NULL").fetchall()
        con.close()
        gdf = gpd.GeoDataFrame(
            {"highway": [r[0] for r in rows], "class": [r[0] for r in rows], "name": [r[1] for r in rows]},
            geometry=[wkt.loads(r[2]) for r in rows], crs="EPSG:4326")
    if len(gdf):
        gdf["geometry"] = gdf.geometry.simplify(2e-5, preserve_topology=False)
    return Layer(name, gdf, kind)


layers = [load_feat(t, n, k) for t, n, k in SPECS]
for L in layers:
    if L.name == "waterways":
        L.color = "#4a90d9"                              # river/streams blue (not road-styled)

render_web_features(layers, OUT, basemap="none", names=True, arrows=True,
                    title="mapstyle — features (per-zoom roads, names, arrows)")
serve = write_serve(OUT)
print(f"rendered -> {OUT}/index.html")
print(f"serve    -> python {serve}" + (f" {PORT}" if PORT else ""))
