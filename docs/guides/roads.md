# How roads are drawn

<p class="lead">A road network is not a set of independent lines: roads join, cross over and under each
other, and run in two directions. mapstyle draws each edge of the duckOSM network so that junctions
read right.</p>

Every road edge stays its own feature on the page: hover it, click it, filter it or colour it by its
`edge_id`, whatever the drawing does around it.

## Two directions, two lanes

duckOSM stores a two-way street as two directed edges. They are drawn side by side, one per
direction (from zoom 15), so each can be clicked and coloured on its own, and their shared end is
drawn as one round end, not two bumps.

A one-way street is one line with arrows. duckOSM also gives it a walking-only reverse edge
(pedestrians may walk both ways); mapstyle marks that edge `is_directed = false`, so it doesn't turn
the street into a two-way road. Footways, steps and other paths are one line too, whichever way you
walk them.

<div class="ms-shots" markdown>
<figure markdown>![Two-way streets as two lanes, crossings over their street](../img/roads_crossings.jpg)<figcaption>Two-way roads as two lanes; crossings drawn over their street</figcaption></figure>
</div>

## Over and under

The OpenStreetMap `layer`, `bridge` and `tunnel` tags decide what passes over what:

- **Bridges** are drawn over the roads they cross, with square deck ends.
- **Tunnels** are ordinary roads with a tunnel style: a dashed outline and light dashes on a faded
  fill. A tunnel is at ground level, so its mouths join their street like any road continuing; it
  goes under the roads only where it really passes under one (4 m clear of the street's drawn width).
- **A road with only a `layer` tag** acts the same: it is at ground level, so a tunnel approach
  tagged `layer=-1`, or a walkway that starts at a path, still joins the road it meets, and it is
  drawn over (or under) a street only where it really crosses it.
- **How that is drawn.** Every road has a casing number (in three parts: start, main, end) and a fill number, computed by
  [roadstyle](https://khoshkhah.github.io/roadstyle/guides/levels/) from the roads' levels, the road classes and where roads meet or cross: the roads are painted number by
  number, lowest first, and at each number all casings before all fills, so joints show no ring and an overpass is over its road. If the database has
  `visualization.edge_levels` (`duckosm levels`), the page reads them; if not, they are computed while the page is made. A click on a road is its own edge.
  `render_map(pieces=True)` draws the older way: a road with a level cut into pieces, ground pieces and the stretch that passes over or under another road.
- **Crossings** (`footway=crossing`) are drawn over their street, **mapped sidewalks** under it.
- **Slip roads** (`*_link`) are drawn under the streets they join.

<div class="ms-shots" markdown>
<figure markdown>![A tunnel mouth: the road runs into the tunnel](../img/roads_tunnel.jpg)<figcaption>Tunnel Albert II: the road runs into the tunnel; the tunnel is dashed</figcaption></figure>
<figure markdown>![A raised walkway passing over a roundabout](../img/roads_walkway.jpg)<figcaption>Promenade Honoré II (a raised walkway) over Rond-Point Canton</figcaption></figure>
</div>

The **Bridges** and **Tunnels** rows in the **ROADS** box hide them.

## Roads you may not use

duckOSM keeps the roads a mode may not use apart (`private_edges`): private roads (driveways, gated
streets) and, for cars, bus-only roads and bus lanes. They are on the map in their own colour,
**grey** for private and **muted blue** for bus, each with a row in the **ROADS** box
(**Private roads**, **Bus lanes**) to hide or show them. They are never part of a route.

Which roads count depends on the map's mode: on a driving map, those cars may not use (as duckOSM's
driving map); on the map of every mode, bus lanes (even where bikes may use them) and the private
roads no mode can use. Your own colours (`rsColor`) paint over them.

## Where it comes from

This drawing is [roadstyle](https://khoshkhah.github.io/roadstyle/)'s (0.10 and later), fed by
mapstyle with what it knows from duckOSM: which edges are directed (`directed_col`), and which paths
are crossings or sidewalks (`band_col`, from duckOSM's `walk_type`), and which stretches of a road
pass over or under another (`band_col` again, with `cap_col` for their square ends).
