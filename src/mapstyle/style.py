"""Load a mapstyle stylesheet (cartographic parameters) from styles/<name>.yaml.

Keeps the tunable numbers (road widths, growth rates, casing) out of code so they can be
edited and re-rendered without touching Python/JS. Add new styles as sibling YAML files.
"""

import colorsys
import re
from pathlib import Path

import yaml

_STYLES = Path(__file__).parent / "styles"


def load_style(name: str = "osm_carto") -> dict:
    with open(_STYLES / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def themes() -> tuple:
    """The theme names: ``osm`` (osm_carto.yaml as it is) and every ``styles/themes/<name>.yaml``."""
    return ("osm", *sorted(p.stem for p in (_STYLES / "themes").glob("*.yaml")))


def recolor(c, saturation=1.0, lighten=0.0):
    """A ``#rrggbb`` colour with ``saturation`` times its saturation, then ``lighten`` of the way to
    white; anything else as it is."""
    if not (isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)):
        return c
    h, l, s = colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    rgb = (x + (1 - x) * lighten for x in colorsys.hls_to_rgb(h, l, s * saturation))
    return "#" + "".join(f"{round(x * 255):02x}" for x in rgb)


def _walk(o, f):
    if isinstance(o, dict):
        return {k: _walk(v, f) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v, f) for v in o]
    return f(o)


def _merge(a, b):
    """``b`` over ``a``, dicts merged key by key (docs/design/themes.md)."""
    if not (isinstance(a, dict) and isinstance(b, dict)) or not b:
        return b                         # a value, or {} to empty a section (no textures)
    return {**a, **{k: _merge(a.get(k), v) for k, v in b.items()}}


def load_theme(theme: str = "osm"):
    """``(style, theme, color)``: osm_carto.yaml in the theme's colours (its transform on every
    colour, then its explicit ones), the theme file itself (``{}`` for ``osm``), and the transform
    as a function, for colours that come from elsewhere (roadstyle's palette, the path styles)."""
    base = load_style()
    if theme in (None, "osm"):
        return base, {}, lambda c: c
    path = _STYLES / "themes" / f"{theme}.yaml"
    if not path.exists():
        raise ValueError(f"unknown theme {theme!r}; choose from {themes()}")
    t = yaml.safe_load(path.read_text()) or {}
    tr = t.get("transform") or {}
    color = lambda c: recolor(c, **tr)  # noqa: E731
    style = _merge(_walk(base, color), {k: t[k] for k in ("roads", "features") if k in t})
    return style, t, color

