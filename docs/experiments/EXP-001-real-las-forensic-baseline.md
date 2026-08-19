# EXP-001 — First real LAS forensic baseline

## Status

Completed

## Question

Can the first real Campo Digital LAS be read reproducibly, and what trustworthy metadata and geometry does it actually contain?

## Hypothesis

The supplied LAS can be processed with the repository tooling, but some metadata may require independent validation rather than being trusted directly.

## Input

Dataset:

~~~text
v01_MG_23jun2026.las
~~~

Private client data remains under `data/raw/` and is not committed.

Known LAS SHA256:

~~~text
57b34253489a7b134854fa702d5261ea79ef28a19289c3178c72340cf0991983
~~~

## Method

The dataset was inspected using:

- laspy streaming;
- repository `lidar inspect`;
- PDAL statistics;
- CloudCompare visual inspection.

The implementation computes observed XYZ bounds from actual point records and compares them with the LAS header.

## Reproduce

~~~bash
uv run lidar inspect \
  data/raw/v01_MG_23jun2026/v01_MG_23jun2026.las
~~~

## Result

Confirmed:

~~~text
LAS version: 1.2
point format: 3
points: 9,718,909
RGB: present
intensity: present
GPS time: present
CRS: missing / ambiguous
~~~

Observed geometry:

~~~text
X: 499959.7519 -> 500159.9936
Y: -4166629.1194 -> -4166548.3633
Z: 276.2244 -> 314.6254
~~~

Approximate observed spans:

~~~text
200.242 × 80.756 × 38.401 source units
~~~

The LAS-header bounds are materially larger than the observed geometry.

The file also identifies an export/conversion path involving `txt2las`.

## Interpretation

The dataset is suitable for further point-cloud experiments, but its header and provenance cannot be treated as fully sensor-native truth.

Actual point coordinates should drive downstream geometry.

## Limitations

This experiment does not establish:

- the original sensor;
- CRS;
- physical coordinate units;
- sensor precision;
- final volume accuracy;
- Campo Digital's commercial cubicación method.

## Decision

Proceed with the real LAS, but preserve explicit forensic safeguards:

- observed rather than header bounds for geometry;
- no CRS inference;
- no m³ claims before unit confirmation.

## Next step

Characterize acquisition timing and return-number structure.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](.) · [Decisions](../decisions) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
