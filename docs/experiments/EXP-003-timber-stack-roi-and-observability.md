# EXP-003 — Timber-stack ROI and depth observability

## Status

Completed

## Question

Can the timber stack in the current real LAS be isolated reproducibly, and does the point cloud contain enough observable geometry to identify both the visible timber face and a coherent opposite/rear timber surface?

## Hypothesis

If the current LAS observes both sides of the timber stack, then after isolating the stack in a local coordinate frame there should be:

- one coherent vertical timber surface on the visible side; and
- a second coherent vertical timber surface at a different transverse position across multiple longitudinal sections.

If the additional transverse structure is instead ground, road, vegetation, or unrelated scene geometry, it should not behave like a persistent second vertical timber wall.

## Input

Primary real dataset:

~~~text
v01_MG_23jun2026.las
9,718,909 points
~~~

Deterministic candidate ROI:

~~~text
data/interim/v01_MG_23jun2026/timber_roi/
timber_stack_candidate_v1.las

4,074,894 points
~~~

Manual CloudCompare reference segmentation:

~~~text
timber_stack_manual_reference_v1.las

1,577,128 points
~~~

Automatic timber-stack segmentation:

~~~text
timber_stack_automatic_v1.las

1,342,183 points
~~~

All coordinates remain in source-coordinate units because the LAS does not contain an explicit confirmed CRS.

## Method

### 1. Deterministic candidate ROI

A large reproducible crop was created from the real LAS:

~~~text
X: 500000 -> 500090
Y: -4166583 -> -4166569
Z: 277.5 -> 287.5
~~~

Result:

~~~text
4,074,894 / 9,718,909 points retained
~~~

Observed candidate bounds:

~~~text
X span: 89.983 source units
Y span: 13.998 source units
Z span: 9.598 source units
~~~

### 2. Manual visual reference

CloudCompare was used only as a visual/debugging tool to produce a manual reference segmentation of the visible timber structure.

The manual reference is not treated as ground truth for timber volume.

### 3. Automatic timber-stack isolation

A reusable detector was implemented in:

~~~text
src/lidar_core/timber_stack.py
~~~

The detector uses local principal directions plus voxel/component geometry to identify an elongated, vertically significant timber-dominant component.

Automatic output:

~~~text
1,342,183 points
32.938% of candidate ROI
3 detected components
81.667% longitudinal coverage
77.083% vertical extent fraction
20.833% transverse extent fraction
~~~

### 4. Geometric comparison against the manual reference

Because CloudCompare export can change exact point serialization, exact point-set equality was not used.

Instead, nearest-neighbour geometric agreement was measured.

At a distance threshold of 0.10 source units:

~~~text
precision-like: 95.57%
recall-like:    85.71%
F1-like:        90.37%
~~~

At 0.25 source units:

~~~text
precision-like: 96.38%
recall-like:    90.42%
F1-like:        93.31%
~~~

These are geometric-closeness diagnostics, not semantic classification precision.

### 5. Local pile coordinate system

The isolated timber wall was used to derive a local coordinate system:

~~~text
longitudinal axis ≈ [0.99989635, 0.0143978]
transverse axis   ≈ [-0.0143978, 0.99989635]
~~~

The transverse coordinate was then used to investigate whether the cloud contains a coherent second timber surface.

### 6. Initial transverse-depth inspection

Eight longitudinal slices were analyzed across the full candidate ROI.

The candidate contained strong secondary transverse density modes around approximately:

~~~text
T ≈ -5 to -6 source units
~~~

while the known timber wall was generally near:

~~~text
T ≈ 0 source units
~~~

At first glance this could have been interpreted as a possible second pile surface.

### 7. Ground-cleaned local test

A region with apparently substantial transverse depth was isolated and cleaned using a fitted ground plane.

After removing near-ground points:

~~~text
input points:     405,223
retained points:  287,999
retained:         71.072%
~~~

The cleaned transverse profiles showed:

~~~text
median q05-q95 transverse spread: 0.357 source units
minimum:                         0.267
maximum:                         0.482
slices with >=2 strong peaks:    1 / 12
~~~

The apparent large depth mostly disappeared after ground removal.

### 8. Whole-stack opposite-side rendering

The candidate was rendered from both transverse directions using a depth-buffer style projection:

~~~text
MAX-T side
MIN-T side
~~~

Both projections showed essentially the same dominant timber wall.

The MIN-T rendering exposed additional scene structure and vegetation near the lower part of the image, but did not reveal a coherent second wall of opposite log ends.

### 9. Vertical-extent wall test

The candidate was divided into eight longitudinal slices.

Within each slice, points were binned transversely and the robust vertical extent was measured using:

~~~text
Z span = q95(Z) - q05(Z)
~~~

A true second timber wall was expected to produce a persistent band of large vertical extent at a second transverse location.

Instead, bins with large vertical extent remained concentrated near the already identified timber-wall transverse region.

No persistent second high-vertical-extent band was observed around the earlier T ≈ -5 to -6 density modes.

## Result

FACT:

A coherent visible timber wall can be isolated reproducibly from the current real LAS.

FACT:

The automatic segmentation geometrically agrees strongly with the manual visual reference.

FACT:

The large candidate ROI contains substantial geometry at transverse positions several source units away from the visible timber wall.

FACT:

After ground-aware analysis, that additional transverse geometry does not form a persistent second vertical timber wall.

FACT:

Opposite transverse renders do not expose two distinct opposing timber-end walls.

RESULT:

No coherent second vertical timber surface was observed in the current candidate cloud.

## Interpretation

INFERENCE:

The current LAS appears to provide one dominant observable timber face together with surrounding ground, road, vegetation, and other scene geometry.

INFERENCE:

The previously observed transverse separation of approximately 5–6 source units must not be interpreted directly as timber-stack depth.

LIMITATION:

Whole-pile depth is not directly observable from the current isolated geometry using the tests performed here.

NOT YET ESTABLISHED:

- whether another part of the original LAS contains the opposite timber face;
- whether Campo Digital's operational workflow derives pile depth from another scan, metadata, known log length, manual input, or another geometric rule;
- whether the current scan was intended to provide full pile enclosure geometry.

## Decision

Do not infer pile depth from the secondary transverse density modes.

Do not close the unobserved side of the pile with an artificial surface and call the resulting mesh or voxel statistic timber volume.

Treat the visible timber wall as directly observable geometry and treat pile depth as a separate unresolved input unless additional evidence establishes it.

## Limitations

The result is specific to:

- the current real LAS;
- the current deterministic candidate ROI;
- the current timber-stack segmentation;
- the tested local pile coordinate system.

The result does not prove that the original physical pile had no observable opposite face during acquisition.

It establishes only that a coherent second timber wall was not found in the currently analyzed point-cloud evidence.

Physical coordinate units also remain unconfirmed.

## Next step

Measure the observable longitudinal/vertical cross-section of the visible timber wall reproducibly.

Then represent whole-pile extrusion volume explicitly as:

~~~text
V(d) = A_front * d
~~~

where:

~~~text
A_front = directly measured observable front cross-sectional area
d       = explicit external/validated depth input
~~~

Depth must not be silently inferred from the current LAS.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../../README.md) · [Docs index](../README.md) · [Findings](../findings/cubicacion_accuracy_problem.md) · [Experiments](.) · [Decisions](../decisions) · [Spanish docs](../es/README.md) · [Estado técnico](../es/estado-proyecto.md) · [Preguntas Campo Digital](../es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
