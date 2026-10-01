# Route planner (demo)

<p class="lead">A demo of what a mapstyle page can host: drag a start and an end, see the route. The
routing itself is duckOSM's job; this page shows it on the map.</p>

![The route planner demo: a route across Monaco](../img/planner.jpg)

[:material-map-marker-path: Try it](../maps/planner.html){ .md-button .md-button--primary }

```bash
mapstyle monaco.duckdb --planner
```

- Drive, walk, cycle, or walk + drive (needs `duckosm multimodal` on the database).
- Gives the same routes as duckOSM's `route_points()`; for routing in your own code, use duckOSM.
- Can't be combined with `dashboard=True` or `tiles=True`.
