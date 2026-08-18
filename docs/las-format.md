# LAS format notes

Quick reference for how this repo handles LAS/LAZ specifics. Not a full
LAS spec reproduction -- see the ASPRS LAS spec for authoritative detail:
https://www.asprs.org/divisions-committees/lidar-division/laser-las-file-format-exchange-activities

## Scale and offset

LAS stores X/Y/Z as scaled integers: `real_value = int_value * scale +
offset`. This repo:

- Never rewrites scale/offset implicitly. `lidar_io.inspect.inspect_las`
  reports the header's scale/offset verbatim.
- `lidar cli crop` preserves the source header (and therefore its
  scale/offset) when writing output.
- Tests (`tests/test_las_scale_offset.py`) assert a round-trip: written
  scale/offset equal what's read back, and bounds match input points
  within quantization error bounded by scale.

## Point formats

`inspect_las` reports the point-format id and enumerates the actual
dimension names present (`standard_dims`, `extra_dims`) rather than
assuming a fixed set of fields exist -- point formats 0-10 differ in
whether RGB, GPS time, waveform, or NIR are present.

## VLRs / EVLRs

Variable Length Records (and Extended VLRs, LAS 1.4+) carry CRS
(GeoKeys/WKT), and potentially other metadata (e.g. classification lookup
tables). `inspect_las` reports counts and short summaries; it does not
attempt to interpret every possible VLR type.

## Classification / return-number histograms

Computed via a **chunked streaming pass** (`laspy`'s `chunk_iterator`),
not a full in-memory load, so this scales to files larger than available
RAM.
