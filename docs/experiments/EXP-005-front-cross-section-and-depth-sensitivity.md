# EXP-005 — Front cross-section and explicit-depth volume sensitivity

## Status

Completed

## Question

Can the directly observable timber wall be converted into a reproducible whole-stack geometric measurement without inventing unobserved pile depth?

## Hypothesis

If the visible timber wall is sufficiently coherent, its longitudinal/vertical cross-sectional area should be measurable reproducibly from the isolated 3D points.

If that area is stable against reasonable longitudinal bin counts, then the remaining dominant uncertainty should come from the definition of the upper/lower wall envelope rather than numerical integration.

Whole-pile geometric volume can then be represented explicitly as:

~~~text
V(d) = A_front * d
~~~

where `d` is supplied externally or established by additional evidence.

## Input

Automatic timber-stack segmentation:

~~~text
data/interim/v01_MG_23jun2026/timber_roi/
timber_stack_automatic_v1.las

1,342,183 points
~~~

The point cloud remains in source-coordinate units because physical coordinate units are not yet confirmed.

## Method

### 1. Local longitudinal coordinate

The isolated timber wall was projected into its dominant horizontal principal direction.

The robust longitudinal extent was defined using the 1st and 99th percentiles.

Result:

~~~text
longitudinal minimum: -31.181...
longitudinal maximum:  30.180...
robust span:           61.361422 source units
~~~

### 2. Robust vertical wall profile

The longitudinal extent was divided into bins.

For each bin:

- a robust lower vertical envelope was estimated;
- a robust upper vertical envelope was estimated;
- local wall height was computed as upper minus lower envelope;
- missing short runs, if any, were interpolated;
- cross-sectional area was integrated longitudinally.

The baseline configuration used:

~~~text
longitudinal bins: 160

longitudinal extent:
1% -> 99%

vertical envelope:
2% -> 98%
~~~

Baseline result:

~~~text
point count:         1,342,183
valid bins:          100.000%
longitudinal span:   61.361422 source units
median height:        3.688422 source units
maximum height:       4.632758 source units

rectangle area:     217.176317 source-units²
trapezoid area:     216.434772 source-units²
~~~

The rectangle and trapezoidal integrations differ by less than one source-unit².

### 3. Area robustness sweep

The same measurement was repeated using four longitudinal resolutions:

~~~text
80 bins
120 bins
160 bins
240 bins
~~~

and three vertical envelope definitions:

~~~text
1% -> 99%
2% -> 98%
5% -> 95%
~~~

Results:

~~~text
bins= 80 | 1%-99% | area=224.646
bins= 80 | 2%-98% | area=218.731
bins= 80 | 5%-95% | area=204.079

bins=120 | 1%-99% | area=223.783
bins=120 | 2%-98% | area=217.758
bins=120 | 5%-95% | area=203.520

bins=160 | 1%-99% | area=223.205
bins=160 | 2%-98% | area=217.176
bins=160 | 5%-95% | area=202.939

bins=240 | 1%-99% | area=222.399
bins=240 | 2%-98% | area=216.464
bins=240 | 5%-95% | area=202.767
~~~

For a fixed vertical envelope, changing the longitudinal bin count from 80 to 240 changed the result by approximately 1% or less.

Across all tested envelope definitions:

~~~text
minimum area: 202.767 source-units²
median area:  217.467 source-units²
maximum area: 224.646 source-units²

mean:         214.789 source-units²
std:            8.874 source-units²

total range / median:
10.06%
~~~

The primary sensitivity therefore comes from the chosen vertical envelope rather than longitudinal integration resolution.

### 4. Frozen area scenarios

Three area scenarios were retained from the robustness sweep by taking the median across bin counts for each envelope:

~~~text
inner / 5%-95%:
203.229 source-units²

central / 2%-98%:
217.467 source-units²

outer / 1%-99%:
223.494 source-units²
~~~

These values represent extraction sensitivity only.

They are not confidence intervals and do not represent total physical measurement error.

### 5. Explicit-depth volume sensitivity

Because EXP-003 found no coherent observable rear timber wall, pile depth was not inferred from the current LAS.

Instead:

~~~text
V(d) = A_front * d
~~~

was evaluated over explicit candidate depths.

Using the central area:

~~~text
depth= 1 ->  217.47 source-units³
depth= 2 ->  434.93 source-units³
depth= 3 ->  652.40 source-units³
depth= 4 ->  869.87 source-units³
depth= 5 -> 1087.34 source-units³
depth= 6 -> 1304.80 source-units³
depth= 8 -> 1739.74 source-units³
depth=10 -> 2174.67 source-units³
~~~

The corresponding inner/outer envelope sensitivity scales linearly with depth.

For example, at depth 5:

~~~text
inner:
1016.15 source-units³

central:
1087.34 source-units³

outer:
1117.47 source-units³
~~~

These sensitivity values use the median area for each envelope across multiple bin counts.

### 6. Reusable implementation

The measurement was promoted from exploratory code into:

~~~text
src/lidar_volume/front_cross_section.py
~~~

The reusable implementation provides:

- robust front-wall cross-sectional estimation;
- explicit configuration of bin count and quantiles;
- observable height profile;
- rectangle and trapezoid area estimates;
- explicit extrusion volume `area * depth`.

Synthetic unit tests verify the estimator against known rectangular geometry.

### 7. Real-LAS regression

The reusable implementation was run against the real automatic timber wall using the exact baseline experiment configuration.

Result:

~~~text
library rectangle area:
217.176317 source-units²

previous experimental area:
217.176000 source-units²

absolute delta:
+0.000317 source-units²

relative delta:
0.000146%
~~~

RESULT:

The reusable implementation reproduces the exploratory calculation.

### 8. CLI integration

The existing `lidar volume` CLI stub was replaced with an operational command.

Without depth:

~~~bash
uv run lidar volume \
  data/interim/v01_MG_23jun2026/timber_roi/timber_stack_automatic_v1.las
~~~

the command reports:

~~~text
point count
longitudinal span
valid-bin fraction
median height
maximum height
rectangle area
trapezoid area
~~~

and explicitly reports:

~~~text
Extruded volume:
(not computed; provide --depth)
~~~

With explicit depth:

~~~bash
uv run lidar volume \
  data/interim/v01_MG_23jun2026/timber_roi/timber_stack_automatic_v1.las \
  --depth 5
~~~

the command additionally reports:

~~~text
Assumed depth:
5.000000 source units

Extruded volume:
1085.881584 source-units³
~~~

The slight difference from the sensitivity-table central value at depth 5 is expected:

- the CLI uses the exact 160-bin 2%-98% baseline area: `217.176317`;
- the sensitivity table's central scenario uses the median 2%-98% area across four bin counts: `217.467`.

These are two related but distinct reported statistics.

## Result

FACT:

The visible timber wall has a reproducible measurable longitudinal/vertical cross-section.

FACT:

The baseline cross-sectional estimate is:

~~~text
217.176317 source-units²
~~~

FACT:

Longitudinal integration resolution has small influence on the result over the tested range.

FACT:

Vertical envelope choice contributes substantially more sensitivity than bin count.

FACT:

The reusable library implementation reproduces the exploratory result to approximately:

~~~text
0.000146% relative difference
~~~

FACT:

The CLI does not compute cubic volume when depth is absent.

FACT:

When depth is explicitly supplied, the CLI computes only the geometric extrusion:

~~~text
A_front * depth
~~~

## Interpretation

INFERENCE:

The visible-wall cross-sectional measurement is sufficiently stable to serve as the current geometric baseline for the PoC.

INFERENCE:

The remaining geometric uncertainty is not dominated by numerical integration resolution.

LIMITATION:

The cross-sectional envelope is not identical to a validated commercial timber-volume boundary.

LIMITATION:

Pile depth is not directly observed from the current isolated geometry.

LIMITATION:

Coordinate units remain unconfirmed.

NOT YET ESTABLISHED:

- whether source units are metres;
- the operational pile/log depth for this dataset;
- Campo Digital's exact Pix4D/LiDAR360 reference volume;
- the exact ROI used for that reference;
- whether Campo Digital applies void, bark, stacking, species, diameter, or other commercial corrections;
- final cubicación accuracy.

## Decision

Adopt the observable front cross-section as the current primary geometric measurement.

Do not infer unobserved pile depth.

Require depth to be explicit when computing extrusion volume.

Do not label cross-sectional results as m² or volume results as m³ until physical coordinate units are confirmed.

Do not present `A_front * depth` as validated commercial cubicación until it has been compared against Campo Digital's reference method and rule.

## Limitations

The current cross-sectional estimator operates on the already isolated timber wall.

Therefore its accuracy depends on upstream timber-stack segmentation.

The tested envelope sensitivity:

~~~text
approximately 203 -> 223 source-units²
~~~

does not represent complete uncertainty.

It excludes, among other factors:

- sensor uncertainty;
- registration/reconstruction uncertainty;
- timber-stack segmentation error;
- hidden geometry;
- physical depth uncertainty;
- coordinate-unit uncertainty;
- Campo Digital's commercial cubicación rule.

## Next step

Obtain from Campo Digital:

1. confirmed CRS and physical units;
2. the exact sensor that produced the current LAS;
3. the exact pile/ROI corresponding to their reference measurement;
4. the Pix4D or LiDAR360 reference volume for that same pile;
5. the depth/log-length information used operationally;
6. clarification of whether the target result is geometric envelope volume, solid timber volume, or another commercial cubicación quantity.

Then compare the reproducible PoC measurement against the operational reference without changing the measurement definition after seeing the answer.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](.) · [Decisions](../decisions) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
