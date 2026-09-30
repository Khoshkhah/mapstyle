"""mapstyle.map on a Monaco duckOSM db built by ../duckOSM: travel-mode styles
(docs/design/mode_styles.md) and feature layers (docs/design/feature_layers.md)."""

import os
import subprocess
from pathlib import Path

import pytest
import roadstyle as rs
from roadstyle import _settings

from mapstyle.map import MODES, load_layers, load_roads, main, mode_settings, render_map
from mapstyle.style import load_style

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
    render_map(monaco, "cycling", layers=False, basemap="positron")
    assert seen["palette"] == "ms_cycling" and seen["basemap"] == "positron"
    assert seen["settings"]["roads"]["group"]["cycleway"] == "cycle"


def test_render_walking_page(monaco):
    html = render_map(monaco, "walking").html
    assert "#c0392b" in html                                 # the steps colour reached the page


def test_unknown_mode():
    with pytest.raises(ValueError):
        mode_settings("flying")


def test_every_layer_has_a_style():
    st, here = load_style()["features"], Path(__file__).resolve().parents[1] / "src/mapstyle"
    for s in load_style("layers")["layers"]:
        name = s.get("merge_into") or s["name"]
        if s["kind"] == "polygon":
            assert name in st["areas"], name
        elif s["kind"] == "line":
            assert name in st["lines"], name
        elif "icon" in st["points"].get(name, {}):
            assert (here / "icons" / st["points"][name]["icon"]).exists(), name


def test_load_layers(monaco):
    fcs = load_layers(monaco)
    assert "institutional" not in fcs                       # merged into landcover
    assert {"hospital", "grass"} <= {f["properties"]["kind"] for f in fcs["landcover"]["features"]}
    b = ["bearing" in f["properties"] for f in fcs["crossings"]["features"]]
    assert sum(b) > 0.9 * len(b)                             # Monaco: 546 of 553
    assert fcs["parking_p"]["features"][0]["geometry"]["type"] == "Point"    # centroid
    assert list(load_layers(monaco, ["crossings"])) == ["crossings"]


def test_no_features_is_roads_only(tmp_path, caplog):
    import duckdb
    duckdb.connect(str(tmp_path / "empty.duckdb")).close()
    assert load_layers(tmp_path / "empty.duckdb") == {}
    assert "no features.*" in caplog.text


def test_page_has_overlays_and_script(monaco):
    html = render_map(monaco, "walking").html
    assert "__MS__" not in html and "ms-icon-crossings" in html and "ms-pat-forest" in html
    assert "window.RS_OVERLAYS" in html
    plain = render_map(monaco, "walking", layers=False).html
    assert "ms-icon-crossings" not in plain


def test_cli(monaco, tmp_path, capsys):
    main([str(monaco), "--mode", "walking", "--no-layers", "-o", str(tmp_path / "m.html")])
    assert (tmp_path / "m.html").stat().st_size > 100_000
    assert capsys.readouterr().out.strip() == str(tmp_path / "m.html")


def test_page_script_parses(monaco, tmp_path):
    """layers.js with its config filled in is valid JavaScript (a syntax error silently drops
    every icon, texture and kind colour)."""
    import re
    import shutil
    if not shutil.which("node"):
        pytest.skip("needs node")
    html = render_map(monaco, "walking").html
    js = re.search(r"<script>(// mapstyle's feature layers.*?)</script>", html, re.S).group(1)
    (tmp_path / "layers.js").write_text(js)
    subprocess.run(["node", "--check", tmp_path / "layers.js"], check=True)
