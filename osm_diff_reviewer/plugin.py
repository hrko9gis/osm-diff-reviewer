"""Plugin entry point: Processing provider, menu action and review dock."""

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt

from .i18n import tr
from .processing.provider import OsmDiffReviewerProvider

MENU = "&OSM Diff Reviewer"


class OsmDiffReviewerPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider: OsmDiffReviewerProvider | None = None
        self.dock = None
        self.action = None

    def initProcessing(self) -> None:  # noqa: N802 - QGIS plugin API
        if self.provider is None:
            self.provider = OsmDiffReviewerProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa: N802 - QGIS plugin API
        from .gui.review_dock import ReviewDock

        self.initProcessing()
        self.dock = ReviewDock(self.iface, self.iface.mainWindow())
        self.dock.hide()
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.action = self.dock.toggleViewAction()
        self.action.setText(tr("Review panel"))
        self.iface.addPluginToMenu(MENU, self.action)

    def unload(self) -> None:
        if self.action is not None:
            self.iface.removePluginMenu(MENU, self.action)
            self.action = None
        if self.dock is not None:
            self.dock.cleanup()
            self.iface.removeDockWidget(self.dock)
            self.dock.close()
            self.dock.deleteLater()
            self.dock = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
