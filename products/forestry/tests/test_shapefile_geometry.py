"""Geometry decoding tests using fully synthetic .shp files.

No real Forestry client data is used or reproduced here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely import wkb as shapely_wkb

from forestry_family_fixtures import (
    SQUARE,
    RecordGeometry,
    square_ring,
    write_shp_and_shx,
)
from forestry_ingestion.shapefile_contract import EXPECTED_PRJ_WKT
from forestry_ingestion.shapefile_geometry import (
    SOURCE_STORAGE_SRID,
    ForestryGeometryError,
    decode_polygon_records,
)


def _write_shp(tmp_path: Path, geometries: list[RecordGeometry]) -> Path:
    shp_path = tmp_path / "synthetic.shp"
    write_shp_and_shx(shp_path, tmp_path / "synthetic.shx", geometries)
    return shp_path


def test_storage_srid_matches_authoritative_epsg_mapping_of_contract_wkt() -> None:
    pyproj = pytest.importorskip("pyproj")

    crs = pyproj.CRS.from_wkt(EXPECTED_PRJ_WKT)

    assert crs.to_epsg(min_confidence=25) == SOURCE_STORAGE_SRID == 32718


def test_decodes_single_clockwise_ring_as_valid_multipolygon(tmp_path: Path) -> None:
    shp_path = _write_shp(tmp_path, [[SQUARE]])

    (feature,) = decode_polygon_records(shp_path)

    assert feature.record_number == 1
    assert feature.is_valid is True
    assert feature.invalid_reason is None
    assert feature.ring_count == 1
    assert feature.part_count == 1
    assert feature.area_source_units == pytest.approx(100.0)

    geometry = shapely_wkb.loads(feature.wkb)
    assert geometry.geom_type == "MultiPolygon"
    (polygon,) = geometry.geoms
    assert list(polygon.exterior.coords) == SQUARE
    assert list(polygon.interiors) == []


def test_decodes_hole_ring_into_containing_exterior(tmp_path: Path) -> None:
    exterior = square_ring(0.0, 0.0, 10.0, clockwise=True)
    hole = square_ring(4.0, 4.0, 2.0, clockwise=False)
    shp_path = _write_shp(tmp_path, [[exterior, hole]])

    (feature,) = decode_polygon_records(shp_path)

    assert feature.is_valid is True
    assert feature.ring_count == 2
    assert feature.part_count == 1
    assert feature.area_source_units == pytest.approx(96.0)

    (polygon,) = shapely_wkb.loads(feature.wkb).geoms
    assert len(polygon.interiors) == 1
    assert list(polygon.interiors[0].coords) == hole


def test_decodes_two_exteriors_as_two_parts(tmp_path: Path) -> None:
    first = square_ring(0.0, 0.0, 10.0, clockwise=True)
    second = square_ring(20.0, 0.0, 5.0, clockwise=True)
    shp_path = _write_shp(tmp_path, [[first, second]])

    (feature,) = decode_polygon_records(shp_path)

    assert feature.is_valid is True
    assert feature.ring_count == 2
    assert feature.part_count == 2
    assert feature.area_source_units == pytest.approx(125.0)


def test_assigns_hole_to_smallest_containing_exterior(tmp_path: Path) -> None:
    outer = square_ring(0.0, 0.0, 20.0, clockwise=True)
    lake = square_ring(2.0, 2.0, 16.0, clockwise=False)
    island = square_ring(4.0, 4.0, 12.0, clockwise=True)
    pond = square_ring(6.0, 6.0, 8.0, clockwise=False)
    shp_path = _write_shp(tmp_path, [[outer, lake, island, pond]])

    (feature,) = decode_polygon_records(shp_path)

    assert feature.is_valid is True
    assert feature.ring_count == 4
    assert feature.part_count == 2

    geometry = shapely_wkb.loads(feature.wkb)
    by_exterior_bounds = {polygon.bounds: polygon for polygon in geometry.geoms}
    outer_polygon = by_exterior_bounds[(0.0, 0.0, 20.0, 20.0)]
    island_polygon = by_exterior_bounds[(4.0, 4.0, 16.0, 16.0)]

    assert [tuple(interior.coords) for interior in outer_polygon.interiors] == [tuple(lake)]
    assert [tuple(interior.coords) for interior in island_polygon.interiors] == [tuple(pond)]


def test_orphan_hole_ring_is_preserved_as_its_own_part(tmp_path: Path) -> None:
    exterior = square_ring(0.0, 0.0, 10.0, clockwise=True)
    orphan = square_ring(20.0, 20.0, 5.0, clockwise=False)
    shp_path = _write_shp(tmp_path, [[exterior, orphan]])

    (feature,) = decode_polygon_records(shp_path)

    assert feature.ring_count == 2
    assert feature.part_count == 2
    assert feature.area_source_units == pytest.approx(125.0)


def test_preserves_self_intersecting_ring_and_reports_invalidity(tmp_path: Path) -> None:
    bowtie = [(0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0), (0.0, 0.0)]
    shp_path = _write_shp(tmp_path, [[bowtie]])

    (feature,) = decode_polygon_records(shp_path)

    assert feature.is_valid is False
    assert feature.invalid_reason is not None
    assert "Self-intersection" in feature.invalid_reason

    (polygon,) = shapely_wkb.loads(feature.wkb).geoms
    assert list(polygon.exterior.coords) == bowtie


def test_decodes_multiple_records_in_order(tmp_path: Path) -> None:
    shp_path = _write_shp(
        tmp_path,
        [[square_ring(0.0, 0.0, 1.0)], [square_ring(5.0, 5.0, 2.0)]],
    )

    features = decode_polygon_records(shp_path)

    assert [feature.record_number for feature in features] == [1, 2]
    assert features[0].area_source_units == pytest.approx(1.0)
    assert features[1].area_source_units == pytest.approx(4.0)


def test_rejects_null_shape_record(tmp_path: Path) -> None:
    shp_path = _write_shp(tmp_path, [[SQUARE], None])

    with pytest.raises(ForestryGeometryError, match="null shape"):
        decode_polygon_records(shp_path)


def test_rejects_ring_with_too_few_points(tmp_path: Path) -> None:
    degenerate = [(0.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
    shp_path = _write_shp(tmp_path, [[degenerate]])

    with pytest.raises(ForestryGeometryError, match="fewer than 4 points"):
        decode_polygon_records(shp_path)


def test_rejects_truncated_record(tmp_path: Path) -> None:
    shp_path = _write_shp(tmp_path, [[SQUARE]])
    raw = shp_path.read_bytes()
    shp_path.write_bytes(raw[:-8])

    with pytest.raises(ForestryGeometryError, match="truncated"):
        decode_polygon_records(shp_path)
