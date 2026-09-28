from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database
from teacher_desk.modules.file_conversion.drop_list import FileDropList
from teacher_desk.services.file_conversion import (
    IMAGE_INPUTS,
    VIDEO_INPUTS,
    convert_image,
    find_ffmpeg,
    finish_output,
    next_output_path,
    temporary_output_path,
    video_command,
)


class ConversionPanel(QWidget):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.output_dir: Path | None = None
        self.files: list[Path] = []
        self.active = False
        self.cancelled = False
        self.index = 0
        self.ok_count = 0
        self.fail_count = 0
        self.process: QProcess | None = None
        self.current_source: Path | None = None
        self.current_output: Path | None = None
        self.current_temporary: Path | None = None
        self.stderr = ""
        self.stdout_buffer = ""
        self._build()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_on_quit)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        if self.mode == "image":
            hint = "把 HEIC／HEIF／WebP 轉成 JPG 或 PNG。透明圖片轉 JPG 時會使用白色背景；動態圖片只輸出首張影格。"
            file_filter = "圖片 (*.heic *.heif *.webp)"
        else:
            hint = "把 HEVC／H.265 原始影片或 MOV 轉成相容性較高的 H.264／AAC MP4。大影片需較長時間。"
            file_filter = "影片 (*.hevc *.h265 *.mov)"
        self.file_filter = file_filter
        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        self.file_count = QLabel("1. 加入檔案（0 個）")
        layout.addWidget(self.file_count)
        self.file_list = FileDropList()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.pathsDropped.connect(self.add_paths)
        layout.addWidget(self.file_list, 1)
        file_buttons = QHBoxLayout()
        self.add_button = QPushButton("加入檔案")
        self.folder_button = QPushButton("加入資料夾內檔案")
        self.remove_button = QPushButton("移除所選")
        self.clear_button = QPushButton("清空清單")
        self.add_button.clicked.connect(self._add_files)
        self.folder_button.clicked.connect(self._add_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear)
        for button in (self.add_button, self.folder_button, self.remove_button, self.clear_button):
            file_buttons.addWidget(button)
        layout.addLayout(file_buttons)

        options = QHBoxLayout()
        if self.mode == "image":
            options.addWidget(QLabel("輸出格式"))
            self.format_box = QComboBox()
            self.format_box.addItem("JPG", ".jpg")
            self.format_box.addItem("PNG", ".png")
            options.addWidget(self.format_box)
        else:
            options.addWidget(QLabel("原始 HEVC 影格率"))
            self.raw_fps = QSpinBox()
            self.raw_fps.setRange(1, 120)
            self.raw_fps.setValue(30)
            self.raw_fps.setSuffix(" FPS")
            self.raw_fps.setToolTip("只用於 .hevc／.h265 原始檔；MOV 會使用檔案內的影格率。")
            options.addWidget(self.raw_fps)
        options.addStretch()
        layout.addLayout(options)

        layout.addWidget(QLabel("2. 輸出資料夾（預設為原檔旁的 Converted）"))
        destination = QHBoxLayout()
        self.output_line = QLineEdit()
        self.output_line.setReadOnly(True)
        destination.addWidget(self.output_line, 1)
        self.output_button = QPushButton("選擇資料夾")
        self.output_button.clicked.connect(self._choose_output)
        destination.addWidget(self.output_button)
        self.open_button = QPushButton("開啟資料夾")
        self.open_button.clicked.connect(self._open_output)
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
        layout.addWidget(QLabel("3. 開始轉換"))
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status = QLabel("選擇檔案後按「開始轉換」。原檔不會被修改。")
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("轉換結果"))
        self.log = QListWidget()
        layout.addWidget(self.log, 1)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "選擇檔案", "", self.file_filter)
        self.add_paths(Path(path) for path in paths)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇含有檔案的資料夾")
        if folder:
            self.add_paths(path for path in sorted(Path(folder).iterdir()) if path.is_file())

    def add_paths(self, paths) -> None:
        allowed = IMAGE_INPUTS if self.mode == "image" else VIDEO_INPUTS
        known = {str(path.resolve()).casefold() for path in self.files}
        expanded = []
        for path in paths:
            expanded.extend(sorted(path.iterdir()) if path.is_dir() else [path])
        for path in expanded:
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
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
        self.file_count.setText(f"1. 加入檔案（{len(self.files)} 個）")

    def _remove_selected(self) -> None:
        rows = sorted((self.file_list.row(item) for item in self.file_list.selectedItems()), reverse=True)
        for row in rows:
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
        directory = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾", start)
        if directory:
            self.output_dir = Path(directory)
            self.output_line.setText(directory)

    def _open_output(self) -> None:
        if self.output_dir is not None and self.output_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))
        else:
            QMessageBox.information(self, "檔案格式轉換", "輸出資料夾尚未建立。")

    def _set_busy(self, busy: bool) -> None:
        for control in (self.add_button, self.folder_button, self.remove_button, self.clear_button,
                        self.output_button, self.file_list):
            control.setEnabled(not busy)
        if self.mode == "image":
            self.format_box.setEnabled(not busy)
        else:
            self.raw_fps.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def _start(self) -> None:
        if not self.files:
            QMessageBox.information(self, "檔案格式轉換", "請先加入檔案。")
            return
        if self.output_dir is None:
            QMessageBox.information(self, "檔案格式轉換", "請先選擇輸出資料夾。")
            return
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "檔案格式轉換", str(exc))
            return
        if self.mode == "video" and find_ffmpeg() is None:
            QMessageBox.warning(self, "檔案格式轉換", "找不到 FFmpeg 影片轉換程式。")
            return
        self.active = True
        self.cancelled = False
        self.index = self.ok_count = self.fail_count = 0
        self.log.clear()
        self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)
        self._set_busy(True)
        QTimer.singleShot(0, self._next)

    def _next(self) -> None:
        if not self.active:
            return
        if self.cancelled or self.index >= len(self.files):
            self._finish()
            return
        source = self.files[self.index]
        self.status.setText(f"轉換中：{source.name}（{self.index + 1}/{len(self.files)}）")
        try:
            suffix = str(self.format_box.currentData()) if self.mode == "image" else ".mp4"
            destination = next_output_path(source, self.output_dir, suffix)
            if self.mode == "image":
                warning = convert_image(source, destination)
                detail = f"（{warning}）" if warning else ""
                self._record(True, f"完成：{source.name} → {destination.name}{detail}")
                return
            self._start_video(source, destination)
        except Exception as exc:  # noqa: BLE001 — show each failed file and keep the batch going
            self._record(False, f"失敗：{source.name} — {exc}")

    def _start_video(self, source: Path, destination: Path) -> None:
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            raise RuntimeError("找不到 FFmpeg。")
        temporary = temporary_output_path(destination)
        command = video_command(source, temporary, ffmpeg, self.raw_fps.value())
        self.current_source = source
        self.current_output = destination
        self.current_temporary = temporary
        self.stderr = ""
        self.stdout_buffer = ""
        self.process = QProcess(self)
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.process.readyReadStandardOutput.connect(self._read_video_progress)
        self.process.readyReadStandardError.connect(self._read_video_errors)
        self.process.finished.connect(self._video_finished)
        self.process.errorOccurred.connect(self._video_error)
        self.process.start()

    def _read_video_progress(self) -> None:
        if self.process is None:
            return
        self.stdout_buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split("\n", 1)
            if line.startswith("out_time=") and self.current_source is not None:
                self.status.setText(f"轉換中：{self.current_source.name}　已處理 {line.split('=', 1)[1].strip()}")

    def _read_video_errors(self) -> None:
        if self.process is not None:
            self.stderr = (self.stderr + bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace"))[-4000:]

    def _video_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.process is not None:
            message = self.process.errorString()
            self._complete_video(False, f"無法啟動 FFmpeg：{message}")

    def _video_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self.process is None:
            return
        self._read_video_errors()
        if self.cancelled:
            self._complete_video(False, "已取消")
            return
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            try:
                finish_output(self.current_temporary, self.current_output)
            except Exception as exc:  # noqa: BLE001
                self._complete_video(False, str(exc))
            else:
                self._complete_video(True, "")
        else:
            self._complete_video(False, self.stderr.strip().splitlines()[-1] if self.stderr.strip() else "FFmpeg 轉換失敗。")

    def _complete_video(self, success: bool, message: str) -> None:
        if self.process is None:
            return
        process = self.process
        source = self.current_source
        destination = self.current_output
        temporary = self.current_temporary
        self.process = None
        self.current_source = self.current_output = self.current_temporary = None
        process.deleteLater()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if self.cancelled:
            self._finish()
        elif success:
            self._record(True, f"完成：{source.name} → {destination.name}")
        else:
            self._record(False, f"失敗：{source.name} — {message}")

    def _record(self, success: bool, message: str) -> None:
        if success:
            self.ok_count += 1
        else:
            self.fail_count += 1
        self.log.addItem(message)
        self.log.scrollToBottom()
        self.index += 1
        self.progress.setValue(self.index)
        QTimer.singleShot(0, self._next)

    def _cancel(self) -> None:
        self.cancelled = True
        self.cancel_button.setEnabled(False)
        self.status.setText("正在取消…")
        if self.process is not None:
            self.process.kill()
        else:
            QTimer.singleShot(0, self._next)

    def _finish(self) -> None:
        self.active = False
        self._set_busy(False)
        state = "已取消" if self.cancelled else "完成"
        self.status.setText(f"{state}：成功 {self.ok_count} 個，失敗 {self.fail_count} 個。原檔沒有修改。")

    def _stop_on_quit(self) -> None:
        self.active = False
        self.cancelled = True
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(3000)
        if self.current_temporary is not None:
            self.current_temporary.unlink(missing_ok=True)


class FileConversionWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        layout = QVBoxLayout(self)
        title = QLabel("選擇轉換類型，加入檔案，確認輸出資料夾，再開始轉換。可拖放檔案到清單。")
        title.setWordWrap(True)
        layout.addWidget(title)
        tabs = QTabWidget()
        from teacher_desk.modules.word_to_pdf.widget import WordToPdfWidget

        self.word_panel = WordToPdfWidget(database)
        self.image_panel = ConversionPanel("image")
        self.video_panel = ConversionPanel("video")
        tabs.addTab(self.word_panel, "Word → PDF")
        tabs.addTab(self.image_panel, "圖片 → JPG／PNG")
        tabs.addTab(self.video_panel, "影片 → MP4")
        self.tabs = tabs
        layout.addWidget(tabs)

    def refresh(self) -> None:
        self.word_panel.refresh()
