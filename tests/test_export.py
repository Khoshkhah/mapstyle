"""export_style: the base map's layers.js values go into the exported style."""
from mapstyle.export import _restyle


def test_restyle_sets_the_kind_colours_zoom_and_dash():
    style = {"layers": [{"id": "ov0-fill", "type": "fill", "source": "roads", "source-layer": "ov0", "paint": {"fill-color": "#000"}},
                        {"id": "ov0-outline", "type": "line", "source": "roads", "source-layer": "ov0", "paint": {}},
                        {"id": "ov1-line", "type": "line", "source": "roads", "source-layer": "ov1", "paint": {}},
                        {"id": "roads-fill", "type": "line", "source": "roads", "source-layer": "roads", "paint": {}}]}
    config = {"layers": [{"color_by": {"map": {"park": "#0f0"}, "default": "#eee"}, "outline_by": {"map": {}, "default": "#111"}, "min_zoom": 15},
                         {"dash": [6, 4]}]}
    _restyle(style, config)
    fill, outline, line, road = style["layers"]
    assert fill["paint"]["fill-color"] == ["match", ["get", "kind"], "park", "#0f0", "#eee"] and fill["minzoom"] == 15
    assert outline["paint"]["line-color"] == "#111" and line["paint"]["line-dasharray"] == [6, 4]
    assert road["paint"] == {}
