# Dashboard panel: a shorter, grouped Filter

**Status:** approved 2026-10-02 (Kaveh: groups by meaning: Nature and water, Buildings and places, Transport; the legend is dropped when
colouring by class) and implemented in `dashboard.js`. The cards, mode chips and compact summary were added in the same pass.
roadstyle and duckOSM are not changed: the work is in `dashboard.js` (and its CSS), over roadstyle's report markup.

## What is wrong now (Monaco, 18 layers)

The panel is about 2000 px tall. In *Filter*:

1. **Every layer takes two rows**: its check box, then a `▸ clicks, kinds` line with a rule under it. 18 layers = 36 rows.
2. **One flat list**: ocean, buildings, traffic signals and bicycle parking sit together, in draw order, with no grouping.
3. **No all / none** for the layers (the kinds inside one layer have it).
4. **The legend and the Road type list repeat each other**: both list the 16 classes with the same colour swatches.
5. Roads, layers and road types are three headings in one long scroll; nothing folds.

## Proposal

```
▾ Roads                         all · none
    ☑ driving 2,765   ☑ walking 10,952   ☑ cycling 10,274
    ☑ private roads 152   ☑ bus lanes 18
    ▾ Road type (= the legend)
      ☑ ▮ primary 212 ...
▾ Areas  (6/6)                  all · none
    ☑ ▮ ocean                          ⚙
    ☑ ▮ landcover                      ⚙
    ...
▸ Lines  (3/3)
▸ Points (5/5)
```

1. **One row per layer**: check box, colour swatch, name, and a small `⚙` at the right. The `⚙` opens the
   clickable / tooltip / popup switches and the kinds (today's `clicks, kinds` content) under the row; closed by default.
2. **Groups by geometry**: Areas, Lines, Points (known from the layer's style: `areas` / `lines` / `points`),
   each folding, with `n/m` on and `all · none`. Roads is the first group; it holds modes, private / bus and the road types.
3. **The legend goes into Road type**: when *Colour by* is road class, the Road type rows already show the swatches,
   so the separate *Legend* list is dropped for that colouring; for other colourings it stays.
4. **Open by default**: Roads and Areas; Lines and Points folded. The state is kept in the page only.
5. Same data, same JS calls (`rsSetOverlay`, `rsSetKinds`, `rsSetInteraction`, `rsSetModes`, `rsSetClasses`); no API change.

Expected height on Monaco: about 900 px with Lines and Points folded (from about 2000).

## Check

`scripts/dashboard_check.py` (filters still act), a screenshot of the panel before / after, and the existing tests.

## Questions for Kaveh

1. Groups by geometry (Areas / Lines / Points) — right, or by meaning (Nature, Buildings, Transport)?
2. Drop the separate Legend when colouring by class (it repeats Road type) — yes?
