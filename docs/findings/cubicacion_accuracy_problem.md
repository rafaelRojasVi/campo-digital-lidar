# Cubicación accuracy: current technical findings

## Purpose

This document records the current engineering understanding of the Campo Digital timber-cubicación problem after forensic analysis of the first real LAS dataset.

The objective is **not yet to claim a volume result or an accuracy percentage**.

The objective is to establish:

1. what the supplied dataset actually contains;
2. which parts of the data can and cannot currently be trusted;
3. where measurement error can enter the pipeline;
4. what has already been demonstrated experimentally;
5. what remains unknown;
6. what the next technical experiment must solve.

---

## 1. The core problem is not simply `point cloud -> m³`

The complete problem is closer to:

~~~text
physical timber pile
        ↓
sensor visibility / acquisition
        ↓
registration / SLAM / reconstruction
        ↓
exported point cloud
        ↓
cleaning / outlier handling
        ↓
timber ROI selection
        ↓
visible timber geometry
        ↓
inference about hidden geometry
        ↓
raw geometric measurement
        ↓
Campo Digital cubicación rule
        ↓
reported / commercial result
~~~

Each stage can introduce uncertainty.

A system can therefore produce a numerically precise answer while still being wrong relative to:

- the physical pile;
- the actual amount of solid timber;
- Campo Digital's current operational method;
- or the commercial value reported to the client.

The engineering objective is therefore not merely to produce a number.

The objective is to produce a **repeatable, auditable and validated measurement** whose assumptions and limitations are explicit.

---

## 2. Dataset currently under analysis

Current source:

`v01_MG_23jun2026.las`

Confirmed characteristics:

- LAS version: 1.2
- point format: 3
- point count: 9,718,909
- RGB: present
- intensity: present
- GPS time: present
- classification: all points are class 1
- explicit CRS: absent
- VLRs: none
- EVLRs: none
- coordinate scale: `(0.0001, 0.0001, 0.0001)`
- coordinate offsets: `(499995.0, -4166584.0, 277.0)`
- generating software indicates `txt2las`
- system identifier references LAStools / rapidlasso

The file therefore appears to have passed through an export or conversion workflow.

It must not automatically be treated as untouched sensor-native LAS data.

---

## 3. Finding: the LAS header geometry is stale

The LAS header declares bounds that differ materially from the coordinates actually observed in the point records.

### Observed point bounds

~~~text
X: 499959.7519  -> 500159.9936
Y: -4166629.1194 -> -4166548.3633
Z: 276.2244      -> 314.6254
~~~

Observed spans:

~~~text
X span: ~200.242 source units
Y span: ~80.756 source units
Z span: ~38.401 source units
~~~

### Header-declared bounds

Approximate header spans:

~~~text
X span: ~242.639 source units
Y span: ~149.714 source units
Z span: ~45.337 source units
~~~

The mismatch is substantial.

### Engineering consequence

Downstream geometry must use bounds recomputed from the actual point records.

The LAS header bounds are still useful as provenance and audit information, but they are not suitable as geometric truth for this dataset.

The repository now explicitly distinguishes:

~~~text
observed bounds
vs
header-declared bounds
~~~

and warns when they disagree.

This is already one concrete example of how a naïve pipeline could introduce error before attempting any timber measurement.

---

## 4. Finding: numeric storage resolution is not measurement accuracy

The LAS coordinate scale is:

~~~text
0.0001
0.0001
0.0001
~~~

This describes coordinate encoding/storage resolution.

It does **not** prove any of the following:

- 0.1 mm sensor ranging accuracy;
- 0.1 mm point-cloud registration accuracy;
- 0.1 mm geometric measurement accuracy;
- 0.1 mm log-diameter accuracy;
- 0.1 mm cubicación accuracy.

These quantities must remain conceptually separate:

~~~text
LAS numeric resolution
    !=
sensor ranging precision
    !=
registered-cloud accuracy
    !=
object-measurement accuracy
    !=
final volume accuracy
~~~

This distinction is particularly important because the original requirement mentioning approximately `1–2 cm` is still ambiguous.

That value could refer to:

- sensor precision;
- geometric point position;
- diameter measurement;
- repeatability;
- local registration quality;
- or final timber-measurement tolerance.

Those are different requirements.

---

## 5. Finding: metres and m³ are not yet formally justified

The coordinates look like projected geospatial coordinates:

~~~text
X ≈ 500000
Y ≈ -4166600
Z ≈ 276–315
~~~

However, the LAS does not encode an explicit CRS.

Therefore the software currently reports geometric quantities in:

~~~text
source units
~~~

rather than silently assuming:

~~~text
metres
~~~

Likewise, the system must not label a volume as:

~~~text
m³
~~~

until the linear units have been confirmed.

A plausible-looking coordinate system is not sufficient evidence for declaring the units.

The CRS and units must either:

1. come from trustworthy source metadata; or
2. be explicitly supplied by Campo Digital.

---

## 6. Finding: acquisition order survived the export

GPS time is present.

Observed range:

~~~text
232456.594
to
232554.609
~~~

Observed span:

~~~text
~98.0149 GPS-time units
~~~

The points are non-decreasing in GPS-time order.

Observed backward steps:

~~~text
0
~~~

This is important because it means the LAS record order retains a strong temporal structure.

The dataset is therefore more than a randomly reordered collection of XYZ points.

That temporal structure can help us investigate:

- acquisition behavior;
- return relationships;
- scan progression;
- possible anomalies;
- and later potentially the scanner path or scene evolution.

It does **not**, by itself, recover scanner pose or trajectory.

---

## 7. Finding: timestamp groups are highly structured

The complete LAS contains:

~~~text
9,718,909 points
~~~

Exact GPS timestamp groups:

~~~text
5,609,224 groups
~~~

Group-size distribution:

~~~text
1 point: 1,499,539 groups
2 points: 4,109,685 groups

maximum group size: 2
~~~

No timestamp group contains more than two records.

This was verified using a streaming analysis that correctly preserves timestamp groups crossing LAS chunk boundaries.

---

## 8. Finding: every two-record timestamp group is Return 1 -> Return 2

For all:

~~~text
4,109,685
~~~

two-record timestamp groups, the return pattern is exactly:

~~~text
Return 1 -> Return 2
~~~

Observed patterns:

~~~text
1 -> 2 : 4,109,685
2 -> 1 : 0
1 -> 1 : 0
2 -> 2 : 0
other  : 0
~~~

Therefore:

~~~text
exact two-record R1/R2 fraction = 1.0
~~~

This is extremely strong evidence that GPS timestamp structure and return-number structure are connected in this export.

However, this still does **not prove the physical interpretation** of those pairs.

Specifically, it does not yet prove that every pair is necessarily:

> first and second physical echoes from the same emitted laser pulse.

The file has passed through a conversion/export workflow.

Sensor and export provenance are still required before assigning that physical meaning.

---

## 9. Finding: singleton timestamp records also exist

Not every timestamp contains two points.

There are:

~~~text
1,499,539 singleton timestamp groups
~~~

Using the total return counts and the paired groups, the singleton labels are:

~~~text
singleton Return 1: 750,146
singleton Return 2: 749,393
~~~

They are almost perfectly balanced.

At the same time, every point in the LAS declares:

~~~text
NumberOfReturns = 2
~~~

Therefore:

> `NumberOfReturns = 2` cannot simply be interpreted as proof that two point records are present for every GPS timestamp.

The export semantics require further investigation.

---

## 10. Finding: exact R1/R2 pairs can be spatially far apart

For all:

~~~text
4,109,685
~~~

exact two-record R1/R2 timestamp groups, the observed 3D separation is:

~~~text
minimum: 0
mean:    0.270756447
maximum: 87.9410127 source units
~~~

Mean absolute coordinate differences:

~~~text
|delta X| mean = 0.174842099
|delta Y| mean = 0.130357711
|delta Z| mean = 0.0946959016
~~~

Mean absolute intensity difference:

~~~text
3.68782668
~~~

The maximum coordinate differences include approximately:

~~~text
|delta X| max = 87.2979
|delta Y| max = 42.9908
|delta Z| max = 21.5627
~~~

### Why this matters

Because timestamp groups never contain more than two points, the very large maximum separation is **not** caused by accidentally comparing neighboring records inside a three-point or larger timestamp group.

The large separation exists inside an exact two-record timestamp group.

That means we still need to determine whether the extreme cases represent:

- legitimate multi-return geometry;
- vegetation or penetrable surfaces;
- scene transitions;
- export artifacts;
- timestamp reuse or quantization;
- registration problems;
- or another property of the originating system.

The mean alone is therefore not sufficient.

The next acquisition-oriented diagnostic should examine the distribution and largest outliers.

---

## 11. Finding: several LAS fields appear normalized or export-derived

Additional observed properties include:

~~~text
PointSourceId:
2424 for all 9,718,909 points

ScanDirectionFlag:
0 for all points

EdgeOfFlightLine:
0 for all points

NumberOfReturns:
2 for all points

ScanAngleRank:
0 to 15

Intensity:
0 to 255

RGB:
0 to 255 per channel
~~~

These fields are useful data, but their regularity reinforces the need to avoid assuming they preserve origi2las` provenance is particularly important here.

---

## 12. The main accuracy problem is not one algorithm

The final cubicación error budget may contain contributions from several independent layers.

### Acquisition

Potential error sources:

- sensor ranging error;
- incidence angle;
- reflectance;
- weather;
- movement;
- scanner distance;
- incomplete scan coverage.

### Registration / reconstruction

Potential error sources:

- SLAM drift;
- IMU error;
- loop closure;
- alignment between passes;
- bad calibration;
- registration artifacts.

### Scene visibility

Potential error sources:

- occlusion;
- vegetation;
- hidden log ends;
- logs behind other logs;
- inaccessible pile sides;
- incomplete top or rear surfaces.

### Point-cloud processing

Potential error sources:

- outliers;
- filtering;
- downsampling;
- wrong ROI;
- wrong orientation;
- background contamination.

### Timber interpretation

Potential error sources:

- incorrect log-end segmentation;
- partial circles;
- bark irregularities;
- ellipse perspective effects;
- overlapping logs;
- missing logs;
- false detections;
- diameter-fitting error.

### Hidden geometry

Potential error sources:

- unknown log length;
- varying log length;
- taper;
- non-cylindrical logs;
- invisible rear geometry;
- unknown internal pile arrangement.

### Commercial cubicación

Potential differences between:

- exterior pile volume;
- stacked volume;
- solid wood volume;
- sum of individual logs;
- forestry conversion factors;
- Campo Digital's own accepted commercial methodology.

### Ground truth

Potential uncertainty from:

- manual reference measurements;
- operator decisions;
- LiDAR360 settings;
- Pix4D settings;
- ROI definition;
- interpolation;
- conversion factors;
- measurement repeatability.

Therefore, asking whether “LiDAR is accurate” is not specific enough.

The complete pipeline must be evaluated.

---

## 13. The major observability limitation

Visual inspection in CloudCompare shows a large timber stack whose exposed face contains many visible circular or elliptical log ends.

Conceptually:

~~~text
 O   O  O    O O
   O   O  O
 O O   O   O O
  O   O O   O
~~~

Each visible end potentially contains information about:

- existence of a log;
- center;
- diameter;
- radius;
- cross-sectional area;
- local orientation.

However, a visible front end does not necessarily reveal the complete hidden geometry of the log.

For an ideal cylindrical log:

~~~text
V = pi * (d / 2)^2 * L
~~~

The visible circular end can help estimate:

~~~text
d
~~~

but the final volume also requires:

~~~text
L
~~~

If the length is hidden behind the front face, it must come from an additional source such as:

- known standardized log length;
- opposite-side scan;
- side geometry;
- stack-depth measurement;
- another sensor/view;
- operational metadata;
- or Campo Digital's measurement rule.

No algorithm can exactly reconstruct completely unobserved geometry without some additional information or assumption.

This is an information limitation, not merely an algorithm-quality problem.

---

## 14. The target "volume" is still not fully specified

The phrase "calculate the volume" is insufficient as a technical specification.

Possible target quantities include:

### Exterior pile volume

Volume occupied by the entire pile envelope, including air gaps.

### Solid wood volume

Only the timber material, excluding air between logs.

### Individual-log volume

Potentially:

~~~text
sum(pi * r_i^2 * L_i)
~~~

or a forestry-specific alternative.

### Cross-sectional stack method

Potentially:

~~~text
measured timber cross-sectional area * pile/log depth
~~~

### Stacked / commercial volume

A forestry or commercial conversion that may include:

- packing factors;
- standard lengths;
- bark treatment;
- species rules;
- conversion coefficients;
- client-specific methodology.

These quantities are not interchangeable.

Before accuracy can be evaluated, Campo Digital must define exactly which output is considered correct.

---

## 15. Ground truth is itself a measurement

A value produced by LiDAR360 or Pix4D is not automatically mathematical truth.

For each validation dataset we need, at minimum:

~~~text
same physical pile
same ROI / segment
reference value
reference unit
reference method
reference operator / procedure
relevant measurement date
~~~

Ideally we should also know:

- repeatability of the current method;
- expected uncertainty;
- operator variability;
- whether manual corrections were applied.

Only then is an error expression such as:

~~~text
relative error =
(V_estimate - V_reference)
/
V_reference
~~~

actually meaningful.

Until that reference exists, the project has **no defensible volume-accuracy percentage**.

---

## 16. Timber-wall working hypothesis

The current geometric hypothesis is to use the visible timber face as the first primary measurement target.

Proposed progression:

~~~text
full 9.7M-point cloud
        ↓
deterministic timber ROI
        ↓
local stack coordinate frame
        ↓
front-face extraction
        ↓
background / vegetation rejection
        ↓
individual log-end detection
        ↓
circle / ellipse / robust boundary fitting
        ↓
diameter estimates
        ↓
log count + detection QC
        ↓
length / depth information
        ↓
raw timber geometry
        ↓
Campo Digital cubicación rule
        ↓
validated result
~~~

This is preferable to immediately:

1. building a watertight mesh from the entire scene;
2. filling all visible and invisible gaps;
3. calculating its volume;
4. calling that result "timber m³".

A closed mesh or voxel occupancy value may still be useful as a comparison method, but it must not silently become the commercial cubicación definition.

---

## 17. Why detecting the visible log ends is promising

The visible circular ends may provide a more interpretable geometric signal than attempting to infer the complete stack exterior immediately.

A future log-end detector could potentially produce:

~~~text
log_id
center_x
center_y
diameter
fit_residual
coverage_fraction
confidence / QC status
~~~

For example:

~~~text
Log 001  diameter=...
Log 002  diameter=...
Log 003  diameter=...
...
~~~

This would provide several advantages:

- individual measurements are auditable;
- bad detections can be reviewed;
- missed logs are visible;
- diameter distributions can be compared;
- uncertainty can be attached to each detection;
- results can be overlaid in CloudCompare or another viewer.

This is more informative than producing only a single opaque volume number.

---

## 18. A robust future system should expose uncertainty

The eventual system should not merely output:

~~~text
103.4 m³
~~~

A stronger result would include information such as:

~~~text
measurement
method / cubicación rule
algorithm version
input dataset
ROI
logs detected
uncertain detections
coverage
quality checks
reference anchors
assumptions
warnings
repeatability / confidence metrics
~~~

The goal is to make uncertainty visible and reproducible rather than hiding it behind one number.

---

## 19. What has already been demonstrated

The project has now demonstrated that:

- the real Campo Digital LAS can be ingested successfully;
- the complete 9.7M-point dataset can be processed reproducibly;
- analysis can be performed in streaming mode rather than loading everything into RAM;
- client LAS/LAZ data remains outside Git;
- observed geometry can be recomputed independently of stale LAS header bounds;
- stale header bounds can be detected and reported;
- CRS absence is preserved rather than guessed;
- GPS-time ordering can be ana be reconstructed across streaming chunk boundaries;
- return-number relationships can be measured rather than assumed;
- the R1/R2 timestamp structure is highly deterministic;
- suspicious acquisition/export behavior can be surfaced;
- the timber wall is visually identifiable in the real dataset;
- the repository now contains a reproducible foundation for the next geometric experiments.

---

## 20. What has NOT been demonstrated

The project has **not yet demonstrated**:

- that the coordinate units are metres;
- the exact CRS;
- which exact sensor generated this LAS;
- the complete export/conversion chain;
- the physical meaning of every R1/R2 pair;
- that the paired-return maximum separation is physically meaningful;
- automatic timber-stack segmentation;
- automatic log-end detection;
- automatic log counting;
- validated diameter accuracy;
- validated pile depth;
- validated individual log lengths;
- validated raw timber volume;
- Campo Digital's commercial cubicación formula;
- the accepted reference value for this exact pile;
- final error relative to Campo Digital's reference;
- final m³ accuracy.

No final accuracy claim should currently be made.

---

## 21. Current interpretation of the accuracy problem

The original problem can be reframed.

It is not simply:

> find a mathematically better volume formula.

Instead:

> determine which physical timber geometry is observable, recover that geometry reproducibly from the available scan, explicitly model what remains hidden or assumed, apply the correct Campo Digital cubicación rule, and validate the complete result against a defensible reference.

This distinction matters because improvements may need to occur at different stages.

For example, a final discrepancy could come from:

~~~text
bad scan
rather than
bad geometry algorithm
~~~

or:

~~~text
good geometry
but
wrong commercial conversion rule
~~~

or:

~~~text
correct visible diameters
but
unknown log lengths
~~~

The system should eventually make these failure modes distinguishable.

---

## 22. Next engineering phase: deterministic timber-stack ROI

Generic full-cloud forensic analysis is now sufficiently mature to move toward the actual timber-measurement problem.

The next primary phase is:

# Phase C — deterministic timber-stack ROI

Objective:

> isolate the visible lumber wall reproducibly from the full point cloud.

The output should be an exact ROI definition stored as configuration or code.

The authoritative workflow must **not** be:

~~~text
open CloudCompare
manually crop something
save it
forget exactly how it was selected
~~~

Instead:

~~~text
full LAS
    ↓
explicit ROI configuration
    ↓
reproducible crop
    ↓
data/interim/timber-stack ROI
    ↓
CloudCompare verification
~~~

CloudCompare remains useful as a visual debugger and inspection tool.

The reproducible pipeline remains in code.

---

## 23. Phase D after ROI: front-face / log-end geometry

Once the lumber wall is isolated, the next experiment should answer:

1. Can the stack face be transformed into a stable local coordinate frame?
2. Is there a dominant plane or orientation representing the exposed log-end face?
3. Can foreground timber points be separated from vegetation/background?
4. Can individual circular or elliptical log ends be identified?
5. How many log ends are fully visible?
6. How many are partial or occluded?
7. How stable are diameter fits under different parameters?
8. Which detections should be marked uncertain rather than forced?
9. How much of the stack is actually observable from this acquWhat additional information is necessary to convert the visible face into Campo Digital's required cubicación result?

---

## 24. Additional acquisition analysis still worth performing

Although generic forensics should no longer dominate the work, one focused acquisition question remains useful.

The exact-pair distance distribution currently has:

~~~text
mean = 0.270756447
max  = 87.9410127
~~~

The distribution should therefore be characterized using robust percentiles such as:

~~~text
p50
p90
p95
p99
p99.9
max
~~~

The largest outliers should be exported to a local, gitignored diagnostic file containing fields such as:

~~~text
GPS timestamp
Return 1 XYZ
Return 2 XYZ
3D distance
delta X
delta Y
delta Z
Return 1 intensity
Return 2 intensity
scan angle
RGB if useful
~~~

Those points can then be inspected spatially to determine whether extreme pair separation is:

- isolated;
- associated with vegetation;
- associated with scene boundaries;
- associated with a particular scan interval;
- or systematic.

This is a diagnostic side task, not the main cubicación algorithm.

---

## 25. External information still required from Campo Digital

The highest-value unanswered questions are:

1. Which sensor produced `v01_MG_23jun2026.las`?
2. Was it DJI L2, XGRIDS K2, GEOSUN GS100G, or another device?
3. What CRS applies?
4. What are the coordinate linear units?
5. What software processed the original acquisition?
6. What exact export sequence produced this LAS?
7. Is this file already fully registered / SLAM-resolved?
8. What exact physical timber pile or segment does it represent?
9. What ROI corresponds to Campo Digital's reference measurement?
10. What reference volume exists for the same pile?
11. Was that reference produced with LiDAR360, Pix4D, manual measurement, or another process?
12. What exact quantity does Campo Digital call the final cubicación?
13. Are log lengths standardized or variable?
14. Are both sides of the pile normally scanned?
15. Is stack depth independently measured?
16. What does the requested `1–2 cm` tolerance specifically refer to?
17. What error in final cubicación is commercially acceptable?
18. What repeatability between operators is acceptable?

Until these questions are answered, geometry work can continue, but defensible absolute accuracy claims cannot.

---

## 26. Current decision

The project should now transition from:

~~~text
What exactly is inside this LAS?
~~~

toward:

~~~text
Can we reproducibly isolate the lumber wall
and recover the visible log-end geometry?
~~~

That is the first experiment directly attacking the core timber-cubicación problem.

The immediate next deliverable is therefore:

~~~text
full point cloud
        ↓
deterministic timber-stack ROI
        ↓
verified timber-only / timber-dominant crop
        ↓
front-face geometry experiment
        ↓
individual log-end detection experiment
~~~

Only after those stages, plus receipt of Campo Digital's reference measurement and cubicación definition, should the project attempt to make a validated m³ accuracy claim.
