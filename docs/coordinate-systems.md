# Coordinate systems

## Golden rule: never silently infer a CRS

If a LAS file's VLRs/EVLRs don't encode a CRS, `lidar_io.inspect_las`
reports `coordinate_metadata.is_explicit = False` and adds a
"CRS missing/ambiguous" warning -- it never guesses a plausible CRS (e.g.
"probably UTM 19S because that's Chile") from context.

## Reprojection

`pipelines/pdal/reproject.json` requires an explicit source CRS
(`in_srs`) and target CRS (`out_srs`) to be filled in by the operator --
the template intentionally contains placeholder tokens (`SOURCE_EPSG:XXXX`,
`EPSG:SOURCE`, `EPSG:TARGET`) rather than a default, so it cannot be run
as-is without a deliberate choice.

## Per-sensor considerations

- **DJI Zenmuse L2**: direct-georeferenced via onboard RTK GNSS + IMU when
  RTK is fixed; the RTK base station's CRS/datum must be recorded
  per-flight, not assumed from the LAS file alone.
- **GeoSun GS-100G / XGRIDS Lixel K2**: SLAM-based; output may be in a
  local/arbitrary coordinate frame unless explicitly georeferenced
  (e.g. via GCPs or GNSS-aided SLAM). Verify per export -- see
  `configs/sensors/*.yaml` (`crs_handling` field).

## Units

LAS headers do not always make horizontal/vertical units unambiguous
across all CRS definitions (e.g. US survey feet vs metres in some state
plane systems). `CoordinateMetadata.horizontal_units` is only populated
when explicitly determinable from the CRS definition -- it is left `None`
otherwise rather than assumed to be metres.
