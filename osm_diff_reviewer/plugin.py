"""Plugin entry point: registers the Processing provider (the review dock arrives in M2)."""

from qgis.core import QgsApplication

from .processing.provider import OsmDiffReviewerProvider


class OsmDiffReviewerPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider: OsmDiffReviewerProvider | None = None

    def initProcessing(self) -> None:  # noqa: N802 - QGIS plugin API
        if self.provider is None:
            self.provider = OsmDiffReviewerProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa: N802 - QGIS plugin API
        self.initProcessing()

    def unload(self) -> None:
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
