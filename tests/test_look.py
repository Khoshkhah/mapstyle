"""export_look: the base-map look for the roadstyle GeoLibre plugin, from layers.yaml and the theme."""
import pytest

from mapstyle.look import _where, export_look
from mapstyle.style import load_style, load_theme


def test_one_look_per_features_table(tmp_path):
    look = export_look(tmp_path / "look.json")
    assert (tmp_path / "look.json").exists()
    tables = {s["table"] for s in load_style("layers")["layers"] if s.get("show", True) and not s.get("centroid")}
    assert set(look["files"]) == {f"features_{t}" for t in tables}
    assert look["order"][0] == "ocean" and set(look["order"]) == tables
    assert [d["layer"] for d in look["not_drawn"]] == ["parking_p"]
    sites = {la["id"] for la in look["files"]["features_sites"]["layers"]}
    assert {"institutional", "parking", "bus_station", "platform"} <= sites
    assert all("source" not in la for f in look["files"].values() for la in f["layers"])


def test_colors_and_filters_come_from_the_config():
    look = export_look(theme="grey")
    st = load_theme("grey")[0]["features"]
    b = next(la for la in look["files"]["features_buildings"]["layers"] if la["id"] == "buildings")
    assert b["paint"]["fill-color"] == st["areas"]["buildings"]["fill"] and b["minzoom"] == st["areas"]["buildings"]["min_zoom"]
    rail = look["files"]["features_streets"]["layers"][0]
    assert rail["filter"][2][0] == "in" and "tram" in rail["filter"][2][2][1]


def test_unknown_where_stops():
    assert _where("kind = 'a'") == ["==", ["get", "kind"], "a"]
    with pytest.raises(ValueError, match="kind IN"):
        _where("name LIKE 'x%'")


def test_hover_and_popup_come_from_the_config():
    from roadstyle import _settings
    look = export_look()
    b = look["files"]["features_buildings"]
    assert b["hover"]["id"] == "osm_id" and b["hover"]["layers"][0]["paint"]["line-color"] == _settings.theme()["selection"]["hover"]
    assert b["popup"] == {"title": "name", "columns": [c for c in load_style("layers")["popup"] if c != "name"]}
