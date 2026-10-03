# Selecting each direction of a two-way road

**Status:** proposal, waiting for Kaveh's sign-off (2026-10-02). Nothing is coded. roadstyle is not changed.

## Problem

A two-way road is two directed edges (the *twins*). roadstyle draws them side by side and a click picks the top
feature in a small box (`pick`: `queryRenderedFeatures`, `HIT` px). On Monaco's way 982061461 (edges `98602…` and `6651…`):

| zoom | the two directions are | a click |
|---|---|---|
| 17–18 | 6–10 px apart | the same one wins over most of the road |
| 20 | about 40 px each | each one is hit on its own side |

So at the zooms people use, one direction (the same one) is selected and the other cannot be reached.
(A direction can have many lanes; this is about directed edges, not lanes.)

## Proposal (in mapstyle's `layers.js` / `dashboard.js`, roadstyle unchanged)

1. `load_roads` gives every edge a `twin`: the `edge_id` of its reverse edge (target→source, same way), or none.
2. When the selected road has a `twin`, the details panel (dashboard) and the planner's "Clicked road" line show both:
   `98602… 1868754484 → 258072562 (selected)` and `6651… 258072562 → 1868754484 [select]`.
   `[select]` selects the other directed edge (`rsSelect` on its feature id; highlight, Street View heading and copy follow it).
3. Clicking the same spot again also switches to the twin.

No arrows are added. Check: browser test on Monaco (click, switch, highlight, copied `edge_id`), plus the existing tests.

## Question

Is a switch in the panel (and click again) what you want, or do you want the click itself to choose by side at every zoom?
