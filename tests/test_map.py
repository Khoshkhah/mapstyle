"""mapstyle.map on a Monaco duckOSM db built by ../duckOSM: travel-mode styles
(docs/design/mode_styles.md) and feature layers (docs/design/feature_layers.md)."""

import os
import subprocess
from pathlib import Path

import pytest
import roadstyle as rs
from roadstyle import _settings

from mapstyle.map import LOOKS, MODES, load_layers, load_roads, main, mode_settings, render_map
from mapstyle.style import load_style

DUCKOSM = Path(os.environ.get("DUCKOSM_DIR") or Path(__file__).resolve().parents[2] / "duckOSM")
DUCKOSM_EXE = Path(os.environ.get("DUCKOSM_EXE") or DUCKOSM / ".venv/bin/duckosm")   # CI: its own checkout
# classes of walking / cycling networks elsewhere (Tartu, Södermalm) that Monaco lacks
PATH_CLASSES = {"footway", "path", "steps", "corridor", "platform", "pedestrian", "cycleway",
                "bridleway", "track", "living_street", "construction"}


@pytest.fixture(scope="session")
def monaco(tmp_path_factory):
    """``$MAPSTYLE_TEST_DB``, else a Monaco db with features.* built by duckOSM (~10 s)."""
    if os.environ.get("MAPSTYLE_TEST_DB"):
        return os.environ["MAPSTYLE_TEST_DB"]
    exe = DUCKOSM_EXE
    if not exe.exists():
        pytest.skip(f"needs duckOSM's duckosm at {exe} (DUCKOSM_DIR / DUCKOSM_EXE)")
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
    # the same order on every call (the page's feature ids are row numbers): edge_id order
    assert list(load_roads(monaco)["edge_id"]) == list(g["edge_id"])
    assert list(g["edge_id"].astype("int64")) == sorted(g["edge_id"].astype("int64"))


@pytest.mark.parametrize("paths", list(load_style("paths")))
@pytest.mark.parametrize("mode", LOOKS)
def test_mode_covers_every_class(monaco, mode, paths):
    """No class falls back to roadstyle's `unclassified` look or `residential` width, in any
    mode and path style."""
    name, s = mode_settings(mode, paths)
    palette, roads, defaults = s["palettes"][name], s["roads"], _settings.roads()
    group = {**defaults["group"], **roads.get("group", {})}
    classes = {c for c in load_roads(monaco)["highway"].dropna()} | PATH_CLASSES
    classes = {rs.normalize_highway(c)[0] for c in classes}
    assert classes - set(palette) == set()
    assert classes - set(group) == set()
    for g in set(group.values()):                           # a new width group is complete
        for table in ("width", "width_zoom_rate", "casing_ratio"):
            assert g in roads.get(table, {}) or g in defaults[table], (g, table)


def test_komoot_walking_draws_paths_solid_with_a_halo():
    name, s = mode_settings("walking", "komoot")
    p = s["palettes"][name]
    assert all(p[c]["dash"] is None for c in ("footway", "path", "corridor", "pedestrian"))
    assert all(p[c]["casing"] == "#ffffff" for c in ("footway", "path", "cycleway"))     # the halo
    assert "footway" not in s["config"]["minor_no_casing"]
    assert p["primary"]["fill"] != "#fcd6a4" and "opacity" not in str(load_style("modes")["walking"])
    assert "footway" not in s["roads"].get("z_order", {})              # class order, no lift


def test_one_way_streets_are_not_drawn_as_two_lanes(monaco, monkeypatch):
    """A one-way street's walking-only reverse edge doesn't make it a two-way road: only edges open
    to cars or bikes are directed (Kaveh: Rue du Castelleretto)."""
    seen = {}
    from types import SimpleNamespace
    monkeypatch.setattr(rs, "render_edges", lambda g, **kw: seen.update(kw, g=g) or SimpleNamespace(_tpl="</body>"))
    render_map(monaco, layers=False)
    g = seen["g"].set_index("edge_id")
    assert seen["directed_col"] == "is_directed"
    assert g.loc["441704187184649227", "is_directed"] and not g.loc["5990211243552773545", "is_directed"]
    assert g.loc[g.highway == "footway", "is_directed"].sum() == 0                 # paths: one line
    assert g.loc[g.driving, "is_directed"].all()                                   # every driving edge


def test_crossings_over_and_sidewalks_under_their_street(monaco, monkeypatch):
    """walk_type -> roadstyle's band_col: a crossing (zebra) over the street, a sidewalk under it
    (roadstyle/docs/design/draw_order_per_edge.md)."""
    roads = load_roads(monaco)
    assert {"crossing", "sidewalk"} <= set(roads["walk_type"].dropna())
    seen = {}
    from types import SimpleNamespace
    monkeypatch.setattr(rs, "render_edges", lambda g, **kw: seen.update(kw, g=g) or SimpleNamespace(_tpl="</body>"))
    render_map(monaco, layers=False)
    g = seen["g"]
    assert seen["band_col"] == "band"
    foot = g.highway == "footway"
    assert set(g.loc[foot & (g.walk_type == "crossing"), "band"]) == {1}
    assert set(g.loc[foot & (g.walk_type == "sidewalk"), "band"]) == {-1}
    assert g.loc[~g.walk_type.isin(["crossing", "sidewalk"]), "band"].isna().all()
    # a car road duckOSM marks "sidewalk" (you walk on its sidewalk) stays with the streets
    road = (g.walk_type == "sidewalk") & g.highway.isin(["residential", "secondary", "primary"])
    assert road.sum() > 100 and g.loc[road, "band"].isna().all()


def test_mode_reaches_render_edges(monaco, monkeypatch):
    seen = {}
    from types import SimpleNamespace
    monkeypatch.setattr(rs, "render_edges",
                        lambda g, **kw: seen.update(kw, n=len(g)) or SimpleNamespace(_tpl="</body>"))
    render_map(monaco, "cycling", layers=False, basemap="positron")
    assert seen["palette"] == "ms_cycling_google" and seen["basemap"] == "positron"
    assert seen["settings"]["roads"]["group"]["cycleway"] == "em"


def test_render_walking_page(monaco):
    html = render_map(monaco, "walking", paths="komoot").html
    assert "#b3301e" in html                                 # komoot's steps colour reached the page


@pytest.mark.parametrize("paths", list(load_style("paths")))
def test_no_class_inherits_a_dash(paths):
    """A class osm_carto.yaml and the path style draw solid stays solid (pedestrian once came out
    dashed)."""
    name, s = mode_settings("walking", paths)
    colors, style = load_style()["roads"]["colors"], load_style("paths")[paths].get("palette") or {}
    for c in ("pedestrian", "platform", "living_street", "busway", "raceway"):
        if "dash" not in colors.get(c, {}) and "dash" not in style.get(c, {}):
            assert s["palettes"][name][c]["dash"] is None, c


def test_unknown_mode_or_path_style():
    with pytest.raises(ValueError):
        mode_settings("flying")
    with pytest.raises(ValueError):
        mode_settings("walking", "crayon")


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


def test_page_scripts_parse(monaco, tmp_path):
    """mapstyle's scripts with their config filled in are valid JavaScript (a syntax error silently
    drops every icon, texture, kind colour and rs* function)."""
    import re
    import shutil
    if not shutil.which("node"):
        pytest.skip("needs node")
    html = render_map(monaco, "walking", dashboard=True).html
    js = re.findall(r"<script>((?:// mapstyle's part|// mapstyle's dashboard).*?)</script>", html, re.S)
    assert len(js) == 2
    for i, s in enumerate(js):
        (tmp_path / f"{i}.js").write_text(s)
        subprocess.run(["node", "--check", tmp_path / f"{i}.js"], check=True)


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
    exe = DUCKOSM_EXE
    if not exe.exists():
        pytest.skip(f"needs duckOSM's duckosm at {exe} (DUCKOSM_DIR / DUCKOSM_EXE)")
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


# ---- dashboard and mapstyle's rs* functions (docs/design/dashboard.md) --------------------------

def _ms(html):
    import json
    return json.loads(html.split("const MS = ", 1)[1].split(", map = window.map;", 1)[0])


def test_every_page_has_the_rs_functions(monaco):
    html = render_map(monaco, layers=["crossings"], interaction={"crossings": {"tooltip": True}}).html
    assert all(f in html for f in ("rsSetModes", "rsSetKinds", "rsSetInteraction"))
    ms = _ms(html)
    assert ms["layers"][0]["interaction"] == {"clickable": True, "tooltip": True, "popup": True}
    assert set(ms["kinds"]["crossings"]) == {"crossing"}
    assert "rsSetModes" in render_map(monaco, layers=False).html       # roads only: modes still


def test_dashboard(monaco):
    html = render_map(monaco, dashboard=True).html
    assert 'id="rp-ovs"' in html and "mapstyle's dashboard" in html   # roadstyle's report + ours
    assert '"Modes"' in html and "walking + cycling" in html           # the colour option
    landcover = next(L for L in _ms(html)["layers"] if L["label"] == "landcover")
    assert landcover["interaction"]["clickable"] is False              # decoration: today's default
    with pytest.raises(ValueError):
        render_map(monaco, dashboard=True, planner=True)


# ---- themes (docs/design/themes.md) -------------------------------------------------------------

def test_grey_theme_is_muted_except_the_water_and_green_hints():
    import colorsys
    import re
    from mapstyle.style import _walk, load_theme
    style, th, _ = load_theme("grey")
    _, settings = mode_settings("all", "google", "grey")
    hints = {"#d5dde0", "#c3cfd4", "#bcc3cc", "#e7ece5", "#e9ede7"}      # water, cycleways, green
    seen = []
    _walk([style["roads"], style["features"], settings["palettes"]], seen.append)
    cols = {c.lower() for c in seen if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)}
    sat = lambda c: colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))[2]  # noqa: E731
    assert cols and all(sat(c) <= 0.15 for c in cols - hints), sorted(c for c in cols - hints if sat(c) > 0.15)
    assert style["features"]["landcover_pattern"] == {} and th["background"] == "#f5f5f3"


def test_theme_osm_is_todays_page_and_an_unknown_theme_names_the_choices(monaco):
    assert render_map(monaco, layers=False).html == render_map(monaco, layers=False, theme="osm").html
    with pytest.raises(ValueError, match="unknown theme 'nope'; choose from \\('osm', 'google', 'grey'\\)"):
        render_map(monaco, theme="nope")
    html = render_map(monaco, theme="grey").html
    assert "blank_grey" in html and "#f5f5f3" in html


def test_cli_theme(monaco, tmp_path, capsys):
    out = tmp_path / "grey.html"
    main([str(monaco), "--theme", "grey", "--no-layers", "-o", str(out)])
    assert out.exists() and "blank_grey" in out.read_text()
