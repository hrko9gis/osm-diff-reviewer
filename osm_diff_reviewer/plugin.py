"""Plugin entry point: Processing provider, menu action and review dock."""

from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

from .i18n import install_translator, remove_translator, tr
from .processing.provider import OsmDiffReviewerProvider

MENU = "&OSM Diff Reviewer"
ICON = Path(__file__).resolve().parent / "icon.png"


class OsmDiffReviewerPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.translator = install_translator()  # before any widget or algorithm is created
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
        self.action.setIcon(QIcon(str(ICON)))
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
        remove_translator(self.translator)
        self.translator = None
