"""Table model of review rows and the filter/sort proxy used by the review dock."""

from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from ..core import matching, review, version_diff
from ..core.review import ReviewRow
from ..i18n import tr

COLUMNS = ("ref_key", "osm", "classification", "change", "total_score", "status", "needs_recheck", "note")
_HEADERS = {
    "ref_key": "Reference key",
    "osm": "OSM",
    "classification": "Classification",
    "change": "Version change",
    "total_score": "Score",
    "status": "Status",
    "needs_recheck": "Recheck",
    "note": "Note",
}
_CLASSIFICATION_LABELS = {
    matching.MATCH: "Match",
    matching.MISSING: "Missing in OSM",
    matching.GEOMETRY_DIFF: "Geometry differs",
    matching.ATTRIBUTE_DIFF: "Attributes differ",
    matching.AMBIGUOUS: "Ambiguous",
    matching.OSM_ONLY: "OSM only",
}
_CHANGE_LABELS = {
    version_diff.ADDED: "Added",
    version_diff.REMOVED: "Removed",
    version_diff.CHANGED: "Changed",
}
_VERDICT_LABELS = {
    version_diff.IN_OSM: "already in OSM",
    version_diff.NOT_IN_OSM: "not in OSM",
    version_diff.STILL_IN_OSM: "still in OSM",
    version_diff.GONE_FROM_OSM: "gone from OSM",
    version_diff.OSM_HAS_OLD: "OSM has the old state",
    version_diff.OSM_REFLECTS_NEW: "OSM already updated",
    version_diff.UNDECIDED: "undecided",
    version_diff.VERDICT_AMBIGUOUS: "ambiguous",
}
SORT_ROLE = Qt.ItemDataRole.UserRole


def change_label(row: ReviewRow) -> str:
    if not row.change_kind:
        return ""
    kind = tr(_CHANGE_LABELS.get(row.change_kind, row.change_kind))
    verdict = tr(_VERDICT_LABELS.get(row.verdict, row.verdict))
    return f"{kind}: {verdict}" if verdict else kind


def classification_label(code: str) -> str:
    return tr(_CLASSIFICATION_LABELS.get(code, code))


def osm_label(row: ReviewRow) -> str:
    if not row.osm_type:
        return ""
    version = f" v{row.osm_version}" if row.osm_version is not None else ""
    return f"{row.osm_type}/{row.osm_id}{version}"


def _display(row: ReviewRow, column: str) -> str:
    if column == "ref_key":
        return row.ref_key or ""
    if column == "osm":
        return osm_label(row)
    if column == "classification":
        return classification_label(row.classification)
    if column == "change":
        return change_label(row)
    if column == "total_score":
        return "" if row.total_score is None else f"{row.total_score:.2f}"
    if column == "status":
        return review.status_label(row.status, tr)
    if column == "needs_recheck":
        return tr("Recheck") if row.needs_recheck else ""
    return row.note


def _sort_key(row: ReviewRow, column: str):
    if column == "total_score":
        return -1.0 if row.total_score is None else row.total_score
    if column == "needs_recheck":
        return int(row.needs_recheck)
    return _display(row, column)


class ReviewTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[ReviewRow] = []

    def set_rows(self, rows: list[ReviewRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row(self, index: int) -> ReviewRow:
        return self._rows[index]

    def replace_row(self, index: int, row: ReviewRow) -> None:
        self._rows = [*self._rows[:index], row, *self._rows[index + 1 :]]
        self.dataChanged.emit(self.index(index, 0), self.index(index, len(COLUMNS) - 1))

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = self._rows[index.row()], COLUMNS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return _display(row, column)
        if role == SORT_ROLE:
            return _sort_key(row, column)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802 - Qt API
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(_HEADERS[COLUMNS[section]])
        return None


class ReviewFilterProxy(QSortFilterProxyModel):
    """Default view: no matches and no "not needed" decisions unless they need a recheck."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self._classification: str | None = None
        self._status: str | None = None
        self._show_matches = False
        self._show_hidden = False
        self._recheck_only = False

    def _update(self, attribute: str, value) -> None:
        setattr(self, attribute, value)
        self.invalidateFilter()

    def set_classification(self, code: str | None) -> None:
        self._update("_classification", code)

    def set_status(self, status: str | None) -> None:
        self._update("_status", status)

    def set_show_matches(self, show: bool) -> None:
        self._update("_show_matches", show)

    def set_show_hidden(self, show: bool) -> None:
        self._update("_show_hidden", show)

    def set_recheck_only(self, only: bool) -> None:
        self._update("_recheck_only", only)

    def row_at(self, proxy_index) -> ReviewRow:
        return self.sourceModel().row(self.mapToSource(proxy_index).row())

    def filterAcceptsRow(self, source_row, source_parent) -> bool:  # noqa: N802 - Qt API
        row = self.sourceModel().row(source_row)
        if self._classification is not None:
            if row.classification != self._classification:
                return False
        elif row.classification == matching.MATCH and not row.change_kind and not self._show_matches:
            return False  # rows of a version-diff run are the change set itself: never hidden as matches
        if self._status is not None:
            if row.status != self._status:
                return False
        elif review.is_hidden_by_default(row.status, row.needs_recheck) and not self._show_hidden:
            return False
        return row.needs_recheck or not self._recheck_only
