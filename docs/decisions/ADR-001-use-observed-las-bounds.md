# ADR-001 — Use observed LAS bounds for geometry

## Status

Accepted

## Context

The first real Campo Digital dataset, `v01_MG_23jun2026.las`, contains LAS-header bounds that differ materially from the coordinates observed by streaming the actual point records.

Observed spans are approximately:

~~~text
X: 200.242 source units
Y: 80.756 source units
Z: 38.401 source units
~~~

The LAS header declares approximately:

~~~text
X: 242.639 source units
Y: 149.714 source units
Z: 45.337 source units
~~~

Using the header directly would therefore make downstream geometry depend on stale metadata.

## Decision

Geometry uses bounds recomputed from the actual LAS point records.

Header-declared bounds are retained separately for provenance and audit.

The inspection model exposes both:

~~~text
bounds
header_bounds
header_bounds_match
~~~

and emits a warning when they disagree.

## Rationale

Actual point coordinates are the relevant evidence for the geometry contained in the file.

The original header still has forensic value, so it should not be discarded or silently overwritten.

This approach makes stale metadata visible while preventing it from contaminating geometry calculations.

## Alternatives considered

### Trust the LAS header

Rejected because the first real dataset demonstrates that the header can be stale.

### Rewrite the LAS header

Rejected for the PoC.

The original client file should remain unchanged and its provenance preserved.

### Use PDAL-reported observed statistics only

Useful for validation, but the repository still needs its own deterministic behavior and typed metadata model.

## Consequences

### Positive

- downstream geometry uses the points actually present;
- metadata disagreement is visible;
- original provenance is retained;
- behavior is covered by regression tests.

### Negative / trade-offs

- inspection requires streaming point coordinates rather than relying only on the header;
- large datasets require more work than header-only inspection.

## Related evidence

- `docs/datasets/v01_MG_23jun2026.md`
- `docs/findings/cubicacion_accuracy_problem.md`
- `src/lidar_io/inspect.py`
- `tests/test_las_scale_offset.py`

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](../experiments) · [Decisions](.) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
