"""OSM Diff Reviewer: compare reference data with OpenStreetMap and review the differences."""


def classFactory(iface):  # noqa: N802 - name required by QGIS
    from .plugin import OsmDiffReviewerPlugin

    return OsmDiffReviewerPlugin(iface)
