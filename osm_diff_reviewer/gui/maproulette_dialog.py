"""MapRoulette hand-over for the candidates shown in the review panel (spec 5.7)."""

from qgis.gui import QgsAuthConfigSelect
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import settings
from ..core.review import ReviewRow
from ..data.credentials import CredentialError, api_key_from_authcfg
from ..data.http import QgisHttpClient
from ..data.license_gate import LicenseGateError, export_allowed
from ..data.store import StoreError, WorkspaceStore
from ..export import maproulette as mr
from ..i18n import tr
from .background import BackgroundRunner

DEFAULT_TEMPLATE = "{classification}: {ref_key} {@id}"
IMPORT_GUIDELINES_URL = "https://wiki.openstreetmap.org/wiki/Import/Guidelines"


class MapRouletteDialog(QDialog):
    def __init__(self, store: WorkspaceStore, source_name: str, rows: list[ReviewRow], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("MapRoulette"))
        self.store = store
        self.source_name = source_name
        self.rows = list(rows)
        self._projects: list[tuple[int, str]] | None = None
        self._new_challenge: int | None = None
        self.runner = BackgroundRunner(self._on_busy_changed, self._message)
        self._build_ui()
        self._refresh_challenges()
        self._apply_licence()

    # ----- layout ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.summary_label = QLabel(
            tr("{} candidate(s) of '{}' — those currently shown in the review panel.").format(
                len(self.rows), self.source_name
            )
        )
        self.licence_label = QLabel()
        self.licence_label.setWordWrap(True)
        self.licence_label.setOpenExternalLinks(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.licence_label)
        layout.addWidget(self._export_group())
        layout.addWidget(self._connection_group())
        layout.addWidget(self._create_group())
        layout.addWidget(self._sync_group())
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _export_group(self) -> QGroupBox:
        self.template_edit = QLineEdit(DEFAULT_TEMPLATE)
        self.template_edit.setToolTip(
            tr("Task description; {name} is replaced by a task property, e.g. {ref_key}, {@id}, {ref:FIELD}")
        )
        self.line_by_line_check = QCheckBox(tr("Line-by-line GeoJSON (one task per line)"))
        self.export_button = QPushButton(tr("Export GeoJSON…"))
        self.export_button.clicked.connect(lambda: self.export_geojson())
        group = QGroupBox(tr("1. Tasks as GeoJSON"))
        form = QFormLayout(group)
        form.addRow(tr("Task description"), self.template_edit)
        form.addRow(self.line_by_line_check)
        form.addRow(self.export_button)
        return group

    def _connection_group(self) -> QGroupBox:
        self.url_edit = QLineEdit(settings.maproulette_url())
        self.auth_select = QgsAuthConfigSelect(self)
        self.auth_select.setConfigId(settings.maproulette_authcfg())
        self.auth_select.setToolTip(
            tr("Store the MapRoulette API key as 'API Header' (header apiKey) or as the password of a 'Basic' config")
        )
        group = QGroupBox(tr("MapRoulette server"))
        form = QFormLayout(group)
        form.addRow(tr("API URL"), self.url_edit)
        form.addRow(tr("API key"), self.auth_select)
        return group

    def _create_group(self) -> QGroupBox:
        self.project_combo = QComboBox()
        self.load_projects_button = QPushButton(tr("Load my projects"))
        self.load_projects_button.clicked.connect(self.load_projects)
        project_row = QHBoxLayout()
        project_row.addWidget(self.project_combo, 1)
        project_row.addWidget(self.load_projects_button)
        self.name_edit = QLineEdit()
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(60)
        self.instruction_edit = QPlainTextEdit()
        self.instruction_edit.setMaximumHeight(80)
        self.checkin_edit = QLineEdit()
        self.checkin_edit.setPlaceholderText(tr("Changeset comment, e.g. #hashtag"))
        self.enabled_check = QCheckBox(tr("Publish immediately"))
        self.enabled_check.setToolTip(tr("Leave off and publish on MapRoulette after consulting the local community"))
        self.create_button = QPushButton(tr("Create challenge"))
        self.create_button.clicked.connect(self.create_challenge)
        group = QGroupBox(tr("2. Create a challenge"))
        form = QFormLayout(group)
        form.addRow(tr("Project"), project_row)
        form.addRow(tr("Name"), self.name_edit)
        form.addRow(tr("Description"), self.description_edit)
        form.addRow(tr("Instructions"), self.instruction_edit)
        form.addRow(tr("Changeset comment"), self.checkin_edit)
        form.addRow(self.enabled_check)
        form.addRow(self.create_button)
        return group

    def _sync_group(self) -> QGroupBox:
        self.challenge_combo = QComboBox()
        self.sync_button = QPushButton(tr("Sync task states"))
        self.sync_button.clicked.connect(self.sync)
        group = QGroupBox(tr("3. Progress"))
        row = QHBoxLayout(group)
        row.addWidget(QLabel(tr("Challenge")))
        row.addWidget(self.challenge_combo, 1)
        row.addWidget(self.sync_button)
        return group

    # ----- state -------------------------------------------------------------------

    def _source(self):
        try:
            return self.store.reference_source(self.source_name)
        except StoreError:
            return None

    def _apply_licence(self) -> None:
        allowed = export_allowed(self._source())
        self.licence_label.setText(
            tr("Licence confirmed. Before publishing a large challenge, consult your local community "
               '(<a href="{}">Import Guidelines</a>).').format(IMPORT_GUIDELINES_URL)
            if allowed
            else tr("Export is blocked: the licence of this reference data is not confirmed (use Licence… in the "
                    "review panel). Progress sync of existing challenges still works.")
        )
        self._on_busy_changed(self.runner.running())

    def _on_busy_changed(self, busy: bool) -> None:
        allowed = export_allowed(self._source())
        self.export_button.setEnabled(allowed and not busy)
        self.create_button.setEnabled(allowed and not busy)
        self.load_projects_button.setEnabled(not busy)
        self.sync_button.setEnabled(not busy)
        if not busy:
            self._take_results()

    def _take_results(self) -> None:
        """Results set by background actions are shown here, on the GUI thread."""
        if self._projects is not None:
            self.project_combo.clear()
            for project_id, name in self._projects:
                self.project_combo.addItem(f"{name} ({project_id})", project_id)
            self._projects = None
        if self._new_challenge is not None:
            self._refresh_challenges()
            self.challenge_combo.setCurrentIndex(self.challenge_combo.findData(self._new_challenge))
            self._new_challenge = None

    def _refresh_challenges(self) -> None:
        self.challenge_combo.clear()
        try:
            ids = self.store.challenge_ids(self.source_name)
        except StoreError as error:
            self._message(str(error))
            return
        for challenge_id in ids:
            self.challenge_combo.addItem(str(challenge_id), challenge_id)

    def _message(self, text: str) -> None:
        self.message_label.setText(text)

    def _client(self) -> mr.MapRouletteClient:
        """Read connection settings on the GUI thread; remember them for next time."""
        url, authcfg = self.url_edit.text().strip() or settings.DEFAULT_MAPROULETTE_URL, self.auth_select.configId()
        settings.set_maproulette_url(url)
        settings.set_maproulette_authcfg(authcfg)
        return mr.MapRouletteClient(QgisHttpClient(), url, api_key_from_authcfg(authcfg))

    def _run(self, description: str, action) -> None:
        try:
            client = self._client()
        except (CredentialError, mr.MapRouletteError) as error:
            self._message(str(error))
            return
        self.runner.run(description, lambda: self._guarded(action, client))

    @staticmethod
    def _guarded(action, client) -> str:
        try:
            return action(client)
        except (mr.MapRouletteError, LicenseGateError, StoreError) as error:
            return str(error)

    # ----- actions -----------------------------------------------------------------

    def export_geojson(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export tasks"), "", tr("GeoJSON (*.geojson *.json)"))
            if not path:
                return
        try:
            mr.write_geojson(path, self.rows, self.template_edit.text(), self._source(), self.line_by_line_check.isChecked())
        except (LicenseGateError, mr.MapRouletteError, OSError) as error:
            self._message(str(error))
            return
        self._message(tr("Wrote {} task(s) to {}").format(len(self.rows), path))

    def load_projects(self) -> None:
        def action(client: mr.MapRouletteClient) -> str:
            self._projects = client.managed_projects()
            return tr("{} project(s) loaded.").format(len(self._projects))

        self._run(tr("Load MapRoulette projects"), action)

    def create_challenge(self) -> None:
        spec = mr.ChallengeSpec(
            project_id=self.project_combo.currentData() or 0,
            name=self.name_edit.text(),
            description=self.description_edit.toPlainText(),
            instruction=self.instruction_edit.toPlainText(),
            checkin_comment=self.checkin_edit.text(),
            enabled=self.enabled_check.isChecked(),
        )
        rows, template, source = self.rows, self.template_edit.text(), self._source()

        def action(client: mr.MapRouletteClient) -> str:
            self._new_challenge = mr.create_challenge_for_rows(client, self.store, spec, rows, template, source)
            return tr("Created challenge {} with {} task(s). MapRoulette builds the tasks in the background.").format(
                self._new_challenge, len(rows)
            )

        self._run(tr("Create MapRoulette challenge"), action)

    def sync(self) -> None:
        challenge_id = self.challenge_combo.currentData()
        if challenge_id is None:
            self._message(tr("No challenge has been created for this reference source yet."))
            return

        def action(client: mr.MapRouletteClient) -> str:
            report = mr.sync_challenge(client, self.store, self.source_name, challenge_id)
            return tr(
                "Updated {} review(s); {} unchanged; {} not in the latest run; {} unknown task(s)."
            ).format(report.updated, report.unchanged, report.not_in_run, report.unknown_tasks)

        self._run(tr("Sync MapRoulette tasks"), action)

    def done(self, result: int) -> None:  # noqa: D401 - Qt API
        if self.runner.running():
            # The request writes to the workspace when it ends; let it finish so the panel reloads its result.
            self._message(tr("Please wait until the current request has finished."))
            return
        self.runner.close()
        super().done(result)
