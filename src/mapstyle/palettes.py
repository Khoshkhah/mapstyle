"""Polygon / point palettes (OSM-carto-ish).

Line palettes come from roadstyle (PALETTES/THEMES). These cover what roadstyle doesn't:
area fills + outlines and point colors. Kept as a simple table for now; can grow into a
roadstyle-style Styler later.
"""

WATER = "#aad3df"
BUILDING_FILL = "#d9d0c9"
BUILDING_OUTLINE = "#c2b8ac"

LANDUSE = {
    "residential": "#e0dfdf", "commercial": "#f2dad9", "retail": "#ffd6d1",
    "industrial": "#ebdbe8", "railway": "#ebdbe8",
    "forest": "#add19e", "wood": "#add19e",
    "grass": "#cdebb0", "grassland": "#cdebb0", "meadow": "#cdebb0",
    "village_green": "#cdebb0", "greenfield": "#f1eee8",
    "farmland": "#eef0d5", "farmyard": "#f5dcba", "orchard": "#aedfa3",
    "vineyard": "#aedfa3", "allotments": "#c9e1bf",
    "park": "#c8facc", "garden": "#cfeda5", "recreation_ground": "#dffce2",
    "pitch": "#aae0cb", "playground": "#dffce2", "nature_reserve": "#d5e8d1",
    "golf_course": "#b5e3b5", "dog_park": "#e5f5cf",
    "cemetery": "#aacbaf",
    "scrub": "#c8d7ab", "heath": "#d6d99f", "wetland": "#add19e",
    "sand": "#f5e9c6", "fell": "#d6d99f", "bare_rock": "#dedede", "scree": "#e0e0e0",
    "quarry": "#c5c3c3", "brownfield": "#b6b592",
}
LANDUSE_DEFAULT = "#e8e6df"


def polygon_style(layer: str, cls):
    """Return a Leaflet path style dict (fill + outline) for one polygon feature."""
    if layer == "water":
        return {"fillColor": WATER, "color": WATER, "weight": 0, "fillOpacity": 1.0}
    if layer == "buildings":
        return {"fillColor": BUILDING_FILL, "color": BUILDING_OUTLINE,
                "weight": 0.4, "fillOpacity": 0.9}
    fill = LANDUSE.get(cls, LANDUSE_DEFAULT)
    return {"fillColor": fill, "color": fill, "weight": 0, "fillOpacity": 0.85}
