# Styles

The look is data, in four YAML files in `src/mapstyle/styles/`:

| File | Says |
|---|---|
| `modes.yaml` | per travel mode: which classes are drawn in the path style's emphasis width, whether roads are drawn as two lanes, whether the roads for cars fade, and roadstyle `roads` settings (widths by zoom, class groups, order); the dashboard's colours by mode |
| `paths.yaml` | per path style (`google`, `osm`, `komoot`, `cyclosm`): the colour, outline (halo) and dash of each path class, the emphasis width by zoom, and how far the roads for cars fade |
| `osm_carto.yaml` | the road colours (openstreetmap.org's), and each base-map layer's look: fills and outlines by `kind`, landcover textures, line colours and dashes, point icons, and the zoom each starts at |
| `themes/*.yaml` | the themes (`google`, `grey`): a background, a transform for every colour, and the colours that differ ([Themes](../guides/themes.md)) |
| `layers.yaml` | which `features.*` layers are drawn, in which order, with which filter (`where`), and which become a point at an area's centre (the parking "P") |

The road entries are roadstyle settings: see its
[settings reference](https://khoshkhah.github.io/roadstyle/reference/settings/) for every key.
