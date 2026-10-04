"""Run one network action at a time off the GUI thread and report its message."""

from collections.abc import Callable

from qgis.core import QgsApplication, QgsTask

from ..i18n import tr


class BackgroundRunner:
    def __init__(self, on_busy_changed: Callable[[bool], None], on_message: Callable[[str], None]) -> None:
        self._on_busy_changed = on_busy_changed
        self._on_message = on_message
        self._task: QgsTask | None = None
        self._closed = False

    def running(self) -> bool:
        return self._task is not None

    def run(self, description: str, action: Callable[[], str]) -> bool:
        """Start ``action`` (returns a message) unless one is running; False when refused."""
        if self.running() or self._closed:
            return False

        def finished(exception, result=None) -> None:
            if self._closed:  # the widget is gone; nothing to update
                return
            self._task = None
            self._on_busy_changed(False)
            self._on_message(str(exception) if exception else result or "")

        self._task = QgsTask.fromFunction(description, lambda task: action(), on_finished=finished)
        self._on_busy_changed(True)
        self._on_message(tr("Working…"))
        QgsApplication.taskManager().addTask(self._task)
        return True

    def close(self) -> None:
        self._closed = True
