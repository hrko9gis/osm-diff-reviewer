from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtCore import QCoreApplication

from .algorithms import MatchAlgorithm


class OsmDiffReviewerProvider(QgsProcessingProvider):
    def id(self) -> str:
        return "osmdiffreviewer"

    def name(self) -> str:
        return QCoreApplication.translate("OsmDiffReviewer", "OSM Diff Reviewer")

    def loadAlgorithms(self) -> None:  # noqa: N802 - QGIS API
        self.addAlgorithm(MatchAlgorithm())
