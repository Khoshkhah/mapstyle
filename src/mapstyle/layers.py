"""A Layer = one styled map layer (a GeoDataFrame + how to draw it)."""

from dataclasses import dataclass
from typing import Any

# default bottom -> top draw order by layer name (duckOSM features.* / Shortbread names).
# streets merges roads + rail (Shortbread); per-mode routing overlays keep their own ids.
Z_ORDER = {
    "land": 10, "water_polygons": 20, "water_lines": 25, "sites": 28, "buildings": 30,
    "streets": 50, "roads_driving": 50, "roads_walking": 51, "roads_cycling": 52,
    "place_labels": 90, "pois": 91, "public_transport": 92,
}


@dataclass
class Layer:
    """One renderable layer.

    name    : layer id (also picks the default z-order + polygon palette bucket)
    gdf     : GeoDataFrame in EPSG:4326 (roads need a `highway` column)
    kind    : "line" | "polygon" | "point"
    palette : roadstyle palette for line layers ("carto" | "highsat")
    z       : draw order (defaults from Z_ORDER by name)
    """
    name: str
    gdf: Any
    kind: str = "line"
    palette: str = "carto"
    z: int | None = None
    color: str | None = None   # solid override (distinct per-mode color); None = palette/class color

    def __post_init__(self):
        if self.z is None:
            self.z = Z_ORDER.get(self.name, 40)


# distinct, toggleable colors per road mode (driving keeps the OSM class palette)
MODE_COLOR = {"roads_cycling": "#2b6cb0", "roads_walking": "#d95f0e"}
