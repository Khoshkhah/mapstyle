"""Load duckOSM features.* layers into GeoDataFrames (the input mapstyle styles)."""

from mapstyle.layers import Layer


def load_layer(db: str, table: str, kind: str = "line", name: str | None = None,
               simplify: float | None = 2e-5) -> Layer:
    """Read features.<table> from a duckOSM .duckdb into a styled Layer.

    Reads the Shortbread ``kind`` column and exposes it as roadstyle's ``highway`` (plus a
    ``class`` alias) so the line styler and the polygon/point palettes work unchanged.
    ``simplify`` (degrees; ~2e-5 ≈ 2 m) thins vertices for a much lighter render — set None
    to keep full precision.
    """
    import duckdb
    import geopandas as gpd
    import shapely.wkt as wkt

    con = duckdb.connect(db, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    rows = con.execute(f"""
        SELECT kind, name, ST_AsText(geom) AS w
        FROM features.{table} WHERE geom IS NOT NULL
    """).fetchall()
    con.close()

    gdf = gpd.GeoDataFrame(
        {
            "highway": [r[0] for r in rows],   # roadstyle reads this for line layers
            "class": [r[0] for r in rows],
            "name": [r[1] for r in rows],
        },
        geometry=[wkt.loads(r[2]) for r in rows],
        crs="EPSG:4326",
    )
    if simplify:
        gdf["geometry"] = gdf.geometry.simplify(simplify, preserve_topology=False)
    return Layer(name or table, gdf, kind)   # color by highway class (OSM Standard)


def load_layers(db: str, specs: list[tuple[str, str]]) -> list[Layer]:
    """Load several layers at once: specs = [(table, kind), ...]."""
    return [load_layer(db, table, kind) for table, kind in specs]
