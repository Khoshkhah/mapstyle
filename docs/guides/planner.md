# Route planner

<p class="lead">Drag a start and an end: the page finds the route itself, with no server.</p>

![The route planner: a driving route across Monaco with turn-by-turn directions](../img/planner.jpg)

[:material-map-marker-path: Try it](../maps/planner.html){ .md-button .md-button--primary }

```bash
mapstyle monaco.duckdb --planner          # -> monaco_walking.html
```

```python
ms.render_map("monaco.duckdb", planner=True)
ms.render_map("monaco.duckdb", mode="cycling", planner=True)
```

## What it does

- **Modes:** Drive, Walk, Cycle, and **Walk + drive** (walk to a car, drive, walk from it).
- **Fastest or shortest**, with the time and length of the trip.
- **Turn-by-turn directions** ("At the roundabout, take the 2nd exit onto …").
- The route is drawn on the map, a colour per leg, and its `edge_id`s are listed, ready to look up
  in the database.
- Each marker snaps to the nearest road its mode can use.

The routing runs in the page (Dijkstra over duckOSM's turn graphs, `<mode>.edge_graph`, so turn
restrictions count), with the same answers as duckOSM's own `route()`.

**Walk + drive** needs duckOSM's multimodal tables: run `duckosm multimodal monaco.duckdb` once. Without
them the planner offers the three other modes and says why.

The planner page is the full mapstyle map, with the walking network in front by default so a walking
leg shows; `mode=` picks another. It can't be combined with `dashboard=True` (both use the side
panel) or `tiles=True` (the planner snaps to the roads in the page).
