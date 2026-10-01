# Get started

<p class="lead">From an OpenStreetMap extract to an interactive map in three commands.</p>

## 1. Install

```bash
pip install "duckosm @ git+https://github.com/Khoshkhah/duckOSM" \
            "mapstyle @ git+https://github.com/Khoshkhah/mapstyle"
```

mapstyle needs Python 3.10+. It installs [roadstyle](https://pypi.org/project/roadstyle/) from PyPI;
add `"mapstyle[tiles] @ git+…"` for [vector tiles](#big-areas).

## 2. Build a database with duckOSM

mapstyle's only input is a [duckOSM](https://github.com/Khoshkhah/duckOSM) database: the road
networks and the base-map layers of an area, in one DuckDB file.

```bash
curl -LO https://download.geofabrik.de/europe/monaco-latest.osm.pbf
duckosm build --pbf monaco-latest.osm.pbf -o monaco.duckdb \
              -m driving -m walking -m cycling
```

Any extract works: [Geofabrik](https://download.geofabrik.de/) has every country and region, and
duckOSM can cut a city out of a bigger file by its boundary (see its documentation). The base-map
layers are built by default; the sea comes from Overture Maps' ocean polygons and needs the network
while building.

## 3. Draw the map

=== "Command line"

    ```bash
    mapstyle monaco.duckdb                    # -> monaco_all.html: the whole map
    mapstyle monaco.duckdb --mode walking     # the walking network in front
    mapstyle monaco.duckdb --planner          # + a route planner
    mapstyle monaco.duckdb --dashboard        # a dashboard with filters
    ```

=== "Python"

    ```python
    import mapstyle as ms

    ms.render_map("monaco.duckdb").save("monaco.html")
    ms.render_map("monaco.duckdb", mode="cycling", paths="cyclosm").save("cycling.html")
    ```

    In Jupyter, `ms.render_map(...)` on the last line of a cell shows the map in the notebook.

Open the HTML file in any browser. It works offline: the data, the styles and the code are all in
the file (the optional raster base maps in the switcher are the only thing loaded from the web).

## What's on the page

- **ROADS** (top left): show or hide each road class, bridges and tunnels.
- **LAYERS** (under it): show or hide each base-map layer. Both boxes start folded: click a title to
  open it.
- Hover a road for its `edge_id`, OSM id, class and name; click a road or a feature for its details.
  The `edge_id` is duckOSM's, ready to look up in the database.
- Top right: zoom, compass, **3D**, Street View, and the base-map switcher.

## Big areas

A city like Monaco or Tartu fits in one page (3-12 MB). For a region, draw the roads as vector tiles
inside the page:

```bash
pip install "mapstyle[tiles] @ git+https://github.com/Khoshkhah/mapstyle"
mapstyle stockholm.duckdb --tiles
```

## Next

- [Travel modes & path styles](guides/modes.md): which network stands out, and how paths look.
- [The base map](guides/base-map.md): the layers, and how to change them.
- [Gallery](gallery.md): live maps to try.
