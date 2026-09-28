from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database
from teacher_desk.services.qr_scan import open_image, scan_qr_image


class QrScanWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.results: list[str] = []

        layout = QVBoxLayout(self)
        hint = QLabel("選擇圖片後會在本機辨識所有 QR Code。內容只會顯示供核對，不會自動開啟連結。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        picker = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("PNG、JPG、HEIC、WebP、BMP 或 TIFF 圖片")
        self.choose_button = QPushButton("匯入圖片並掃描")
        self.choose_button.clicked.connect(self._choose_image)
        picker.addWidget(self.path_edit, 1)
        picker.addWidget(self.choose_button)
        layout.addLayout(picker)

        self.preview = QLabel("圖片預覽")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setMaximumHeight(280)
        self.preview.setStyleSheet("border: 1px solid #cad2c5; background: #f6f7f5;")
        layout.addWidget(self.preview)

        self.status = QLabel("尚未匯入圖片。")
        layout.addWidget(self.status)
        self.result_list = QListWidget()
        self.result_list.setMinimumHeight(90)
        self.result_list.currentRowChanged.connect(self._show_result)
        layout.addWidget(self.result_list, 1)

        layout.addWidget(QLabel("QR Code 內容"))
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(100)
        layout.addWidget(self.detail, 1)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("複製所選內容")
        self.copy_all_button = QPushButton("複製全部內容")
        self.copy_button.clicked.connect(self._copy_selected)
        self.copy_all_button.clicked.connect(self._copy_all)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.copy_all_button)
        actions.addStretch()
        layout.addLayout(actions)
        self._update_copy_buttons()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇含 QR Code 的圖片",
            "",
            "圖片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.heic *.heif)",
        )
        if path:
            self.scan_path(Path(path))

    def scan_path(self, path: Path) -> None:
        self.path_edit.setText(str(path))
        self.results.clear()
        self.result_list.clear()
        self.detail.clear()
        self.preview.clear()
        self._update_copy_buttons()
        self.status.setText("正在掃描圖片…")
        QApplication.processEvents()
        try:
            self._show_preview(path)
            self.results = scan_qr_image(path)
        except Exception as exc:  # noqa: BLE001 — surface invalid or unreadable images in the UI
            self.status.setText("掃描失敗。")
            QMessageBox.warning(self, "QR 二維碼掃描", f"無法讀取或掃描圖片：\n{exc}")
            return

        for index, value in enumerate(self.results, 1):
            excerpt = value.replace("\n", " ").strip()[:90]
            self.result_list.addItem(f"{index}. {excerpt or '（空白內容）'}")
        if self.results:
            self.result_list.setCurrentRow(0)
            self.status.setText(f"找到 {len(self.results)} 個 QR Code。點選項目查看完整內容。")
        else:
            self.status.setText("找不到可辨識的 QR Code。可嘗試較清晰、完整的圖片。")
        self._update_copy_buttons()

    def _show_preview(self, path: Path) -> None:
        image = open_image(path)
        try:
            image.thumbnail((640, 280), Image.Resampling.LANCZOS)
            data = BytesIO()
            image.save(data, format="PNG")
            pixmap = QPixmap()
            if not pixmap.loadFromData(data.getvalue(), "PNG"):
                raise ValueError("圖片預覽失敗。")
            self.preview.setPixmap(pixmap)
        finally:
            image.close()

    def _show_result(self, row: int) -> None:
        self.detail.setPlainText(self.results[row] if 0 <= row < len(self.results) else "")
        self._update_copy_buttons()

    def _update_copy_buttons(self) -> None:
        self.copy_button.setEnabled(0 <= self.result_list.currentRow() < len(self.results))
        self.copy_all_button.setEnabled(bool(self.results))

    def _copy_selected(self) -> None:
        row = self.result_list.currentRow()
        if 0 <= row < len(self.results):
            QApplication.clipboard().setText(self.results[row])
            self.status.setText("已複製所選 QR Code 內容。")

    def _copy_all(self) -> None:
        if self.results:
            QApplication.clipboard().setText("\n\n".join(self.results))
            self.status.setText(f"已複製全部 {len(self.results)} 個 QR Code 內容。")
