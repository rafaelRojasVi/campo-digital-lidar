# EXP-002 — GPS timestamp and return-group structure

## Status

Completed

## Question

Does the real LAS preserve a meaningful relationship between GPS timestamps and LAS return numbers?

## Hypothesis

If timestamp and return fields preserve acquisition structure, repeated exact GPS timestamps may exhibit systematic return-number patterns.

## Input

~~~text
v01_MG_23jun2026.las
9,718,909 points
~~~

## Method

A streaming acquisition analyzer was implemented.

It measures:

- GPS-time range;
- monotonicity;
- equal/backward steps;
- return-number counts;
- exact contiguous timestamp groups;
- return pattern inside two-record groups;
- R1/R2 geometric separation;
- intensity differences.

Timestamp groups crossing LAS streaming chunk boundaries are preserved explicitly.

## Reproduce

~~~bash
uv run lidar analyze \
  data/raw/v01_MG_23jun2026/v01_MG_23jun2026.las
~~~

## Result

GPS time is non-decreasing in LAS record order.

~~~text
backward steps: 0
equal adjacent steps: 4,109,685
~~~

Exact timestamp groups:

~~~text
total groups: 5,609,224

size 1: 1,499,539
size 2: 4,109,685

maximum group size: 2
~~~

Every two-record timestamp group has the pattern:

~~~text
Return 1 -> Return 2
~~~

Pattern counts:

~~~text
1->2: 4,109,685
2->1: 0
1->1: 0
2->2: 0
other: 0
~~~

Exact-pair 3D separation:

~~~text
minimum: 0
mean: 0.270756447
maximum: 87.9410127 source units
~~~

The remaining singleton labels are approximately balanced:

~~~text
Return 1 singletons: 750,146
Return 2 singletons: 749,393
~~~

Every LAS point nevertheless declares:

~~~text
NumberOfReturns = 2
~~~

## Interpretation

FACT:

GPS timestamp grouping and return-number ordering are strongly and deterministically related in this export.

INFERENCE:

The conversion/export pipeline preserves meaningful acquisition structure.

NOT YET ESTABLISHED:

That every R1/R2 pair is necessarily the first and second physical echo from one emitted laser pulse.

## Limitations

The physical interpretation of return fields remains unresolved because:

- the exact sensor is not confirmed;
- the export sequence is not confirmed;
- the LAS passed through `txt2las`;
- some exact R1/R2 pairs have very large spatial separation.

## Decision

Retain return/timestamp diagnostics as useful forensic evidence, but do not build the timber-measurement algorithm around unverified physical return semantics.

Generic whole-cloud forensic work is now sufficiently mature to move toward the timber ROI.

## Next step

Isolate the visible timber stack reproducibly and begin front-face/log-end geometry experiments.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](.) · [Decisions](../decisions) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
