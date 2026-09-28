from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database, TimetableEntry
from teacher_desk.language import is_english
from teacher_desk.services.timetable_import import WEEKDAYS, extract_timetable_text, parse_timetable_text
from teacher_desk.services.timetable_vision import DEFAULT_MODEL, DEFAULT_OPENROUTER_MODEL


class ImportWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, path: Path, method: str, model: str, api_key: str) -> None:
        super().__init__()
        self.path = path
        self.method = method
        self.model = model
        self.api_key = api_key

    def run(self) -> None:
        try:
            self.finished.emit(extract_timetable_text(self.path, self.method, self.model, self.api_key))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TimetableWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.thread: QThread | None = None
        self.worker: ImportWorker | None = None
        self._dirty = False
        self._building_rows = False
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "匯入圖片、PDF、Excel 或 Word 後，程式會自動建立下方時間表及提醒草稿。"
            "核對內容後儲存；圖片與掃描 PDF 可選一般 OCR、本機 AI 或雲端 AI。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        top = QHBoxLayout()
        self.import_button = QPushButton("匯入時間表檔案")
        self.import_button.clicked.connect(self._import_file)
        self.ocr_method = QComboBox()
        self.ocr_method.addItem("一般 OCR（Tesseract）", "standard")
        self.ocr_method.addItem("本機 AI（Ollama）", "vision")
        self.ocr_method.addItem("NVIDIA Nemotron OCR v2（雲端）", "nvidia")
        self.ocr_method.addItem("雲端 AI（OpenRouter）", "openrouter")
        self.model_name = QLineEdit(DEFAULT_MODEL)
        self.model_name.setPlaceholderText("模型名稱")
        self.model_name.setToolTip("只用於圖片及 PDF；OpenRouter 只接受免費模型。")
        self.model_name.setMaximumWidth(240)
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("貼上 NVIDIA API key（只保留於記憶體）")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setMaximumWidth(360)
        self.cloud_notice = QLabel("雲端辨識會將所選圖片或 PDF 頁面上傳至 NVIDIA。")
        self.cloud_notice.setWordWrap(True)
        self.ocr_method.currentIndexChanged.connect(self._method_changed)
        parse_button = QPushButton("從下方文字重新辨識")
        parse_button.clicked.connect(self._parse_text)
        top.addWidget(self.import_button)
        top.addWidget(self.ocr_method)
        top.addWidget(self.model_name)
        top.addWidget(parse_button)
        top.addStretch()
        layout.addLayout(top)

        credentials = QHBoxLayout()
        credentials.addWidget(self.api_key)
        credentials.addWidget(self.cloud_notice, 1)
        layout.addLayout(credentials)
        self.ocr_method.setCurrentIndex(self.ocr_method.findData("nvidia"))
        self._method_changed()

        self.status = QLabel("關閉視窗後程式仍在通知區執行，並顯示每週提醒。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("擷取文字（可修改後重新辨識；無法辨識的項目可在表格手動新增）"))
        self.extracted_text = QTextEdit()
        self.extracted_text.setPlaceholderText("例如：星期一 08:30-09:15 1A 中文 201室")
        self.extracted_text.setMaximumHeight(125)
        layout.addWidget(self.extracted_text)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["星期", "開始", "結束", "課堂／事項", "地點", "提前分鐘", "啟用"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemChanged.connect(self._mark_dirty)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        add_button = QPushButton("新增一列")
        remove_button = QPushButton("移除所選")
        save_button = QPushButton("儲存時間表及提醒")
        add_button.clicked.connect(self._add_blank_row)
        remove_button.clicked.connect(self._remove_selected)
        save_button.clicked.connect(self._save)
        actions.addWidget(add_button)
        actions.addWidget(remove_button)
        actions.addStretch()
        actions.addWidget(save_button)
        layout.addLayout(actions)

    def refresh(self) -> None:
        if self._dirty:
            return
        self._fill_rows(self.database.list_timetable_entries())
        self.status.setText(f"已儲存 {self.table.rowCount()} 項每週時間表；關閉視窗後仍在通知區提醒。")

    def _mark_dirty(self, *_args: object) -> None:
        if not self._building_rows:
            self._dirty = True

    def _fill_rows(self, entries: list[TimetableEntry]) -> None:
        self._building_rows = True
        self.table.setRowCount(0)
        for entry in entries:
            self._add_row(entry)
        self._building_rows = False
        self._dirty = False

    def _add_row(self, entry: TimetableEntry) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        weekday = QComboBox()
        labels = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday") if is_english() else WEEKDAYS
        for index, label in enumerate(labels):
            weekday.addItem(label, index)
        weekday.setCurrentIndex(entry.weekday)
        weekday.currentIndexChanged.connect(self._mark_dirty)
        self.table.setCellWidget(row, 0, weekday)
        for column, value in (
            (1, entry.start_time),
            (2, entry.end_time),
            (3, entry.title),
            (4, entry.location),
            (5, str(entry.remind_before)),
        ):
            self.table.setItem(row, column, QTableWidgetItem(value))
        enabled = QTableWidgetItem()
        enabled.setFlags(enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled.setCheckState(Qt.CheckState.Checked if entry.enabled else Qt.CheckState.Unchecked)
        self.table.setItem(row, 6, enabled)

    def _add_blank_row(self) -> None:
        self._add_row(TimetableEntry(None, 0, "08:00", "08:45", ""))
        self._dirty = True

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self._dirty = True

    def _method_changed(self, *_args: object) -> None:
        method = self.ocr_method.currentData()
        cloud_provider = method if method in {"openrouter", "nvidia"} else None
        if cloud_provider and cloud_provider != getattr(self, "_last_cloud_provider", None):
            self.api_key.clear()
        if cloud_provider:
            self._last_cloud_provider = cloud_provider
        if method == "openrouter":
            self.model_name.setText(DEFAULT_OPENROUTER_MODEL)
        elif method == "vision":
            self.model_name.setText(DEFAULT_MODEL)
        self.model_name.setVisible(method in {"vision", "openrouter"})
        show_cloud = cloud_provider is not None
        self.api_key.setVisible(show_cloud)
        self.cloud_notice.setVisible(show_cloud)
        if method == "nvidia":
            self.api_key.setPlaceholderText("貼上 NVIDIA API key（只保留於記憶體）")
            self.cloud_notice.setText("圖片或 PDF 頁面會上傳至 NVIDIA Nemotron OCR v2；辨識後請核對預覽表。")
        elif method == "openrouter":
            self.api_key.setPlaceholderText("貼上 OpenRouter API key（只保留於記憶體）")
            self.cloud_notice.setText("圖片或 PDF 頁面會上傳至 OpenRouter 及其模型供應商。")

    def _import_file(self) -> None:
        if self.thread is not None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "匯入時間表", "",
            "時間表 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf *.xlsx *.xlsm *.xls *.docx *.doc)",
        )
        if not path:
            return
        method = str(self.ocr_method.currentData())
        cloud_file = Path(path).suffix.lower() in {
            ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp",
        }
        if method in {"openrouter", "nvidia"} and cloud_file and not self.api_key.text().strip():
            provider = "NVIDIA" if method == "nvidia" else "OpenRouter"
            QMessageBox.warning(self, "時間表", f"請先輸入 {provider} API key")
            return
        self.status.setText(f"正在讀取：{path}（{self.ocr_method.currentText()}）")
        self.import_button.setEnabled(False)
        self.thread = QThread(self)
        self.worker = ImportWorker(Path(path), method, self.model_name.text().strip(), self.api_key.text().strip())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._imported)
        self.worker.failed.connect(self._import_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()

    def _imported(self, text: str) -> None:
        self.extracted_text.setPlainText(text)
        if self._parse_text():
            self.table.scrollToTop()
            self.table.setFocus()

    def _import_failed(self, message: str) -> None:
        self.status.setText("匯入失敗")
        QMessageBox.warning(self, "時間表", message)

    def _cleanup_thread(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self.import_button.setEnabled(True)

    def _parse_text(self) -> bool:
        suggestions = parse_timetable_text(self.extracted_text.toPlainText())
        if not suggestions:
            self.status.setText("未能自動建立時間表；請核對擷取文字後重新辨識，或手動新增。現有表格未改動。")
            return False
        entries = [
            TimetableEntry(None, item.weekday, item.start_time, item.end_time, item.title,
                           item.location, enabled=item.enabled)
            for item in suggestions
        ]
        self._fill_rows(entries)
        self._dirty = True
        uncertain = sum(not entry.enabled for entry in entries)
        note = f"其中 {uncertain} 項文字重疊、暫停提醒；" if uncertain else ""
        self.status.setText(f"已自動建立 {len(entries)} 項時間表及提醒（預設提前 10 分鐘）；{note}請核對後儲存。")
        return True

    def _value(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    def _read_entries(self) -> list[TimetableEntry]:
        entries = []
        for row in range(self.table.rowCount()):
            weekday_widget = self.table.cellWidget(row, 0)
            weekday = int(weekday_widget.currentData()) if isinstance(weekday_widget, QComboBox) else 0
            start = self._value(row, 1)
            end = self._value(row, 2)
            title = self._value(row, 3)
            location = self._value(row, 4)
            try:
                start_time = datetime.strptime(start, "%H:%M").time()
                end_time = datetime.strptime(end, "%H:%M").time()
                minutes = int(self._value(row, 5))
            except ValueError as exc:
                raise ValueError(f"第 {row + 1} 列的時間或提醒分鐘格式有誤") from exc
            if start_time >= end_time:
                raise ValueError(f"第 {row + 1} 列結束時間必須晚於開始時間")
            if not title:
                raise ValueError(f"第 {row + 1} 列欠缺課堂／事項")
            if not 0 <= minutes <= 1440:
                raise ValueError(f"第 {row + 1} 列提醒分鐘須介乎 0 至 1440")
            enabled_item = self.table.item(row, 6)
            enabled = bool(enabled_item and enabled_item.checkState() == Qt.CheckState.Checked)
            entries.append(
                TimetableEntry(None, weekday, start_time.strftime("%H:%M"), end_time.strftime("%H:%M"),
                               title, location, minutes, enabled)
            )
        return entries

    def _save(self) -> None:
        try:
            entries = self._read_entries()
        except ValueError as exc:
            QMessageBox.warning(self, "時間表", str(exc))
            return
        if self.database.list_timetable_entries() and QMessageBox.question(
            self, "取代時間表", "儲存後會取代目前的每週時間表，確定？"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.replace_timetable_entries(entries)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "時間表", str(exc))
            return
        self._dirty = False
        self.refresh()
        QMessageBox.information(self, "時間表", f"已儲存 {len(entries)} 項每週時間表。")
