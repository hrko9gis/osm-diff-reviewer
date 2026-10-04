"""Choice of the projected CRS in which distances and areas are measured."""

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsPointXY

UTM_ZONE_WIDTH_DEG = 6
UTM_ZONE_COUNT = 60


def choose_working_crs(
    project_crs: QgsCoordinateReferenceSystem | None, center_wgs84: QgsPointXY
) -> QgsCoordinateReferenceSystem:
    """Use the project CRS when it is projected, otherwise the WGS84 UTM zone of the data centre."""
    if _measures_true_metres(project_crs):
        return project_crs
    zone = int((center_wgs84.x() + 180) // UTM_ZONE_WIDTH_DEG) + 1
    zone = min(max(zone, 1), UTM_ZONE_COUNT)
    base = 32600 if center_wgs84.y() >= 0 else 32700
    return QgsCoordinateReferenceSystem(f"EPSG:{base + zone}")


def _measures_true_metres(crs: QgsCoordinateReferenceSystem | None) -> bool:
    """Projected, in metres and not Mercator (whose metres stretch by 1/cos(latitude))."""
    return (
        crs is not None
        and crs.isValid()
        and not crs.isGeographic()
        and crs.mapUnits() == Qgis.DistanceUnit.Meters
        and crs.projectionAcronym() != "merc"
    )
