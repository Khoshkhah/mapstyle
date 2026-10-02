# Level of a road: from the graph, not the `layer` tag

**Status:** superseded by `levels_plan.md` (pieces, same day); first approved by Kaveh 2026-10-02 (plain-`layer` roads only; the join is fine) and implemented (`load_roads`' `level_band`, `render_map`'s `band`). roadstyle is not changed.

## Problem

mapstyle passes OSM `layer` to roadstyle, which puts a road with `layer > 0` in the high band and
`layer < 0` in the low band. A road tagged `layer=1` that joins ground roads at its end node is then
drawn over them: its casing cuts their casing, leaving a gap and a casing stub at the junction. The
roads look unconnected although the graph connects them (Monaco: `4070595946847136678`, a footway
tagged `layer=1`, joined at node `6232893203` to two footways with no `layer`).

Same cause, other place: the footway `7641129831729739830` crossing the tunnel
`1186510750682437559` shows its casing cut. That one is roadstyle's tunnel stretches and is fixed on
roadstyle's `levels-and-looks` branch (not released); this note does not touch it.

## Rule

mapstyle sets `band_col` for every road with a `layer` tag and no `bridge` / `tunnel` tag:

- **high (1)** if it really crosses a road at a lower level that is not underground
  (its level `lb` with `0 <= lb < level`);
- **low (-1)** if it really crosses a road at ground level or above (`lb >= 0`);
- **ground (0)** otherwise.

"Really crosses" = the lines cross and the two edges share no node (a shared node is a junction).
Roads with a `bridge` or `tunnel` tag, crossings and sidewalks keep today's rule. One rule, no list
of cases: nothing reads `walk_type`, highway class or tag combinations.

## Monaco, counted (`/tmp/monaco_docs6`, 12,789 edges)

- 912 edges have a `layer` tag; 282 of them have no `bridge` / `tunnel`.
- Rule on all 912: 582 go to ground, 64 high, 266 low. Rule on the 282 untagged ones only (proposed):
  252 go to ground (footway 156, steps 24, pedestrian 24, service 8, tertiary 3, primary 1; the
  rest is shown in the gallery), the others keep their band.
- `4070595946847136678` crosses only tunnels (levels -1, -2), which the low band already draws
  under it, so it goes to ground and the junction is clean (gallery: `render/casing/cmp4.png`).

## Open questions (Kaveh)

1. Only the 282 plain-`layer` roads (proposed), or also tunnels and bridges? Moving the 330 tagged
   ones to ground would draw a bridge over water, which crosses no road, without its deck.
2. Level of a road that crosses another road at the same `layer` (rare, bad data): ground.
3. Cost: one spatial self-join in `load_roads` (6 s on Monaco with every layered edge; only
   layered edges need testing). To be timed on `stockholm_county` before merging.

## Checks

- A test: a `layer=1` footway sharing a node with ground roads goes to ground; one that crosses a
  ground road stays high; one over a tunnel only goes to ground.
- Before / after gallery of every moved class, rebuilt for all preview pages (Kaveh's rule), before merge.
- README / skill / docs untouched unless the API changes (it does not).
