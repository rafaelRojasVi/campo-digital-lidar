# Accuracy terminology (do not conflate these)

Different, non-interchangeable concepts, each of which sensor
datasheets/documentation may report separately or not at all:

- **Range precision**: the noise/repeatability of a single laser
  range measurement to a fixed target, usually in mm at a stated
  distance/reflectivity. Not the same as accuracy (bias may still exist).
- **Point-cloud thickness**: the apparent "fuzziness"/spread of points
  sampling what is physically a thin surface, resulting from range noise,
  angular quantization, and multi-path effects. Directly affects
  voxel/mesh volume estimates.
- **Relative / local precision**: how consistent nearby points are with
  each other (e.g. flatness of a scanned flat surface), independent of
  whether the whole cloud is correctly positioned in world coordinates.
- **Absolute XYZ accuracy**: how close the point cloud's coordinates are
  to true world coordinates in a stated CRS/datum -- depends on
  georeferencing method (RTK fix quality, GCPs, SLAM loop closure) as much
  as the sensor's raw ranging performance.
- **Registration accuracy**: for multi-scan or SLAM-based captures, how
  well individual scans/frames are aligned to each other (loop-closure
  drift, ICP residuals).
- **Repeatability**: whether re-scanning the same target under similar
  conditions produces the same measurement -- distinct from accuracy
  (repeatable but biased is possible).
- **Final volume error**: the end-to-end error in a reported timber
  volume, which compounds range precision, point-cloud thickness,
  registration, absolute accuracy, ROI/segmentation choices, and the
  volume-estimation method's own bias (e.g. convex-hull underestimation on
  concave cross-sections). This is the number that actually matters
  commercially and is NOT directly readable off any single sensor spec.

No sensor config in `configs/sensors/*.yaml` claims a "final volume error"
figure -- that can only be established empirically, per method, against
reference measurements (`ReferenceMeasurement` in `lidar_core.models`).
