"""Travel-mode styles (docs/design/mode_styles.md) on a Monaco duckOSM db built by ../duckOSM."""

import os
import subprocess
from pathlib import Path

import pytest
import roadstyle as rs
from roadstyle import _settings

from mapstyle.map import MODES, load_roads, mode_settings, render_map

DUCKOSM = Path(__file__).resolve().parents[2] / "duckOSM"
# classes of walking / cycling networks elsewhere (Tartu, Södermalm) that Monaco lacks
PATH_CLASSES = {"footway", "path", "steps", "corridor", "platform", "pedestrian", "cycleway",
                "bridleway", "track", "living_street", "construction"}


@pytest.fixture(scope="session")
def monaco(tmp_path_factory):
    """``$MAPSTYLE_TEST_DB``, else a Monaco db with features.* built by duckOSM (~10 s)."""
    if os.environ.get("MAPSTYLE_TEST_DB"):
        return os.environ["MAPSTYLE_TEST_DB"]
    exe = DUCKOSM / ".venv/bin/duckosm"
    if not exe.exists():
        pytest.skip(f"needs duckOSM with its .venv at {DUCKOSM}")
    out = tmp_path_factory.mktemp("monaco")
    sample = DUCKOSM / "data/sample"
    (out / "monaco.yaml").write_text(
        f"name: monaco\noutput_path: {out}\n"
        f"source: {{type: pbf, pbf_path: {sample / 'monaco.osm.pbf'}}}\n"
        f"boundary: {{path: {sample / 'monaco.geojson'}}}\n"
        "modes: [driving, walking, cycling]\noptions: {build_features: true}\n")
    subprocess.run([exe, "build", "-c", out / "monaco.yaml"], cwd=DUCKOSM, check=True,
                   capture_output=True)
    return out / "monaco.duckdb"


def test_load_roads(monaco):
    g = load_roads(monaco)
    assert g["edge_id"].is_unique and isinstance(g["edge_id"].iloc[0], str)
    assert g[list(MODES)].any(axis=1).all()
    assert g["walking"].sum() > g["driving"].sum()          # footways and steps


@pytest.mark.parametrize("mode", MODES)
def test_mode_covers_every_class(monaco, mode):
    """No class falls back to roadstyle's `unclassified` look or `residential` width."""
    name, s = mode_settings(mode)
    palette, roads, defaults = s["palettes"][name], s["roads"], _settings.roads()
    group = {**defaults["group"], **roads.get("group", {})}
    classes = {c for c in load_roads(monaco)["highway"].dropna()} | PATH_CLASSES
    classes = {rs.normalize_highway(c)[0] for c in classes}
    assert classes - set(palette) == set()
    assert classes - set(group) == set()
    for g in set(group.values()):                           # a new width group is complete
        for table in ("width", "width_zoom_rate", "casing_ratio"):
            assert g in roads.get(table, {}) or g in defaults[table], (g, table)


def test_walking_draws_paths_solid_and_on_top():
    name, s = mode_settings("walking")
    p, z = s["palettes"][name], s["roads"]["z_order"]
    assert all(p[c]["dash"] is None for c in ("footway", "path", "steps", "corridor"))
    assert min(z[c] for c in ("footway", "steps", "platform")) > 9     # motorway = 9


def test_mode_reaches_render_edges(monaco, monkeypatch):
    seen = {}
    monkeypatch.setattr(rs, "render_edges", lambda g, **kw: seen.update(kw, n=len(g)))
    render_map(monaco, "cycling", basemap="positron")
    assert seen["palette"] == "ms_cycling" and seen["basemap"] == "positron"
    assert seen["settings"]["roads"]["group"]["cycleway"] == "cycle"


def test_render_walking_page(monaco):
    html = render_map(monaco, "walking").html
    assert "#c0392b" in html                                 # the steps colour reached the page


def test_unknown_mode():
    with pytest.raises(ValueError):
        mode_settings("flying")
