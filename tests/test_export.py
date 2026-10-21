"""export_style: the base map's layers.js values go into the exported style."""
from mapstyle.export import _restyle


def test_restyle_sets_the_kind_colours_zoom_and_dash():
    style = {"layers": [{"id": "ov0-fill", "type": "fill", "source": "roads", "source-layer": "ov0", "paint": {"fill-color": "#000"}},
                        {"id": "ov0-outline", "type": "line", "source": "roads", "source-layer": "ov0", "paint": {}},
                        {"id": "ov1-line", "type": "line", "source": "roads", "source-layer": "ov1", "paint": {}},
                        {"id": "roads-fill", "type": "line", "source": "roads", "source-layer": "roads", "paint": {}}]}
    config = {"layers": [{"color_by": {"map": {"park": "#0f0"}, "default": "#eee"}, "outline_by": {"map": {}, "default": "#111"}, "min_zoom": 15},
                         {"dash": [6, 4]}]}
    config["images"] = {}
    _restyle(style, config)
    fill, outline, line, road = style["layers"]
    assert fill["paint"]["fill-color"] == ["match", ["get", "kind"], "park", "#0f0", "#eee"] and fill["minzoom"] == 15
    assert outline["paint"]["line-color"] == "#111" and line["paint"]["line-dasharray"] == [6, 4]
    assert road["paint"] == {}


def test_restyle_adds_textures_and_icons_with_their_images():
    style = {"layers": [{"id": "ov0-fill", "type": "fill", "source": "roads", "source-layer": "ov0", "paint": {}, "metadata": {"roadstyle:group": "landcover"}},
                        {"id": "ov1-circle", "type": "circle", "source": "roads", "source-layer": "ov1", "paint": {}}]}
    config = {"layers": [{"patterns": {"forest": "ms-pat-forest"}}, {"icon": {"image": "ms-icon-bus", "opacity": 0.8, "size": [[16, 1.0]]}}],
              "images": {"ms-pat-forest": "data:image/png;base64,AA==", "ms-icon-bus": "data:image/svg+xml;base64,AA=="}}
    _restyle(style, config)
    ids = [x["id"] for x in style["layers"]]
    assert ids == ["ov0-fill", "ov0-pattern", "ov1-circle", "ov1-icon"]
    assert style["layers"][1]["metadata"] == {"roadstyle:group": "landcover"} and style["layers"][3]["layout"]["icon-image"] == "ms-icon-bus"
    assert style["layers"][2]["paint"]["circle-opacity"] == 0 and style["metadata"]["roadstyle:images"] == config["images"]


def test_buildings_3d_is_a_hidden_layer_over_the_roads():
    """The blocks of the buildings overlay: a fill-extrusion layer of its own group, off at first, drawn over the roads (as the page)."""
    style = {"layers": [{"id": "ov0-fill", "type": "fill", "source": "ov0", "paint": {"fill-color": "#ddd"}, "metadata": {"roadstyle:group": "buildings"}},
                        {"id": "roads-fill", "type": "line", "source": "roads", "paint": {}},
                        {"id": "roads-arrows", "type": "symbol", "source": "slots", "paint": {}}]}
    config = {"layers": [{"extrude": {"color": "#d9d0c9", "opacity": 0.9}}], "images": {}}
    _restyle(style, config)
    ids = [x["id"] for x in style["layers"]]
    assert ids == ["ov0-fill", "roads-fill", "ov0-3d", "roads-arrows"]
    b = style["layers"][2]
    assert b["type"] == "fill-extrusion" and b["layout"]["visibility"] == "none" and b["source"] == "ov0"
    assert b["metadata"]["roadstyle:group"] == "buildings 3D"
    assert b["paint"] == {"fill-extrusion-color": "#d9d0c9", "fill-extrusion-height": ["get", "height"], "fill-extrusion-opacity": 0.9}
