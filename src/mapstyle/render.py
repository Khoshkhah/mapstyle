"""render_basemap — compose many layers onto one map (dispatch to a backend)."""

import importlib

from mapstyle.layers import Layer

_BACKENDS = {"folium": "mapstyle.render_folium", "lonboard": "mapstyle.render_lonboard"}


def render_basemap(layers: list[Layer], *, backend: str = "folium",
                   theme: str = "light", out: str | None = None, **kwargs):
    """Render `layers` (bottom -> top by z) onto one map.

    backend : "folium" (small, interactive toggles) | "lonboard" (WebGL, scales to 100k+)
    theme   : roadstyle theme — "light" | "dark" | "satellite"
    out     : if given, save the result there and still return it
    """
    mod_name = _BACKENDS.get(backend)
    if not mod_name:
        raise ValueError(f"unknown backend {backend!r}; choose {list(_BACKENDS)}")
    mod = importlib.import_module(mod_name)
    m = mod.render(layers, theme=theme, **kwargs)
    if out:
        mod.save(m, out)
    return m
