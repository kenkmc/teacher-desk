from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from teacher_desk import __version__
from teacher_desk.db import Database
from teacher_desk.modules.registry import ModuleSpec, available_modules
from teacher_desk.services.reminders import due_occurrence
from teacher_desk.ui.styles import APP_QSS


class MainWindow(QMainWindow):
    def __init__(self, database: Database | None = None) -> None:
        super().__init__()
        self.database = database or Database()
        self.modules: list[ModuleSpec] = available_modules()
        self.setWindowTitle(f"課務台　v{__version__}")
        self.resize(1180, 760)
        self.setStyleSheet(APP_QSS)
        self._build()
        self._setup_reminders()

    def _build(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 16, 0, 16)
        brand = QLabel("課務台")
        brand.setStyleSheet("color: #cad2c5; font-size: 14pt; font-weight: 700; padding: 0 16px 12px 16px;")
        subtitle = QLabel("教師課務與文件工具")
        subtitle.setStyleSheet("color: #84a98c; padding: 0 16px 8px 16px;")
        version = QLabel(f"v{__version__}")
        version.setStyleSheet("color: #84a98c; padding: 0 16px 12px 16px;")
        self.module_list = QListWidget()
        self.module_list.setObjectName("ModuleList")
        side_layout.addWidget(brand)
        side_layout.addWidget(subtitle)
        side_layout.addWidget(version)
        side_layout.addWidget(self.module_list, 1)
        self.quit_button = QPushButton("完全結束程式")
        self.quit_button.setObjectName("QuitButton")
        self.quit_button.setToolTip("關閉課務台並停止時間表提醒")
        self.quit_button.clicked.connect(self._quit_application)
        side_layout.addWidget(self.quit_button)
        sidebar.setStyleSheet("background: #2f3e46;")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 16)
        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.hint_label = QLabel()
        self.hint_label.setObjectName("HintLabel")
        self.hint_label.setWordWrap(True)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.title_label)
        content_layout.addWidget(self.hint_label)
        content_layout.addWidget(self.stack, 1)

        layout.addWidget(sidebar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

        for spec in self.modules:
            item = QListWidgetItem(spec.title)
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            self.module_list.addItem(item)
            widget = spec.factory(self.database)
            widget.setProperty("module_id", spec.id)
            self.stack.addWidget(widget)

        self.module_list.currentRowChanged.connect(self._on_module_changed)
        if self.modules:
            self.module_list.setCurrentRow(0)

        self.statusBar().showMessage(
            f"課務台 v{__version__}　資料預設儲存在本機；選擇 NVIDIA 或 OpenRouter 辨識時檔案會上傳。"
        )

    def _setup_reminders(self) -> None:
        self._quitting = False
        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            QApplication.instance().setQuitOnLastWindowClosed(False)
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.setWindowIcon(icon)
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.setToolTip("課務台")
            menu = QMenu(self)
            menu.addAction("開啟課務台", self._show_window)
            menu.addAction("結束課務台", self._quit_application)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self._check_reminders)
        self.reminder_timer.start(30_000)
        QTimer.singleShot(0, self._check_reminders)

    def _check_reminders(self) -> None:
        from datetime import datetime

        now = datetime.now()
        for entry in self.database.list_timetable_entries():
            try:
                occurrence = due_occurrence(entry, now)
            except ValueError:
                continue
            if not occurrence or entry.id is None:
                continue
            if not self.database.mark_reminder_delivered(entry.id, occurrence):
                continue
            location = f"　{entry.location}" if entry.location else ""
            message = f"{entry.start_time}　{entry.title}{location}"
            if self.tray is not None:
                self.tray.showMessage("課務台時間表提醒", message, QSystemTrayIcon.MessageIcon.Information, 10_000)
            else:
                QMessageBox.information(self, "課務台時間表提醒", message)

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _quit_application(self) -> None:
        self._quitting = True
        self.reminder_timer.stop()
        if self.tray is not None:
            self.tray.hide()
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.tray is not None and not self._quitting:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "課務台仍在背景執行", "時間表提醒會繼續顯示；在系統通知區可重新開啟或結束。",
                QSystemTrayIcon.MessageIcon.Information, 5_000,
            )
            return
        super().closeEvent(event)

    def _on_module_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.modules):
            return
        spec = self.modules[row]
        self.title_label.setText(spec.title)
        self.hint_label.setText(spec.description)
        self.stack.setCurrentIndex(row)
        current = self.stack.widget(row)
        refresh = getattr(current, "refresh", None)
        if callable(refresh):
            refresh()
