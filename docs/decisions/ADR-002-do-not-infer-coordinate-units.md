# ADR-002 — Do not infer CRS or coordinate units

## Status

Accepted

## Context

The current real LAS contains coordinates that visually resemble projected geospatial coordinates, but it does not encode an explicit CRS.

Its coordinate scale is:

~~~text
0.0001
~~~

That scale controls numeric storage resolution and does not establish physical measurement accuracy or linear units.

The project ultimately concerns timber volume, so incorrectly assuming metres would also incorrectly justify reporting m³.

## Decision

The system does not infer CRS or linear units from coordinate appearance.

Until units are explicitly confirmed, geometric measurements are reported in:

~~~text
source units
~~~

Volume must not be labelled m³ unless metric linear units have been established from trustworthy metadata or explicit user/client input.

## Rationale

Several distinct concepts must remain separate:

~~~text
LAS numeric resolution
!= sensor ranging precision
!= registered-cloud accuracy
!= object-measurement accuracy
!= final cubicación accuracy
~~~

Guessing a CRS or unit would convert an inference into a false fact and could invalidate every downstream measurement.

## Alternatives considered

### Infer a likely projected CRS from coordinate magnitude/location

Rejected because plausible coordinates are insufficient evidence.

### Assume metres only for the current Campo Digital dataset

Rejected because this would create dataset-specific hidden behavior and make later results difficult to audit.

### Require confirmed coordinate metadata before any processing

Rejected because useful geometry analysis can still proceed safely in source units.

## Consequences

### Positive

- prevents unsupported metre/m³ claims;
- preserves uncertainty explicitly;
- allows geometry experiments to continue before CRS confirmation;
- keeps validation scientifically defensible.

### Negative / trade-offs

- some user-facing results are less convenient until Campo Digital confirms the CRS;
- absolute physical interpretation is delayed.

## Related evidence

- `docs/coordinate-systems.md`
- `docs/datasets/v01_MG_23jun2026.md`
- `docs/findings/cubicacion_accuracy_problem.md`
- `docs/es/preguntas-campo-digital.md`
