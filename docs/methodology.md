# Volume-estimation methodology

## Scope

This PoC implements two **raw geometric** volume methods on a
user-selected ROI (region of interest) of a point cloud. Neither is
Campo Digital's proprietary commercial cubicación rule -- that rule (how
raw geometry maps to a billable timber volume, accounting for species,
bark, stacking convention, etc.) is out of scope and must be applied as a
separate, explicit conversion step on top of these raw results.

## Cross-section integration (`CrossSectionVolumeEstimator`)

Analogous to classic forestry sectional methods (e.g. Smalian, Huber):

1. Choose a longitudinal axis (the stack's long direction).
2. Divide the ROI into `n_sections` equal-thickness slabs along that axis.
3. For each slab, project its points onto the plane perpendicular to the
   axis and compute the 2D convex-hull area of that projection.
4. Sum `area * thickness` across slabs.

Validated in `tests/test_volume_estimators.py` against analytically-known
rectangular-prism and cylinder volumes (relative error < 10% at
reasonable section counts/point densities); also tested under partial
occlusion to confirm the estimate degrades (as expected) rather than
silently reporting the true value.

Known limitations: convex-hull-per-slab underestimates concave
cross-sections (e.g. gaps between logs); section count and axis choice are
not auto-tuned.

## Voxel occupancy baseline (`VoxelVolumeEstimator`)

Voxelizes the ROI at a fixed `voxel_size` and reports
`occupied_voxel_count * voxel_size**3`. This is explicitly labeled (in the
result's `warnings`) as a raw geometric statistic, not a validated
commercial volume -- it is sensitive to voxel size (tested in
`tests/test_volume_estimators.py::test_voxel_size_sensitivity`) and biased
by point-cloud thickness/gaps/occlusion.

## Not implemented (stubs only)

- `Grid25DVolumeEstimator`: would rasterize the ROI into a height grid
  (DSM-style) and integrate per-cell volume. Needs a validated
  interpolation/gap-filling strategy first.
- `MeshVolumeEstimator`: would reconstruct a watertight mesh (e.g.
  Poisson or alpha-shape) and take its enclosed volume. Needs a chosen
  reconstruction algorithm and watertightness validation strategy first.

Both raise `NotImplementedError` with an explanatory message rather than
producing fabricated output.

## Result provenance

Every `VolumeResult` carries `method`, `parameters` (exact inputs used),
`bounds`, `point_count_input` / `point_count_used`, `warnings`, `runtime`,
and a `provenance` dict -- enough to reproduce or audit any single run.
`volume_unit` defaults to `cubic_units_unspecified`; it is only set to
`m3` when the caller explicitly confirms the source CRS/scale is metric.
