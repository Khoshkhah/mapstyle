# JavaScript API

Every mapstyle page is a roadstyle page, so roadstyle's whole
[JavaScript API](https://khoshkhah.github.io/roadstyle/reference/javascript/) works on it:
`rsQuery`, `rsFilter`, `rsColor`, `rsSetClasses`, `rsSetOverlay`, the `rs:select` event, and
`window.map` (the MapLibre map). mapstyle adds, in the same style:

| Function | Does | Fires |
|---|---|---|
| `rsSetModes(list)` | show the roads any of these modes can use (`["walking", "cycling"]`); `null` = all. Combines with `rsSetClasses`; it uses `rsFilter` on the roads, so a later `rsFilter(ids)` replaces it | `rs:filterchange` (`modes`) |
| `rsGetModes()` | the modes shown, or `null` for all | |
| `rsSetAccess(kind, on)` | show or hide the roads you may not use: `"private"`, `"bus"`, `"pedestrian"` or `"delivery"`; combines with `rsSetModes` | `rs:filterchange` (`access`, `visible`) |
| `rsGetAccess()` | `{private: bool, bus: bool}`: shown or not | |
| `RS_ACCESS` | `{kind: count}` of those roads on the page | |
| `rsSetKinds(layer, list)` | show only these `kind`s of a base-map layer (`["park", "grass"]`); `null` = all | `rs:filterchange` (`overlay`, `kinds`) |
| `rsGetKinds(layer)` | the kinds shown, or `null` for all | |
| `RS_KINDS` | `{layer: {kind: count}}` | |
| `rsSetInteraction(layer, {clickable?, tooltip?, popup?})` | switch a layer's clicks, hover tooltip and click popup; keys left out keep their state. Roads are always clickable | `rs:interactionchange` (`overlay`, `clickable`, `tooltip`, `popup`) |
| `rsGetInteraction(layer)` | `{clickable, tooltip, popup}` of a layer | |
| `rsSetBuildings3D(on)` | show the buildings as 3D blocks (the "Buildings 3D" row of the Layers box). The blocks show only while the `buildings` layer is on. Tilt the map to see them | `ms:buildings3d` (`on`) |
| `rsGetBuildings3D()` | `true` when the 3D blocks are on | |

`layer` is a layer's name (`"crossings"`) or its index. `ms:ready` fires once they are all defined
(the layers' icons and textures load first).

```js
document.addEventListener("ms:ready", () => {
  rsSetModes(["cycling"]);                       // only what a bike can use
  rsSetKinds("landcover", ["park", "garden"]);   // just the green
  rsColor(rsQuery(p => p.name === "Boulevard du Larvotto"), "#e11d48");
});
```
