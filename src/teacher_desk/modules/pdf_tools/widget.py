from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database
from teacher_desk.services.pdf_tools import (
    PageNumberStyle,
    add_page_numbers,
    expand_pdf_pages,
    reorder_and_merge,
    split_pages,
)


class PdfToolsWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("加入 PDF 後會展開成每一頁。可拖曳或用上移／下移調整頁序，再合併並可加頁碼。"))
        self.page_list = QListWidget()
        self.page_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.page_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.page_list, 1)
        row = QHBoxLayout()
        add_btn = QPushButton("加入 PDF")
        up_btn = QPushButton("上移")
        down_btn = QPushButton("下移")
        remove_btn = QPushButton("移除所選頁")
        add_btn.clicked.connect(self._add)
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn.clicked.connect(lambda: self._move(1))
        remove_btn.clicked.connect(self._remove)
        row.addWidget(add_btn)
        row.addWidget(up_btn)
        row.addWidget(down_btn)
        row.addWidget(remove_btn)
        layout.addLayout(row)

        edit_row = QHBoxLayout()
        rotate_left = QPushButton("所選頁左轉 90°")
        rotate_right = QPushButton("所選頁右轉 90°")
        extract_btn = QPushButton("擷取所選頁")
        split_btn = QPushButton("所選頁分拆成檔案")
        rotate_left.clicked.connect(lambda: self._rotate_selected(-90))
        rotate_right.clicked.connect(lambda: self._rotate_selected(90))
        extract_btn.clicked.connect(self._extract_selected)
        split_btn.clicked.connect(self._split_selected)
        for button in (rotate_left, rotate_right, extract_btn, split_btn):
            edit_row.addWidget(button)
        layout.addLayout(edit_row)

        self.page_numbers = QCheckBox("合併後加入頁碼")
        self.page_numbers.setChecked(True)
        self.skip_first = QCheckBox("第一頁不加頁碼")
        self.format_box = QComboBox()
        self.format_box.addItem("1 / N", "{page} / {total}")
        self.format_box.addItem("第 1 頁", "第 {page} 頁")
        self.format_box.addItem("1", "{page}")
        layout.addWidget(self.page_numbers)
        layout.addWidget(self.skip_first)
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("頁碼格式"))
        format_row.addWidget(self.format_box, 1)
        layout.addLayout(format_row)

        export_btn = QPushButton("依目前頁序合併並儲存")
        export_btn.clicked.connect(self._export)
        layout.addWidget(export_btn)

    def refresh(self) -> None:
        return

    def _add(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "選擇 PDF", "", "PDF (*.pdf)")
        for file in files:
            path = Path(file)
            try:
                pages = expand_pdf_pages(path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "PDF", str(exc))
                continue
            for source, index in pages:
                item = QListWidgetItem(f"{source.name}　第 {index + 1} 頁")
                item.setToolTip(str(source))
                item.setData(256, str(source))
                item.setData(257, index)
                item.setData(258, 0)
                self.page_list.addItem(item)

    def _rotate_selected(self, delta: int) -> None:
        for item in self.page_list.selectedItems():
            angle = (int(item.data(258) or 0) + delta) % 360
            item.setData(258, angle)
            item.setText(f"{Path(str(item.data(256))).name}　第 {int(item.data(257)) + 1} 頁"
                         + (f"　旋轉 {angle}°" if angle else ""))

    def _move(self, delta: int) -> None:
        rows = sorted({index.row() for index in self.page_list.selectedIndexes()})
        if not rows:
            row = self.page_list.currentRow()
            rows = [row] if row >= 0 else []
        if not rows:
            return
        if delta < 0:
            if rows[0] + delta < 0:
                return
            for row in rows:
                item = self.page_list.takeItem(row)
                self.page_list.insertItem(row + delta, item)
                item.setSelected(True)
                self.page_list.setCurrentRow(row + delta)
        else:
            if rows[-1] + delta >= self.page_list.count():
                return
            for row in reversed(rows):
                item = self.page_list.takeItem(row)
                self.page_list.insertItem(row + delta, item)
                item.setSelected(True)
                self.page_list.setCurrentRow(row + delta)

    def _remove(self) -> None:
        for item in self.page_list.selectedItems():
            self.page_list.takeItem(self.page_list.row(item))

    def _page_refs(self) -> list[tuple[Path, int]]:
        refs: list[tuple[Path, int]] = []
        for index in range(self.page_list.count()):
            item = self.page_list.item(index)
            refs.append((Path(str(item.data(256))), int(item.data(257))))
        return refs

    def _rotations(self) -> list[int]:
        return [int(self.page_list.item(index).data(258) or 0) for index in range(self.page_list.count())]

    def _selected_pages(self) -> tuple[list[tuple[Path, int]], list[int]]:
        rows = sorted(self.page_list.row(item) for item in self.page_list.selectedItems())
        refs = self._page_refs()
        rotations = self._rotations()
        return [refs[row] for row in rows], [rotations[row] for row in rows]

    def _extract_selected(self) -> None:
        refs, rotations = self._selected_pages()
        if not refs:
            QMessageBox.information(self, "PDF", "請先選擇要擷取的頁面。")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "擷取所選頁", "selected-pages.pdf", "PDF (*.pdf)")
        if not dest:
            return
        try:
            reorder_and_merge(refs, Path(dest), rotations)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF", str(exc))
            return
        QMessageBox.information(self, "PDF", f"已儲存：{dest}")

    def _split_selected(self) -> None:
        refs, rotations = self._selected_pages()
        if not refs:
            QMessageBox.information(self, "PDF", "請先選擇要分拆的頁面。")
            return
        directory = QFileDialog.getExistingDirectory(self, "選擇分拆輸出資料夾")
        if not directory:
            return
        try:
            outputs = split_pages(refs, Path(directory), rotations)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF", str(exc))
            return
        QMessageBox.information(self, "PDF", f"已儲存 {len(outputs)} 個 PDF。")

    def _export(self) -> None:
        refs = self._page_refs()
        if not refs:
            QMessageBox.information(self, "PDF", "請先加入檔案。")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "儲存合併 PDF", "merged.pdf", "PDF (*.pdf)")
        if not dest:
            return
        output = Path(dest)
        if any(path.resolve() == output.resolve() for path, _ in refs):
            QMessageBox.warning(self, "PDF", "輸出檔不可覆蓋來源 PDF。")
            return
        try:
            if self.page_numbers.isChecked():
                with tempfile.TemporaryDirectory() as directory:
                    temp = Path(directory) / "pages.pdf"
                    reorder_and_merge(refs, temp, self._rotations())
                    style = PageNumberStyle(
                        format=str(self.format_box.currentData()),
                        skip_first=self.skip_first.isChecked(),
                    )
                    add_page_numbers(temp, output, style)
            else:
                reorder_and_merge(refs, output, self._rotations())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF", str(exc))
            return
        QMessageBox.information(self, "PDF", f"已儲存：{output}")
