"""Map highlighting of the reference and OSM sides of a candidate."""

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtGui import QColor

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
REFERENCE_COLOR = QColor(230, 120, 0)
OSM_COLOR = QColor(30, 110, 230)
POINT_ZOOM_SCALE = 2000
EXTENT_MARGIN = 1.6


def make_band(canvas: QgsMapCanvas, color: QColor) -> QgsRubberBand:
    band = QgsRubberBand(canvas)
    band.setColor(color)
    fill = QColor(color)
    fill.setAlpha(50)
    band.setFillColor(fill)
    band.setWidth(3)
    band.setIconSize(14)
    band.setIcon(QgsRubberBand.IconType.ICON_CIRCLE)
    return band


def show(band: QgsRubberBand, wkt: str) -> QgsGeometry | None:
    """Draw a WGS84 WKT geometry on the band; returns it, or None when there is nothing to draw."""
    geometry = QgsGeometry.fromWkt(wkt) if wkt else QgsGeometry()
    if geometry.isNull() or geometry.isEmpty():
        band.reset()
        return None
    band.reset(geometry.type())
    band.setToGeometry(geometry, WGS84)
    return geometry


def zoom_to(canvas: QgsMapCanvas, geometries: list[QgsGeometry]) -> None:
    if not geometries:
        return
    extent = QgsRectangle(geometries[0].boundingBox())
    for geometry in geometries[1:]:
        extent.combineExtentWith(geometry.boundingBox())
    transform = QgsCoordinateTransform(WGS84, canvas.mapSettings().destinationCrs(), QgsProject.instance())
    extent = transform.transformBoundingBox(extent)
    if extent.width() == 0 or extent.height() == 0:
        canvas.setCenter(extent.center())
        canvas.zoomScale(POINT_ZOOM_SCALE)
    else:
        extent.scale(EXTENT_MARGIN)
        canvas.setExtent(extent)
    canvas.refresh()
