from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database
from teacher_desk.services.checkmate import (
    CHECKMATE_RELEASE_PAGE,
    CheckMateHit,
    download_and_install,
    iter_checkmate_exes,
    pick_best_hit,
    windows_fixed_drives,
)


class SearchWorker(QObject):
    progress = Signal(str)
    finished = Signal(list)

    def run(self) -> None:
        hits = iter_checkmate_exes(windows_fixed_drives(), progress=self.progress.emit)
        self.finished.emit(hits)


class InstallWorker(QObject):
    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, release_page: str) -> None:
        super().__init__()
        self.release_page = release_page

    def run(self) -> None:
        try:
            path = download_and_install(self.release_page, progress=self.progress.emit)
            self.finished.emit(str(path))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class McGraderPlaceholderWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self._pending_install = False
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("這裡用來尋找、安裝並啟動 CheckMate 選擇題批改軟件。"))
        layout.addWidget(
            QLabel("會掃描本機所有磁碟。若找不到，可從 GitHub 發行頁下載並安裝最新版本。")
        )
        self.release_edit = QLineEdit(CHECKMATE_RELEASE_PAGE)
        layout.addWidget(QLabel("發行頁網址"))
        layout.addWidget(self.release_edit)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        browse = QPushButton("瀏覽")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        buttons = QHBoxLayout()
        self.search_btn = QPushButton("全磁碟搜尋 CheckMate")
        self.install_btn = QPushButton("找不到則下載安裝")
        save = QPushButton("儲存路徑")
        launch = QPushButton("啟動批改軟件")
        self.search_btn.clicked.connect(self._search)
        self.install_btn.clicked.connect(self._install)
        save.clicked.connect(self._save)
        launch.clicked.connect(self._launch)
        buttons.addWidget(self.search_btn)
        buttons.addWidget(self.install_btn)
        buttons.addWidget(save)
        buttons.addWidget(launch)
        layout.addLayout(buttons)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

    def refresh(self) -> None:
        saved = self.database.get_setting("mc_grader_path")
        if saved:
            self.path_edit.setText(saved)
        release = self.database.get_setting("checkmate_release_url")
        if release:
            self.release_edit.setText(release)
        else:
            self.release_edit.setText(CHECKMATE_RELEASE_PAGE)

    def _append(self, text: str) -> None:
        self.log.append(text)

    def _busy(self, busy: bool) -> None:
        self.search_btn.setEnabled(not busy)
        self.install_btn.setEnabled(not busy)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "選擇批改軟件", "", "Python 或執行檔 (*.py *.exe)")
        if path:
            self.path_edit.setText(path)

    def _save(self) -> None:
        self.database.set_setting("mc_grader_path", self.path_edit.text().strip())
        self.database.set_setting("checkmate_release_url", self.release_edit.text().strip())
        QMessageBox.information(self, "選擇題批改", "已儲存路徑。")

    def _search(self) -> None:
        if self.thread is not None:
            return
        self._append("開始全磁碟搜尋 CheckMate.exe …")
        self._busy(True)
        thread = QThread(self)
        worker = SearchWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._append)
        worker.finished.connect(self._on_search_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._cleanup_thread)
        self.thread = thread
        self.worker = worker
        thread.start()

    def _on_search_done(self, hits: list[CheckMateHit]) -> None:
        if not hits:
            self._append("全磁碟找不到 CheckMate.exe。可按「找不到則下載安裝」。")
            reply = QMessageBox.question(
                self,
                "選擇題批改",
                "找不到 CheckMate。要從發行頁下載並安裝嗎？",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pending_install = True
            return
        self._append(f"共找到 {len(hits)} 個執行檔：")
        for hit in hits:
            version = hit.version or "未知版本"
            extra = "（建置／發行資料夾）" if hit.is_build_tree else ""
            self._append(f"  {hit.path}　{version}{extra}")
        best = pick_best_hit(hits)
        if best is None:
            return
        self.path_edit.setText(str(best.path))
        self.database.set_setting("mc_grader_path", str(best.path))
        self._append(f"已選用：{best.path}　{best.version or '未知版本'}")

    def _install(self) -> None:
        if self.thread is not None:
            return
        url = self.release_edit.text().strip() or CHECKMATE_RELEASE_PAGE
        self.database.set_setting("checkmate_release_url", url)
        self._append(f"準備從 {url} 下載並安裝 …")
        self._busy(True)
        thread = QThread(self)
        worker = InstallWorker(url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._append)
        worker.finished.connect(self._on_install_done)
        worker.failed.connect(self._on_install_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._cleanup_thread)
        self.thread = thread
        self.worker = worker
        thread.start()

    def _on_install_done(self, path: str) -> None:
        self.path_edit.setText(path)
        self.database.set_setting("mc_grader_path", path)
        self._append(f"安裝完成：{path}")
        QMessageBox.information(self, "選擇題批改", f"已安裝 CheckMate：\n{path}")

    def _on_install_failed(self, message: str) -> None:
        self._append(f"安裝失敗：{message}")
        QMessageBox.warning(self, "選擇題批改", message)

    def _cleanup_thread(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self._busy(False)
        if self._pending_install:
            self._pending_install = False
            self._install()

    def _launch(self) -> None:
        path = Path(self.path_edit.text().strip())
        if not path.is_file():
            QMessageBox.warning(self, "選擇題批改", "找不到檔案。請先全磁碟搜尋，或下載安裝 CheckMate。")
            return
        self.database.set_setting("mc_grader_path", str(path))
        try:
            if path.suffix.lower() == ".py":
                subprocess.Popen([sys.executable, str(path)], cwd=str(path.parent))
            else:
                subprocess.Popen([str(path)], cwd=str(path.parent))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "選擇題批改", str(exc))
