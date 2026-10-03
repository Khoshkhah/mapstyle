# Approach B: a level for each node (no cutting)

**Status:** proposal and **prototype only**, for Kaveh's decision. Nothing in the library uses it. It is the second
approach next to the cutting of `levels_plan.md` (Approach A). Idea and wording: Kaveh, 2026-10-02 ("assign an interval
to each edge ... the begin of the interval is the time for drawing the casing of the edge and the end of the interval
is the time of filling the casing with the edge colour").

## The idea

Every edge gets two times, drawn in time order: `c` (its casing) and `f` (its fill), `c < f`. Its interval is `[c, f]`.

- **Two edges that share a node** must have intersecting intervals (`c_A < f_B` and `c_B < f_A`). Each casing is then
  under the other edge's fill: the two merge cleanly at the node.
- **Two edges that cross with no shared node**, one over the other, must have disjoint intervals, the upper later
  (`f_lower < c_upper`). The upper edge is then drawn completely over the lower one, with its own casing: an overpass.
- Two edges that never cross: anything.

### It comes down to one level for each node

All edges at a node must pairwise intersect, so they share one common time there. Give each **node** a level `p`.
An edge's casing time is the **lowest** level of its two nodes and its fill time the **highest**:
`c = min(p_start, p_end)`, `f = max(p_start, p_end)`. For an overpass (upper `U`, lower `L`, no shared node) the only
requirement is: **every node of `U` has a higher level than every node of `L`**.

An edge between two nodes of the same level `k` is an ordinary edge of level `k` (casing and fill in level `k`, as in a
band). An edge between a level-0 and a level-1 node (a ramp) has its **casing with the level-0 casings and its fill with
the level-1 fills**. So its casing is under the ground roads' fills (it merges with them at the ground end) and its
fill is over them (it merges with the raised edges at the other end). Roadstyle's "band" is the special case where
casing and fill are in the same level.

### The heuristic (not necessarily correct)

1. **Pairs.** Every pair of edges whose lines cross, with no shared node and a different level tag
   (`layer`, bridge, tunnel; roadstyle's level rule): `(upper, lower)`.
2. **Cycles.** Build "this node must be above that node" for every pair (every node of the lower edge to every node
   of the upper edge). Drop the pairs whose nodes lie in one cycle (strongly connected component): no levels can
   satisfy them (a spiral ramp, an interleaved structure). What remains is acyclic.
3. **Levels.** Rank the nodes by the longest chain of "must be above" below them.
4. **Place.** For each connected part, shift all ranks by one number so that most nodes are near the level their
   edges' tags suggest (a node on a ground road: 0, else the level nearest 0 among its edges). Nodes in no pair stay 0.
5. **Draw.** One casing layer and one fill layer for each level, in level order. An edge's casing is in the layer of
   its lowest node level, its fill in the layer of its highest.

The step between levels falls on the **neighbouring edge** that joins the two levels (for a raised edge crossing a
street and joined to a ground path, the path is the ramp), not on the long edge, which stays whole.

## Test (prototype: `scripts/node_levels.py`, `scripts/node_levels_render.py`)

**The algorithm on Monaco** (12,941 edges, 4,539 nodes):

| | |
|---|---|
| crossing pairs with different levels | 1,882 |
| dropped as unsatisfiable (cycles) | 16 (0.9%) |
| pairs still violated after solving | 0 |
| node levels used | -2 … 2 (5 levels) |
| edges whose casing and fill are in the same level | 11,893 (91.9%) |
| edges that span 1 / 2 / 3 levels | 919 / 117 / 12 (8.1% together) |

(Approach A cuts about 289 edges; Approach B makes 1,048 edges span levels, but none is cut and no feature is added.)

**Drawn on synthetic scenes** (a prototype page: roadstyle's layers hidden, one casing and one fill layer for each level
added in the browser; the tunnel and bridge looks are not redone, so the tunnel is plain):

![synthetic](node_levels/synthetic.jpg)

The ramp and the raised walkway join their ground paths without a ring and pass over the street with their own
casing. The street is continuous over the tunnel.

**Drawn at the places you reported** (left: the live site; right: Approach B; tunnels are plain in the prototype):

![1](node_levels/monaco_0.jpg)
![2](node_levels/monaco_1.jpg)
![3](node_levels/monaco_2.jpg)
![4](node_levels/monaco_3.jpg)

What I see:

| Place | Approach B |
|---|---|
| tunnel crossing (`1186510750682437559`) | pedestrian street's casing continuous; the plaza ring is gone |
| junction `4070595946847136678` | clean |
| plaza edge `2727263958372164090` | ring gone |
| Avenue de Fontvieille | clean, no ring |
| `2694529092516317559` / `5213788470366489481` | the slip road joins the tunnel as one road: **correctly connected** |
| `7652029510735114293` / `5566772266206780522` | joined, no ring: **correctly connected** |
| `5066803562804960394` / `3639438131486059958` | **wrong**: the tunnel is drawn over the pedestrian band that should pass over it |
| `4070595946847136678` / `7270978127836132176` | bands over the road, each with its own casing |
| (two places) | a **white round blob** where a tunnel's round end shows over a pedestrian band's casing |

## Optimization version (solved with a solver)

Kaveh, 2026-10-02: "make it as an optimization problem and solve it by a solver ... and use your approach for
initialization". Prototype: `scripts/node_levels_opt.py`, solver OR-Tools CP-SAT (installed outside the repository for
the test; not a dependency of mapstyle).

### The formula, exactly as given to the solver

**Data**

- `N`: the nodes. `E`: the edges, `e = (s_e, t_e)`, with a level tag `lvl_e` (the `layer` if nonzero, else a bridge 1,
  else a tunnel -1, else 0) and a length `len_e` in metres. `nodes(e) = {s_e, t_e}`.
- `P`: the overpass pairs `q = (U_q, L_q)`: two edges whose lines cross, with no node in common and different tags.
  `U_q` is the one with the higher tag. (The first runs had only these pairs: see "What pairs the solver was given".)
- `pref_n`: the level the tags suggest for node `n`: the tag level nearest 0 among the edges at `n` (so 0 if a ground
  edge touches it), clamped to `[-K, K]`.
- `c_e = max(1, round(len_e / 5))`: what one level step costs on edge `e` (a long edge costs more, so a step lands on a
  short edge).

**Variables**

- `p_n` in `{-K, ..., K}` for each node (K = 4): the level of the node.
- `v_q` in `{0, 1}` for each pair: 1 means the overpass is given up.
- `d_e = |p_(s_e) - p_(t_e)|` and `r_n = |p_n - pref_n|`: auxiliary variables (`0 .. 2K`), tied to the above by the
  solver's absolute-value constraint.

**Constraints**, for every pair `q`, every `u` in `nodes(U_q)` and every `l` in `nodes(L_q)`:

```
v_q = 0   implies   p_u - p_l >= 1
```

**Objective** (minimize):

```
W1 * sum_q v_q   +   W2 * sum_e c_e * d_e   +   W3 * sum_n r_n          W1 = 1000, W2 = 10, W3 = 1
```

In words: first, as few given-up overpasses as possible; then as few level steps as possible, on short edges; then as
close to the tags as possible.

**Start (warm start):** the heuristic's solution as a hint: `p_n` = its level, `v_q = 1` for the pairs it dropped.

**Reading the answer:** casing level of `e` = `min(p_s, p_t)`, fill level = `max(p_s, p_t)`, as before.

**Solver settings:** CP-SAT, 8 workers, time limit 60 s (a 90 s run also tried). It does not prove optimality in that time.

### What pairs the solver was given, and what it was not

Kaveh, 2026-10-02: "so you didn't give the solver the list of crossing pairs?" and "if you add more than the exact
crossing pairs it is OK too: a list of *possible* crossings is good; it is better than considering all pairs."
In Monaco there are:

| Kind of pair | Count | In the first runs | Later runs |
|---|---|---|---|
| lines cross, no shared node, **different** level tags (overpass) | 1,882 | yes | yes |
| lines cross, no shared node, **same** level tag (a zebra, a missing junction) | 344 | **no** | yes: `S_q`, either edge may be on top |
| no crossing, no shared node, different tags, drawn widths overlap (the 1.3 m case) | 3,785 (76 touch or overlap exactly) | **no** | yes, as overpass pairs ("possible crossings") |
| share a node **and** cross somewhere else | 105 | no | **no**: the model cannot say it (see below) |

**Same-level crossings (`S_q`).** Each gets a boolean `o_q` ("a is on top") and a give-up variable `w_q`:
`w_q = 0 and o_q  implies  p_a - p_b >= 1` for every node pair, `w_q = 0 and not o_q  implies  p_b - p_a >= 1`; cost
`W1S * w_q` with `W1S = 300` (less than an overpass: these are often data errors).

**Why 105 pairs cannot be given.** Two edges that share a node must have intersecting intervals (that is how they
merge), and two edges that cross in their middle must have disjoint intervals. Both cannot hold. In the model a
node-sharing pair is simply "connected". Such an edge needs the cutting of Approach A.

### Result on Monaco, crossing pairs only

| | heuristic | solver, crossing pairs | solver, crossing + "drawn widths overlap" pairs |
|---|---|---|---|
| pairs | 1,882 | 1,882 | 5,667 |
| pairs given up | 16 dropped | **9** | 334 (5.9%); the heuristic's start dropped 1,125 |
| edges that span 1 or more levels | 1,048 | **766** (60 s: objective 26,761, bound 23,565; 90 s: 25,059, bound 23,560) | 1,315 |
| node levels used | -2 .. 2 | -3 .. 2 | -4 .. 4 |

The solver is better than the heuristic on both counts, but it is not proven optimal (the gap to its bound is 6 to 12%).
Adding the "drawn widths overlap" pairs (the C1 rule of `levels_plan.md`) makes the problem much harder: three times
the pairs and many conflicts. As a node-level problem it does not look usable as it stands.

### Result with the pairs added

| | heuristic | solver, overpass crossings | solver, + same-level crossings | solver, + same-level + possible crossings (all candidates) |
|---|---|---|---|---|
| overpass pairs | 1,882 | 1,882 | 1,882 | 5,667 |
| same-level pairs | not used | not used | 344 | 344 |
| overpass pairs given up | 16 (dropped) | 9 | 9 | 338 to 341 (6%) |
| same-level pairs given up | | | 0 | 4 to 12 |
| edges that span 1 or more levels | 1,048 | 766 | 1,209 | 1,729 (13.4%) |
| node levels used | -2 .. 2 | -3 .. 2 | -3 .. 2 | -4 .. 4 |
| solver, time and result | none | 60 s, objective 26,761, bound 23,565 | 100 s, objective 32,846, bound 23,560 | 120 s, objective 393,404, bound 359,988 |

Adding the same-level crossings costs about 440 more edges that span a level and gives up no pair. Adding the
possible crossings multiplies the pairs by three, the solver gives up 6% of the overpasses, and a seventh of the edges
span levels.

### Drawn at your places: live site, solver with crossing pairs, solver with all candidate pairs

![c0](node_levels/cand_0.jpg)
![c1](node_levels/cand_1.jpg)
![c2](node_levels/cand_2.jpg)
![c3](node_levels/cand_3.jpg)

- **The extra pairs did not fix `5066803562804960394` / `3639438131486059958`.** Even though the pair is now a
  constraint, the pedestrian band is still drawn under the tunnel: the solver gave that pair up (it is among the 338
  to 341).
- **They made another place worse.** At the tunnel crossing, with all candidate pairs, a pedestrian band
  (Promenade Honoré II) is drawn as a grey area: its casing is in a higher level than its fill is drawn, because that
  edge now spans three levels.
- **So the best result so far is the solver with the overpass crossings only**, which is clean at seven of the eight
  places, and the same wrong place.

### Drawn at your places: live site, heuristic, solver (overpass crossing pairs only)

![a](node_levels/opt_0.jpg)
![b](node_levels/opt_1.jpg)
![c](node_levels/opt_2.jpg)
![d](node_levels/opt_3.jpg)

- The solver **removes the white round end** the heuristic left at the tunnel crossing and at the plaza edge.
- Clean at the tunnel crossing, `4070595946847136678`, the plaza edge, Avenue de Fontvieille.
- The slip road and the tunnel join as one connected road in both pairs (`2694…`/`5213…`, `7652…`/`5566…`); where
  their widths differ there is a small shoulder in the casing.
- **Still wrong:** `5066803562804960394` / `3639438131486059958`. The pair does not cross (the lines are 1.3 m apart), so
  neither the heuristic nor the solver has a constraint for it. Only the "drawn widths overlap" version would, and that
  version is the hard one above.

## What it needs

- **Roadstyle:** an edge's casing and fill in different levels (two new columns, a small extension of `band_col`), and
  more than three levels (here 5; layers `roads-casing-<level>` and `roads-fill-<level>`). Tunnel and bridge looks
  (dashes, deck) would have to follow the levels.
- **mapstyle:** the node levels (a spatial join for the pairs, a graph step: about 100 lines).

## Weaknesses found

1. **Only crossings are constrained.** A tunnel that runs next to a band without the lines crossing (1.3 m apart,
   `5066…` / `3639…`) is "free", so it can be drawn over the band. Adding the pairs whose drawn widths overlap (the
   C1 rule of `levels_plan.md`, a rule change that needs your permission in either approach) was tested: it did not
   fix that pair and made another place worse.
   Also, 105 pairs share a node and cross elsewhere: the model cannot express them.
2. **Cycles** (16 pairs for the heuristic, 9 for the solver) cannot be solved by levels. They need a fallback (the
   cutting of Approach A for those few edges).
3. **A blob** (round end of an edge shown over another edge's casing) at two places with the heuristic; the solver's
   levels do not show it at the places I looked at.
4. **Many edges span levels** (8.1%) and so their fills are drawn above all fills of the lower levels between their
   nodes; for an edge that touches other roads without a shared node that can show.
5. **The tunnel and bridge looks** are not done in the prototype.

## Decision for Kaveh

- **A (cutting)**: built on local branches; edges are cut; needs changes C1–C5 approved (`levels_plan.md`).
- **B (node levels)**: no cutting, a small graph step, a roadstyle extension; the weaknesses above are open.
- **A + B**: B for most edges, A's cutting only for the cycles and the places B cannot fix.

Nothing in this document is built into the library. The prototype scripts are in `scripts/` and are not imported
anywhere.
