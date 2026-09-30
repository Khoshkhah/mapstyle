"""Procedural landcover textures (OpenStreetMap-Carto style): 64 px tiles of trees / graves / waves /
dots / sand / hatch / rows, drawn in a darker shade of the landcover fill, so a forest reads as green +
darker tree dots, a cemetery as green + graves, wetland as blue-green + waves.
"""
import io
import math

TILE = 64


def _trees(d):
    for cx, cy in [(16, 16), (46, 30), (28, 48), (56, 54), (6, 44)]:
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(255, 255, 255, 220))
        d.line([cx, cy + 5, cx, cy + 9], fill=(255, 255, 255, 220), width=2)


def _graves(d):
    for cx in range(12, 64, 20):
        for cy in range(12, 64, 20):
            d.line([cx, cy - 5, cx, cy + 5], fill=(255, 255, 255, 200), width=2)
            d.line([cx - 4, cy - 1, cx + 4, cy - 1], fill=(255, 255, 255, 200), width=2)


def _waves(d):
    for y in range(12, 64, 16):
        pts = [(x, y + int(3 * math.sin(x / 6.0))) for x in range(0, TILE + 1, 2)]
        d.line(pts, fill=(255, 255, 255, 205), width=2, joint="curve")


def _dots(d):
    for cx, cy in [(14, 14), (40, 20), (24, 42), (52, 50), (8, 52), (58, 10)]:
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 255, 255, 210))


def _sand(d):
    for cx, cy in [(12, 18), (36, 12), (50, 40), (20, 52), (58, 58), (30, 32)]:
        d.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=(255, 255, 255, 190))


def _hatch(d):
    for off in range(-TILE, TILE, 12):
        d.line([(off, TILE), (off + TILE, 0)], fill=(255, 255, 255, 150), width=2)


def _rows(d):                                    # orchard / vineyard — trees in rows
    for cy in (16, 40):
        for cx in range(10, 64, 16):
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 255, 255, 210))


_DRAW = {"trees": _trees, "graves": _graves, "waves": _waves, "dots": _dots,
         "sand": _sand, "hatch": _hatch, "rows": _rows}


def pattern_png(name, color):
    """One tile of pattern ``name`` drawn in ``color`` (hex) on transparent: a MapLibre
    ``fill-pattern`` image (MapLibre can't tint one, so each colour is its own tile)."""
    from PIL import Image, ImageDraw
    tile = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    _DRAW[name](ImageDraw.Draw(tile))
    out = Image.new("RGBA", tile.size, color)
    out.putalpha(tile.getchannel("A"))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()

