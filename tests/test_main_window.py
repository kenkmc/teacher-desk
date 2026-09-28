from __future__ import annotations

from PySide6.QtWidgets import QApplication

from teacher_desk.db import Database
from teacher_desk.ui.main_window import MainWindow


class FakeTray:
    def __init__(self) -> None:
        self.messages: list[tuple] = []
        self.hidden = False

    def showMessage(self, *args) -> None:  # noqa: N802
        self.messages.append(args)

    def hide(self) -> None:
        self.hidden = True


def test_window_x_hides_to_tray_and_button_quits(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Database(tmp_path / "desk.sqlite3"))
    tray = FakeTray()
    window.tray = tray
    window.show()

    window.close()
    assert not window.isVisible()
    assert window.reminder_timer.isActive()
    assert tray.messages

    window.show()
    window.quit_button.click()
    assert not window.isVisible()
    assert not window.reminder_timer.isActive()
    assert tray.hidden

    app.processEvents()
