# EXP-004 — Visible log-end detection and 2D-to-3D backprojection

## Status

Completed

## Question

Can clearly visible log ends on the isolated timber wall be detected reproducibly in a local front-view image, and can those 2D detections be mapped exactly back to the original 3D LAS points?

## Hypothesis

If the visible timber face is projected into a deterministic local front view, circular or approximately radial log-end structure should be detectable using classical computer-vision methods.

If the projection preserves source-point correspondence, accepted 2D detections should also support deterministic 2D-to-3D backprojection into the original timber-wall LAS.

## Input

Automatic timber-stack segmentation:

~~~text
data/interim/v01_MG_23jun2026/timber_roi/
timber_stack_automatic_v1.las

1,342,183 points
~~~

A local front-view sweep was generated from overlapping longitudinal windows and several view yaw angles.

The detector-development window used here was:

~~~text
W03
yaw = -10 degrees
~~~

The work in this experiment targets visible log-end geometry only.

It does not establish individual-log length or whole-pile volume.

## Method

### 1. Local front-view projection

A reusable projection/backprojection implementation was created in:

~~~text
src/lidar_core/front_view.py
~~~

The projection preserves exact source LAS row indices for visible projected points.

The W03 projection was independently reconstructed and compared against the original experimental raster.

Reproduction result:

~~~text
reference image shape:    260 x 480 x 3
reproduced image shape:   260 x 480 x 3

occupied pixels reference:   90,643
occupied pixels reproduced:  90,643

occupancy agreement: 100.000000%
occupancy IoU:       100.000000%
RGB MAE:             ~1e-8
~~~

Projection geometry:

~~~text
longitudinal window:
-9.512869 -> 0.841871

longitudinal axis:
[0.99989635, 0.0143978]

view axis:
[0.15945111, 0.98720583]

horizontal image axis:
[0.98720583, -0.15945111]

horizontal source units / pixel:
0.02083715

vertical source units / pixel:
0.01596409
~~~

### 2. Initial DoG detector

A classical difference-of-Gaussians log-end detector was implemented in:

~~~text
src/lidar_core/log_ends.py
~~~

Several iterations were tested.

The retained baseline was version 3.

Detector-development progression:

~~~text
v1 accepted candidates: 565
v2 accepted candidates: 237
v3 accepted candidates: 183
~~~

A later dual-polarity DoG variant performed worse and was not retained.

### 3. Manual 100-log sampled benchmark

A non-exhaustive set of 100 clearly visible log centres was manually labelled in W03:

~~~text
W03_manual_log_centres_v1.csv
~~~

This set measures detection recall against selected obvious logs.

It does not by itself provide detector precision because the entire image was not exhaustively labelled.

DoG v3 matching results:

~~~text
match radius  3 px: 27 / 100
match radius  5 px: 40 / 100
match radius  8 px: 50 / 100
match radius 10 px: 53 / 100
match radius 12 px: 64 / 100
~~~

At an 8-pixel threshold, matched-centre error was:

~~~text
median: 2.74 px
p90:    6.09 px
maximum: 7.97 px
~~~

### 4. Radial-gradient detector

A separate detector based on radial gradient-direction voting was implemented in:

~~~text
src/lidar_core/log_ends_radial.py
~~~

The method uses:

- observed-pixel support;
- multiple candidate radii;
- radial gradient consistency;
- both intensity polarities;
- non-maximum suppression.

Real W03 output:

~~~text
raw radial candidates: 222
accepted candidates:   204
~~~

Performance against the same 100 manually sampled logs:

~~~text
match radius  3 px: 49 / 100
match radius  5 px: 68 / 100
match radius  8 px: 74 / 100
match radius 10 px: 78 / 100
match radius 12 px: 80 / 100
~~~

The radial detector substantially improved recall over the DoG baseline.

### 5. Radial-first fusion experiment

A higher-recall fusion was tested using radial detections as primary candidates and adding non-duplicate DoG detections.

Result:

~~~text
radial primary:       204
DoG duplicates:       116
new DoG additions:     67
combined candidates:  271
~~~

Manual 100-log benchmark:

~~~text
3 px:  51 / 100
5 px:  71 / 100
8 px:  76 / 100
10 px: 79 / 100
12 px: 82 / 100
~~~

At 8 pixels:

~~~text
median centre error: 2.11 px
p90:                 4.93 px
maximum:             7.80 px
~~~

This increased recall, but candidate count also increased substantially.

### 6. Exhaustive precision/recall benchmark

To obtain actual precision as well as recall, a smaller W03 crop was exhaustively labelled.

Crop:

~~~text
X pixels: 160 -> 320
Y pixels: 45  -> 225
~~~

Manual exhaustive labels:

~~~text
70 clearly visible log ends
~~~

At an 8-pixel matching radius:

~~~text
DoG v3
-------
candidates: 54
TP: 33
FP: 21
FN: 37

precision: 61.1%
recall:    47.1%
F1:        53.2%
~~~

~~~text
Radial v5
---------
candidates: 69
TP: 46
FP: 23
FN: 24

precision: 66.7%
recall:    65.7%
F1:        66.2%
~~~

~~~text
Radial-first v5.1
-----------------
candidates: 81
TP: 50
FP: 31
FN: 20

precision: 61.7%
recall:    71.4%
F1:        66.2%
~~~

At larger matching tolerances:

~~~text
10 px F1
--------
DoG v3:            58.1%
Radial v5:         69.1%
Radial-first v5.1: 68.9%

12 px F1
--------
DoG v3:            62.9%
Radial v5:         74.8%
Radial-first v5.1: 74.2%
~~~

### 7. 2D-to-3D backprojection proof

Five radial detections that matched manually labelled visible logs were selected.

The front-view projection was used to recover the exact source LAS rows contributing to each detection.

Both directly visible and locally enriched 3D point patches were exported for CloudCompare inspection.

Example results:

~~~text
log01
manual match error: 2.05 px
detector radius:    5 px
visible points:     282
enriched points:    944

log02
manual match error: 2.80 px
detector radius:    5 px
visible points:     282
enriched points:    888

log03
manual match error: 2.89 px
detector radius:    5 px
visible points:     253
enriched points:    737

log04
manual match error: 1.18 px
detector radius:    5 px
visible points:     292
enriched points:    1,043

log05
manual match error: 0.65 px
detector radius:    6 px
visible points:     313
enriched points:    942
~~~

The exported patches were visually inspected in CloudCompare.

## Result

FACT:

The W03 local front-view projection can be reproduced deterministically from the 3D timber-wall LAS.

FACT:

The projection preserves source-point correspondence sufficiently to map accepted 2D detections back to exact original LAS rows.

FACT:

Classical computer vision detects a substantial fraction of clearly visible log ends.

FACT:

The radial-gradient detector outperformed the retained DoG detector on the manually labelled benchmarks.

FACT:

On the exhaustive 70-log crop, radial v5 achieved:

~~~text
precision: 66.7%
recall:    65.7%
F1:        66.2%
~~~

at an 8-pixel match radius.

FACT:

A higher-recall fusion increased recall to 71.4% at 8 pixels, but reduced precision to 61.7%.

## Interpretation

INFERENCE:

Radial v5 is the best balanced classical detector tested so far.

INFERENCE:

The higher-recall radial-first fusion may be useful when downstream review can tolerate additional false positives.

RESULT:

Visible log-end detection plus deterministic 2D-to-3D backprojection is technically feasible on the current timber wall.

LIMITATION:

Current classical detection quality is not sufficient to treat every automatic detection as a reliable individual log measurement without review or further model development.

NOT YET ESTABLISHED:

- reliable per-log diameter measurement;
- individual log length;
- correspondence between one visible log end and an opposite end;
- whole-pile volume from individual-log reconstruction;
- whether an ML detector would materially improve operational performance.

## Decision

Freeze further classical log-end detector tuning for the current phase.

Retain radial v5 as the best balanced classical baseline.

Retain deterministic front-view projection and 2D-to-3D backprojection as reusable capabilities.

Do not make individual-log reconstruction the primary cubicación path until the whole-pile measurement definition and available depth information are clarified.

## Limitations

The precision/recall benchmark is based on:

- one local W03 front-view region;
- one current real LAS;
- manual labels of visually clear log ends;
- pixel-distance matching rather than physically calibrated diameter error.

Because physical coordinate units remain unconfirmed, pixel and source-unit geometry must not yet be translated into centimetre-level accuracy claims.

## Next step

Prioritize directly observable whole-pile geometry.

Measure the longitudinal/vertical cross-sectional area of the visible timber wall and quantify its sensitivity to extraction parameters.

Then evaluate volume only under an explicit externally supplied or validated pile depth.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](.) · [Decisions](../decisions) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
