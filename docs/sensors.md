# Sensors

Three LAS-producing sensors are in scope for Campo Digital. Structured,
version-controlled facts live in `configs/sensors/*.yaml`; this page is a
narrative summary. Unknown/unverified fields are `null`/TODO in the YAML
-- never guessed.

## XGRIDS Lixel K2

Handheld/backpack SLAM LiDAR + camera. Outputs LAS, mesh, and 3D Gaussian
Splatting (3DGS). For this PoC, LAS is the interchange format used by the
volume algorithms; mesh/3DGS outputs are noted as available but not
consumed by any code here.

## GeoSun GS-100G

Terrestrial/backpack SLAM LiDAR. Outputs LAS. Primary expected source of
ground-level, close-range scans of timber stacks (higher point density on
stack faces than aerial capture).

## DJI Zenmuse L2

Aerial LiDAR + RGB payload for drones. Outputs LAS. RTK-aided direct
georeferencing when RTK is fixed. Likely lower point density on vertical
stack faces due to top-down/oblique flight geometry -- a consideration for
which volume method (cross-section vs voxel) is appropriate per sensor.

## Common LAS interchange

Because all three sensors can emit LAS, `lidar_io.inspect_las` and the
volume estimators are sensor-agnostic at the file level -- sensor-specific
handling (if ever needed) would live in a per-sensor ingestion step, not
in the core inspection/volume code.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../README.md) · [Docs index](README.md) · [Findings](findings/cubicacion_accuracy_problem.md) · [Experiments](experiments) · [Decisions](decisions) · [Spanish docs](es/README.md) · [Estado técnico](es/estado-proyecto.md) · [Preguntas Campo Digital](es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
