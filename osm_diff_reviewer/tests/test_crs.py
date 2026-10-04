from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY

from osm_diff_reviewer.core.crs import choose_working_crs


def test_projected_project_crs_is_used_as_is(qgis_app):
    project_crs = QgsCoordinateReferenceSystem("EPSG:6677")  # JGD2011 / Japan Plane Rectangular CS IX
    assert choose_working_crs(project_crs, QgsPointXY(139.7, 35.68)).authid() == "EPSG:6677"


def test_geographic_project_crs_falls_back_to_utm_north(qgis_app):
    project_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    assert choose_working_crs(project_crs, QgsPointXY(139.7, 35.68)).authid() == "EPSG:32654"


def test_utm_south_for_southern_hemisphere(qgis_app):
    assert choose_working_crs(None, QgsPointXY(151.2, -33.9)).authid() == "EPSG:32756"


def test_longitude_180_maps_to_zone_60(qgis_app):
    assert choose_working_crs(None, QgsPointXY(180.0, 10.0)).authid() == "EPSG:32660"


def test_web_mercator_is_not_used_for_distances(qgis_app):
    project_crs = QgsCoordinateReferenceSystem("EPSG:3857")
    assert choose_working_crs(project_crs, QgsPointXY(139.7, 35.68)).authid() == "EPSG:32654"


def test_non_metre_projected_crs_is_not_used(qgis_app):
    project_crs = QgsCoordinateReferenceSystem("EPSG:2263")  # NY Long Island, US feet
    assert choose_working_crs(project_crs, QgsPointXY(-73.9, 40.7)).authid() == "EPSG:32618"
