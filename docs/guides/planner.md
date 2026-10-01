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
- **Fastest or shortest**, with the **total time and total distance**, split into the walk to the
  road, the trip on the roads, and the walk from the road.
- **Off the road:** a marker may be up to a set distance from a road (**Off-road up to … m**,
  default 50 m); the straight walk to the road costs walking time (**walking … km/h**, default 4.5),
  whatever the mode. That walk never crosses another road (one of the mode, or any road for cars):
  it joins the first road in its way. Each marker shows the distance as a circle, red when no road
  is in reach.
- **Exact distances:** the trip starts and ends where you put the markers, not at a road's end:
  starting halfway along a street counts half of it.
- **Turn-by-turn directions** ("At the roundabout, take the 2nd exit onto …").
- The route is drawn as its exact line, a colour per leg, the walks to the road dashed; its
  `edge_id`s are listed, ready to look up in the database.

The routing runs in the page (Dijkstra over duckOSM's turn graphs, `<mode>.edge_graph`, so turn
restrictions count), with the same answers as duckOSM's `route_points()` and
`route_multimodal_points()`.

**Walk + drive** needs duckOSM's multimodal tables: run `duckosm multimodal monaco.duckdb` once. Without
them the planner offers the three other modes and says why.

The planner page is the full mapstyle map, with the walking network in front by default so a walking
leg shows; `mode=` picks another. It can't be combined with `dashboard=True` (both use the side
panel) or `tiles=True` (the planner snaps to the roads in the page).
