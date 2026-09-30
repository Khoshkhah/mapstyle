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


# ---- route planner (docs/design/route_planner.md) ----------------------------------------------

def _rm(html):
    import json
    return json.loads(html.split("const RM = ", 1)[1].split(";</script>", 1)[0])


def test_planner_embeds_the_turn_graph(tmp_path):
    """Ported from duckOSM's test_route_map: node ids pass 2**53, the page sees small indices."""
    import duckdb
    big, db = 2**62 + 1, tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("INSTALL spatial; LOAD spatial; CREATE SCHEMA driving")
    con.execute("CREATE TABLE driving.edges(edge_id BIGINT, osm_id BIGINT, source BIGINT, target BIGINT, "
                "name VARCHAR, highway VARCHAR, bridge BOOLEAN, tunnel BOOLEAN, layer INTEGER, "
                "oneway BOOLEAN, length_m DOUBLE, cost_s DOUBLE, geometry GEOMETRY)")
    g = lambda w: f"ST_GeomFromText('{w}')"
    con.execute(f"""INSERT INTO driving.edges VALUES
        (30, 1, 1, 2, 'A', 'residential', false, false, 0, true, 100, 10, {g('LINESTRING(7.40 43.73, 7.41 43.73)')}),
        (10, 2, 2, {big}, 'B', 'residential', false, false, 0, true, 200, 20, {g('LINESTRING(7.41 43.73, 7.42 43.73)')}),
        (20, 3, {big}, 4, NULL, 'service', false, false, 0, true, 50, 5, {g('LINESTRING(7.42 43.73, 7.43 43.73)')})""")
    con.execute("CREATE TABLE driving.edge_graph(from_edge BIGINT, to_edge BIGINT)")
    con.execute("INSERT INTO driving.edge_graph VALUES (30, 10), (10, 20)")
    con.close()

    rm = _rm(render_map(db, planner=True, layers=False).html)
    eid = [int(e) for e in load_roads(db)["edge_id"]]         # feature index k -> edge_id
    k = {e: i for i, e in enumerate(eid)}
    assert rm["modes"] == ["driving"] and rm["n"] == 3 and rm["mm"] is None
    assert all(7.40 <= p[0] <= 7.43 for p in (rm["start"], rm["end"]))
    assert rm["name"][k[10]] == "B" and rm["name"][k[20]] == ""
    assert rm["hw"][k[20]] == "service" and rm["rb"] == []   # no `junction` column: no roundabouts
    assert max(rm["src"] + rm["tgt"]) < 4                     # 4 nodes, remapped to 0..3
    assert rm["tgt"][k[10]] == rm["src"][k[20]]               # B ends where the service road starts (big)
    d = rm["graphs"]["driving"]
    nxt = {eid[a]: [eid[b] for b in bs] for a, bs in zip(d["k"], d["next"])}
    assert nxt == {10: [20], 20: [], 30: [10]}                # as edge_graph
    assert {eid[a]: c for a, c in zip(d["k"], d["cost"])} == {10: 20, 20: 5, 30: 10}


@pytest.fixture(scope="session")
def monaco_mm(monaco, tmp_path_factory):
    """Monaco with duckOSM's walk + drive tables (`duckosm multimodal`, on a copy)."""
    import shutil
    exe = DUCKOSM / ".venv/bin/duckosm"
    if not exe.exists():
        pytest.skip(f"needs duckOSM with its .venv at {DUCKOSM}")
    db = tmp_path_factory.mktemp("mm") / "monaco_mm.duckdb"
    shutil.copy(monaco, db)
    subprocess.run([exe, "multimodal", db], cwd=DUCKOSM, check=True, capture_output=True)
    return db


def test_planner_on_monaco(monaco, monaco_mm):
    rm = _rm(render_map(monaco, planner=True, layers=False).html)
    assert rm["modes"] == list(MODES) and rm["mm"] is None    # no walk + drive: the page says why
    assert all(len(rm["graphs"][m]["k"]) > 1000 for m in MODES)
    mm = _rm(render_map(monaco_mm, planner=True, layers=False).html)["mm"]
    assert len(mm["edges"]) > 10_000 and len(mm["transfers"]) > 1000


def test_planner_refuses_tiles(monaco):
    with pytest.raises(ValueError):
        render_map(monaco, planner=True, tiles=True)
