"""OSM Standard (openstreetmap-carto) road palette — so driving/cycling/walking match osm.org.

roadstyle's `carto` palette matches OSM for the vehicular classes but diverges on paths
(footway/path/steps salmon, cycleway blue, pedestrian lilac, construction dashed). This table
is the full openstreetmap-carto road styling, by `highway` class, used by every mapstyle
backend so the rendered roads totally match the OSM base layer.

`RoadStyle` mirrors roadstyle's ResolvedStyle fields, so backends consume it the same way.
"""

from dataclasses import dataclass

from mapstyle.style import load_style


@dataclass(frozen=True)
class RoadStyle:
    fill: str
    width: float
    casing: str | None
    casing_width: float
    dash: tuple | None = None          # (on, off) px; None = solid
    opacity: float = 1.0
    casing_opacity: float = 0.9


# per-class base (fill, casing) line-widths for the legacy line backend (render_basemap). The
# MAIN merged viewer computes PHYSICAL widths from lanes (styles/*.yaml roads.width_model — see
# docs/width-model.md); these feed only the older per-layer backend. COLOURS (fill/casing/dash) come from the stylesheet's
# roads.colors block — edit there, not here.
_BASE_W = {
    "motorway": (6.0, 8.0), "trunk": (5.2, 7.2), "primary": (4.4, 6.2),
    "secondary": (3.4, 5.0), "tertiary": (2.8, 4.0), "unclassified": (2.2, 3.2),
    "residential": (2.2, 3.2), "living_street": (1.8, 2.6), "service": (1.2, 2.0),
    "pedestrian": (1.8, 2.6), "footway": (1.0, 0.0), "path": (0.9, 0.0),
    "steps": (2.6, 0.0), "cycleway": (1.0, 0.0), "bridleway": (1.0, 0.0),
    "track": (1.2, 0.0), "construction": (1.8, 2.8), "corridor": (0.8, 0.0),
    "raceway": (1.4, 2.2), "busway": (2.0, 3.0),
}


def _build_carto(name="osm_carto"):
    """Build the class -> RoadStyle palette from the stylesheet's roads.colors (fill/casing/dash)
    combined with the per-class base widths above."""
    colors = (load_style(name).get("roads", {}).get("colors") or {})
    out = {}
    for cls, (w, cw) in _BASE_W.items():
        c = colors.get(cls, {})
        casing = c.get("casing")                       # null/absent -> no edge (path-like)
        dash = tuple(c["dash"]) if c.get("dash") else None
        out[cls] = RoadStyle(c.get("fill", "#ffffff"), w, casing,
                             cw if casing else 0.0, dash)
    return out


ROAD_CARTO = _build_carto()
_FALLBACK = ROAD_CARTO["unclassified"]


# OSM draw order: higher = rendered on top (major roads over minor over paths).
ROAD_Z = {
    "motorway": 9, "trunk": 8, "primary": 7, "secondary": 6, "tertiary": 5,
    "unclassified": 4, "residential": 4, "road": 4, "busway": 4,
    "living_street": 3, "service": 3, "pedestrian": 2,
    "track": 1, "path": 1, "footway": 1, "cycleway": 1, "bridleway": 1,
    "steps": 1, "corridor": 1, "raceway": 5, "construction": 0,
}


def road_z(highway) -> int:
    """OSM draw rank (higher = drawn in front).

    Links render BELOW all roads (openstreetmap-carto: a ramp's end must not overlap the road
    it joins), but keep class order among themselves (motorway_link over secondary_link).
    """
    if not highway:
        return 4
    h = str(highway).strip().lower()
    is_link = h.endswith("_link")
    if is_link:
        h = h[:-5]
    z = ROAD_Z.get(h, 4)
    return z - 20 if is_link else z


# highway class -> width-table group (the openstreetmap-carto width buckets)
ROAD_GROUP = {
    "motorway": "major", "trunk": "major",
    "primary": "primary", "secondary": "secondary", "tertiary": "tertiary",
    "unclassified": "residential", "residential": "residential", "road": "residential",
    "busway": "residential", "raceway": "tertiary",
    "living_street": "living_street", "service": "service", "pedestrian": "pedestrian",
    "footway": "path", "path": "path", "cycleway": "path", "steps": "path",
    "bridleway": "path", "track": "path", "corridor": "path", "construction": "path",
}


def road_group(highway) -> str:
    """Map a highway class to its openstreetmap-carto width group."""
    if not highway:
        return "residential"
    h = str(highway).strip().lower()
    if h.endswith("_link"):
        h = h[:-5]
    return ROAD_GROUP.get(h, "residential")


def resolve_road(highway, theme="light") -> RoadStyle:
    """OSM-Carto style for a highway class. `*_link` -> base class, slightly thinner."""
    if not highway:
        return _FALLBACK
    h = str(highway).strip().lower()
    is_link = h.endswith("_link")
    if is_link:
        h = h[:-5]
    rs = ROAD_CARTO.get(h, _FALLBACK)
    if is_link:
        rs = RoadStyle(rs.fill, rs.width * 0.75, rs.casing, rs.casing_width * 0.8,
                       rs.dash, rs.opacity, rs.casing_opacity)
    return rs
