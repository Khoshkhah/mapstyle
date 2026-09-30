"""mapstyle — OSM full-base-map styling (roadstyle generalized to polygons + points)."""

from mapstyle.layers import Layer
from mapstyle.io import load_layer, load_layers
from mapstyle.render import render_basemap
from mapstyle.render_web import render_web
from mapstyle.merge import merge_modes, merge_stats, render_merge
from mapstyle.map import load_roads, render_map

__version__ = "0.0.1"
__all__ = ["Layer", "load_layer", "load_layers", "render_basemap", "render_web",
           "merge_modes", "merge_stats", "render_merge", "load_roads", "render_map",
           "__version__"]
