# External point-cloud datasets for future validation

These datasets are intentionally out of scope for the current Campo Digital
measurement implementation. They are retained for later robustness,
cross-sensor, performance, and forestry validation.

They must not be interpreted as ground truth for Campo Digital timber
cubicacion.

## Chile

### Central Chile Pinus pinea UAV LiDAR

Forestry UAV-LiDAR dataset acquired with DJI Matrice 300 RTK + Zenmuse L1.
Useful for future DJI / forestry / LAS compatibility testing.

Access is currently restricted.

https://zenodo.org/records/14989428

### Santiago large point cloud

OpenTopography point-cloud dataset over Santiago.

Useful primarily for:
- large-file ingestion
- LAZ compatibility
- CRS handling
- memory/performance testing

Not a timber-volume validation dataset.

https://portal.opentopography.org/dataspace/dataset\?opentopoID\=OTDS.022021.32719.2

### San Ramon Fault large point cloud

Large Chilean OpenTopography dataset.

Useful primarily for:
- large-file ingestion
- LAZ compatibility
- classification handling
- CRS handling
- performance/stress testing

Not a timber-volume validation dataset.

https://portal.opentopography.org/dataspace/dataset\?opentopoID\=OTDS.022021.32719.1

## International forestry

### Multi-platform forestry LiDAR dataset

Large forestry dataset containing multiple acquisition platforms and formats,
including terrestrial/mobile/UAV point clouds.

Useful later for testing whether the processing pipeline remains robust across
different sensors and acquisition systems.

https://zenodo.org/records/17186174

### SegmentedForests

Large labelled forestry TLS/MLS point-cloud corpus.

Potential future use:
- wood/non-wood segmentation research
- automatic timber classification
- detector benchmarking
- ML experiments if geometric approaches become insufficient

https://zenodo.org/records/17396681

## Validation hierarchy

These datasets answer different questions:

1. Campo Digital real LAS
   - domain-specific engineering baseline

2. External large LAS/LAZ
   - software robustness and performance

3. External forestry LiDAR
   - cross-sensor and forestry robustness

4. Campo Digital same-pile ground truth
   - actual cubicacion accuracy

Only item 4 can validate the commercial measurement target.
