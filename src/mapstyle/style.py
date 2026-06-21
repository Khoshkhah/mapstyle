"""Load a mapstyle stylesheet (cartographic parameters) from styles/<name>.yaml.

Keeps the tunable numbers (road widths, growth rates, casing) out of code so they can be
edited and re-rendered without touching Python/JS. Add new styles as sibling YAML files.
"""

from pathlib import Path

import yaml

_STYLES = Path(__file__).parent / "styles"


def load_style(name: str = "osm_carto") -> dict:
    with open(_STYLES / f"{name}.yaml") as f:
        return yaml.safe_load(f)
