from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database
from teacher_desk.modules.file_conversion.drop_list import FileDropList
from teacher_desk.services.word_convert import ConversionEngine, collect_word_files, convert_file, detect_engine


class ConvertWorker(QObject):
    progress = Signal(bool, str)
    finished = Signal(int, int, bool)

    def __init__(self, files: list[Path], output_dir: Path, engine: ConversionEngine) -> None:
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.engine = engine
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        ok = fail = 0
        for source in self.files:
            if self._cancelled.is_set():
                break
            result = convert_file(source, self.output_dir, self.engine)
            if result.ok:
                ok += 1
                self.progress.emit(True, f"完成：{source.name} → {result.output.name}")
            else:
                fail += 1
                self.progress.emit(False, f"失敗：{source.name} — {result.message}")
        self.finished.emit(ok, fail, self._cancelled.is_set())


class WordToPdfWidget(QWidget):
    """Word tab in the unified file conversion screen."""

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.files: list[Path] = []
        self.output_dir: Path | None = None
        self.thread: QThread | None = None
        self.worker: ConvertWorker | None = None
        self.completed = 0
        self._build()
        self.refresh()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_on_quit)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel("批次把 .doc／.docx 轉成 PDF。可加入檔案、資料夾，或拖放到清單。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.engine_label = QLabel()
        self.engine_label.setWordWrap(True)
        layout.addWidget(self.engine_label)

        self.file_count = QLabel("1. 加入 Word 檔案（0 個）")
        layout.addWidget(self.file_count)
        self.file_list = FileDropList()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.pathsDropped.connect(self.add_paths)
        layout.addWidget(self.file_list, 1)
        file_buttons = QHBoxLayout()
        self.add_button = QPushButton("加入檔案")
        self.folder_button = QPushButton("加入資料夾")
        self.remove_button = QPushButton("移除所選")
        self.clear_button = QPushButton("清空清單")
        self.add_button.clicked.connect(self._add_files)
        self.folder_button.clicked.connect(self._add_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear)
        for button in (self.add_button, self.folder_button, self.remove_button, self.clear_button):
            file_buttons.addWidget(button)
        layout.addLayout(file_buttons)
        self.recursive = QCheckBox("加入資料夾時包含子資料夾")
        self.recursive.setChecked(True)
        layout.addWidget(self.recursive)

        layout.addWidget(QLabel("2. 輸出資料夾（預設為原檔旁的 Converted）"))
        destination = QHBoxLayout()
        self.output_line = QLineEdit()
        self.output_line.setReadOnly(True)
        self.output_button = QPushButton("選擇資料夾")
        self.open_button = QPushButton("開啟資料夾")
        self.output_button.clicked.connect(self._choose_output)
        self.open_button.clicked.connect(self._open_output)
        destination.addWidget(self.output_line, 1)
        destination.addWidget(self.output_button)
        destination.addWidget(self.open_button)
        layout.addLayout(destination)

        actions = QHBoxLayout()
        self.start_button = QPushButton("開始轉換")
        self.cancel_button = QPushButton("取消轉換")
        self.cancel_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        self.cancel_button.clicked.connect(self._cancel)
        actions.addWidget(self.start_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status = QLabel("選擇檔案後按「開始轉換」。已存在的同名 PDF 會保留。")
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("轉換結果"))
        self.log = QListWidget()
        layout.addWidget(self.log, 1)

    def refresh(self) -> None:
        engine = detect_engine()
        if engine is None:
            self.engine_label.setText("需要在電腦安裝 LibreOffice 或 Microsoft Word，才能轉換 Word 檔。")
        else:
            self.engine_label.setText(f"目前使用：{engine.name}")

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "選擇 Word 檔案", "", "Word (*.doc *.docx)")
        self.add_paths(Path(path) for path in paths)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇含有 Word 檔案的資料夾")
        if folder:
            self.add_paths([Path(folder)])

    def add_paths(self, paths) -> None:
        if self.thread is not None:
            return
        candidates = collect_word_files(list(paths), self.recursive.isChecked())
        known = {str(path.resolve()).casefold() for path in self.files}
        for path in candidates:
            key = str(path.resolve()).casefold()
            if key in known:
                continue
            self.files.append(path)
            self.file_list.addItem(str(path))
            known.add(key)
        if self.files and self.output_dir is None:
            self.output_dir = self.files[0].parent / "Converted"
            self.output_line.setText(str(self.output_dir))
        self._update_count()

    def _update_count(self) -> None:
        self.file_count.setText(f"1. 加入 Word 檔案（{len(self.files)} 個）")

    def _remove_selected(self) -> None:
        for row in sorted((self.file_list.row(item) for item in self.file_list.selectedItems()), reverse=True):
            self.file_list.takeItem(row)
            del self.files[row]
        self._update_count()

    def _clear(self) -> None:
        self.files.clear()
        self.file_list.clear()
        self.log.clear()
        self.progress.setValue(0)
        self._update_count()

    def _choose_output(self) -> None:
        start = str(self.output_dir or (self.files[0].parent if self.files else Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾", start)
        if folder:
            self.output_dir = Path(folder)
            self.output_line.setText(folder)

    def _open_output(self) -> None:
        if self.output_dir is not None and self.output_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))
        else:
            QMessageBox.information(self, "檔案格式轉換", "輸出資料夾尚未建立。")

    def _set_busy(self, busy: bool) -> None:
        for control in (self.add_button, self.folder_button, self.remove_button, self.clear_button,
                        self.recursive, self.output_button, self.file_list):
            control.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def _start(self) -> None:
        if self.thread is not None:
            return
        if not self.files:
            QMessageBox.information(self, "Word 轉 PDF", "請先加入 Word 檔案。")
            return
        engine = detect_engine()
        if engine is None:
            QMessageBox.warning(self, "Word 轉 PDF", "請先安裝 LibreOffice 或 Microsoft Word。")
            return
        if self.output_dir is None:
            QMessageBox.information(self, "Word 轉 PDF", "請先選擇輸出資料夾。")
            return
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Word 轉 PDF", str(exc))
            return
        self.log.clear()
        self.completed = 0
        self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)
        self.status.setText(f"轉換中：0/{len(self.files)} 個")
        self.thread = QThread(self)
        self.worker = ConvertWorker(self.files.copy(), self.output_dir, engine)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._record)
        self.worker.finished.connect(self._done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self._set_busy(True)
        self.thread.start()

    def _record(self, success: bool, message: str) -> None:
        self.completed += 1
        self.progress.setValue(self.completed)
        self.log.addItem(message)
        self.log.scrollToBottom()
        self.status.setText(f"轉換中：{self.completed}/{len(self.files)} 個")

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消；目前的檔案完成後會停止。")

    def _done(self, ok: int, fail: int, cancelled: bool) -> None:
        state = "已取消" if cancelled else "完成"
        self.status.setText(f"{state}：成功 {ok} 個，失敗 {fail} 個。原檔及已有的 PDF 沒有修改。")

    def _thread_finished(self) -> None:
        self.thread = None
        self.worker = None
        self._set_busy(False)

    def _stop_on_quit(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
        if self.thread is not None:
            self.thread.wait()
