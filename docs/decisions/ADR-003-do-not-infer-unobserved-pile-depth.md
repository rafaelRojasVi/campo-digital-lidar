# ADR-003 — Do not infer or artificially close unobserved pile depth

## Status

Accepted

## Context

The current Campo Digital timber-stack LAS contains one dominant observable timber face.

EXP-003 investigated whether additional transverse geometry represented a coherent opposite or rear timber wall.

The analysis included:

- deterministic timber-stack isolation;
- local longitudinal/transverse coordinates;
- transverse density inspection;
- ground-aware cleanup;
- opposite-side rendering;
- vertical-extent analysis across longitudinal slices.

The result was:

~~~text
No coherent second vertical timber surface was observed
in the current analyzed candidate cloud.
~~~

Secondary transverse geometry several source units away from the visible wall was associated mainly with surrounding scene structure such as ground, road, vegetation, or other non-wall geometry.

The project ultimately needs timber cubicación, but closing an unobserved surface would convert a missing measurement into an unsupported geometric assumption.

## Decision

The system must not infer pile depth from unrelated transverse point-cloud structure.

The system must not automatically construct an artificial rear surface solely to create a closed mesh, voxel body, or volumetric solid.

When pile depth is not directly established by trustworthy geometric evidence, it must remain an explicit external or validated input.

The currently supported whole-stack extrusion model is therefore:

~~~text
V(d) = A_front * d
~~~

where:

~~~text
A_front = directly measured observable front cross-sectional area
d       = explicit supplied or independently validated depth
~~~

Without `d`, the system reports observable cross-sectional geometry only.

## Rationale

A closed 3D body is mathematically convenient, but mathematical closure does not imply physical observability.

The following are not equivalent:

~~~text
visible front surface
!=
complete pile boundary

secondary transverse point density
!=
rear timber surface

closed reconstruction
!=
measured physical volume

geometric extrusion
!=
validated commercial cubicación
~~~

Inventing a rear surface would create false geometric certainty and could dominate the resulting volume error.

Keeping depth explicit preserves the distinction between:

- directly measured geometry;
- externally supplied information;
- inferred geometry;
- commercial cubicación rules.

## Alternatives considered

### Use the farthest transverse point cluster as pile depth

Rejected.

EXP-003 showed that the strong secondary transverse modes do not behave like a persistent second vertical timber wall.

### Close the visible surface automatically with a watertight mesh

Rejected.

A watertight mesh would produce a numerical volume but would not prove that the unobserved closure matches the physical pile.

### Use voxel occupancy across the entire candidate ROI

Rejected as a primary volume method.

The candidate ROI contains ground, vegetation, road, and other non-timber geometry.

Voxel occupancy would therefore combine scene occupancy with assumptions about hidden pile structure.

### Require complete 360-degree pile geometry before producing any useful measurement

Rejected.

The visible timber wall contains useful directly observable geometry.

Its cross-sectional area can be measured safely while keeping the missing depth explicit.

### Allow explicit user/client-supplied depth

Accepted.

This preserves provenance of the hidden dimension and makes the volume calculation auditable.

## Consequences

### Positive

- prevents unsupported whole-pile depth claims;
- prevents artificial mesh closure from being mistaken for measurement;
- preserves the distinction between observed and supplied geometry;
- allows the PoC to continue using valid front-wall measurements;
- makes the volume model transparent and reproducible;
- supports later replacement of explicit depth with validated geometric depth if future datasets contain sufficient evidence.

### Negative / trade-offs

- a cubic volume cannot be computed from the current isolated wall alone;
- operational use may require an additional depth/log-length input;
- the current result may differ from Pix4D or LiDAR360 if those workflows use additional geometry or proprietary assumptions.

## Implementation consequences

`lidar volume FILE`

reports observable front-wall geometry only.

`lidar volume FILE --depth D`

additionally reports:

~~~text
A_front * D
~~~

in source-units³.

The command must not infer metres or m³ unless coordinate units are independently confirmed.

The command must not infer `D` from the current LAS.

## Related evidence

- `docs/experiments/EXP-003-timber-stack-roi-and-observability.md`
- `docs/experiments/EXP-005-front-cross-section-and-depth-sensitivity.md`
- `docs/decisions/ADR-002-do-not-infer-coordinate-units.md`
- `docs/findings/cubicacion_accuracy_problem.md`
- `docs/es/preguntas-campo-digital.md`

## Future reconsideration

This decision may be revisited if a future dataset or confirmed acquisition workflow provides:

- a coherent observable rear timber surface;
- registered scans from multiple sides;
- known log lengths or pile depth;
- validated sensor geometry sufficient to recover depth;
- a confirmed Campo Digital operational rule that defines how depth must be supplied or derived.

Any future automated depth estimate must be validated independently before replacing explicit depth input.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](../experiments) · [Decisions](.) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
