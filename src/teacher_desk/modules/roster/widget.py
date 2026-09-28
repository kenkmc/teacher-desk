from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database
from teacher_desk.services.roster_import import import_students


class RosterWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("組別"))
        self.class_list = QListWidget()
        self.class_list.currentRowChanged.connect(self._load_selected_class)
        left.addWidget(self.class_list, 1)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(6)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(7)
        form.addRow("組別名稱", self.name_edit)
        form.addRow("列數", self.rows_spin)
        form.addRow("行數", self.cols_spin)
        left.addLayout(form)
        buttons = QHBoxLayout()
        add_btn = QPushButton("新增組別")
        save_btn = QPushButton("儲存組別")
        del_btn = QPushButton("刪除組別")
        add_btn.clicked.connect(self._add_class)
        save_btn.clicked.connect(self._save_class)
        del_btn.clicked.connect(self._delete_class)
        buttons.addWidget(add_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(del_btn)
        left.addLayout(buttons)

        right = QVBoxLayout()
        right.addWidget(QLabel("學生（欄位：班別、學號、中文姓名、英文姓名）"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["班別", "學號", "中文姓名", "英文姓名"])
        self.table.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self.table, 1)
        student_form = QHBoxLayout()
        self.class_name_edit = QLineEdit()
        self.class_name_edit.setPlaceholderText("班別")
        self.no_edit = QLineEdit()
        self.no_edit.setPlaceholderText("學號")
        self.student_name_edit = QLineEdit()
        self.student_name_edit.setPlaceholderText("中文姓名")
        self.english_name_edit = QLineEdit()
        self.english_name_edit.setPlaceholderText("英文姓名")
        add_student = QPushButton("加入學生")
        add_student.clicked.connect(self._add_student)
        student_form.addWidget(self.class_name_edit)
        student_form.addWidget(self.no_edit)
        student_form.addWidget(self.student_name_edit)
        student_form.addWidget(self.english_name_edit)
        student_form.addWidget(add_student)
        right.addLayout(student_form)
        extra = QHBoxLayout()
        import_btn = QPushButton("匯入 Excel／CSV")
        delete_student_btn = QPushButton("刪除所選學生")
        import_btn.clicked.connect(self._import_file)
        delete_student_btn.clicked.connect(self._delete_student)
        extra.addWidget(import_btn)
        extra.addWidget(delete_student_btn)
        extra.addStretch()
        right.addLayout(extra)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

    def refresh(self) -> None:
        current_id = self._current_class_id()
        self.class_list.blockSignals(True)
        self.class_list.clear()
        for school_class in self.database.list_classes():
            self.class_list.addItem(f"{school_class.name}  ({school_class.rows}×{school_class.cols})")
            self.class_list.item(self.class_list.count() - 1).setData(256, school_class.id)
        self.class_list.blockSignals(False)
        if self.class_list.count() == 0:
            self.table.setRowCount(0)
            return
        target = 0
        for row in range(self.class_list.count()):
            if self.class_list.item(row).data(256) == current_id:
                target = row
                break
        self.class_list.setCurrentRow(target)

    def _current_class_id(self) -> int | None:
        item = self.class_list.currentItem()
        if item is None:
            return None
        value = item.data(256)
        return int(value) if value is not None else None

    def _load_selected_class(self) -> None:
        class_id = self._current_class_id()
        if class_id is None:
            self.table.setRowCount(0)
            return
        school_class = next((item for item in self.database.list_classes() if item.id == class_id), None)
        if school_class:
            self.name_edit.setText(school_class.name)
            self.rows_spin.setValue(school_class.rows)
            self.cols_spin.setValue(school_class.cols)
        students = self.database.list_students(class_id)
        self.table.setRowCount(len(students))
        for row, student in enumerate(students):
            self.table.setItem(row, 0, QTableWidgetItem(student.class_name))
            self.table.setItem(row, 1, QTableWidgetItem(student.student_no))
            self.table.setItem(row, 2, QTableWidgetItem(student.name))
            self.table.setItem(row, 3, QTableWidgetItem(student.english_name))
            self.table.item(row, 1).setData(256, student.id)

    def _add_class(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "組別", "請輸入組別名稱。")
            return
        try:
            self.database.add_class(name, self.rows_spin.value(), self.cols_spin.value())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "組別", str(exc))
            return
        self.refresh()

    def _save_class(self) -> None:
        class_id = self._current_class_id()
        if class_id is None:
            return
        self.database.update_class(class_id, self.name_edit.text(), self.rows_spin.value(), self.cols_spin.value())
        self.refresh()

    def _delete_class(self) -> None:
        class_id = self._current_class_id()
        if class_id is None:
            return
        if QMessageBox.question(self, "刪除組別", "會一併刪除該組學生與座位表，確定？") != QMessageBox.StandardButton.Yes:
            return
        self.database.delete_class(class_id)
        self.refresh()

    def _add_student(self) -> None:
        class_id = self._current_class_id()
        if class_id is None:
            QMessageBox.information(self, "學生", "請先新增或選擇組別。")
            return
        name = self.student_name_edit.text().strip()
        english = self.english_name_edit.text().strip()
        class_name = self.class_name_edit.text().strip()
        if not name and not english:
            QMessageBox.warning(self, "學生", "請輸入中文姓名或英文姓名。")
            return
        display = name or english
        try:
            self.database.add_student(
                class_id,
                self.no_edit.text() or display,
                name,
                english,
                class_name,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "學生", str(exc))
            return
        self.class_name_edit.clear()
        self.no_edit.clear()
        self.student_name_edit.clear()
        self.english_name_edit.clear()
        self._load_selected_class()

    def _delete_student(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 1) or self.table.item(row, 0)
        if item is None:
            return
        student_id = item.data(256)
        if student_id is None:
            return
        self.database.delete_student(int(student_id))
        self._load_selected_class()

    def _import_file(self) -> None:
        class_id = self._current_class_id()
        if class_id is None:
            QMessageBox.information(self, "匯入", "請先選擇組別。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "匯入名冊", "", "試算表 (*.xlsx *.xlsm *.csv)")
        if not path:
            return
        try:
            students = import_students(Path(path))
            imported_numbers = {student_no.strip() for student_no, *_ in students}
            removed_count = sum(
                student.student_no not in imported_numbers for student in self.database.list_students(class_id)
            )
            if removed_count and QMessageBox.question(
                self,
                "匯入名冊",
                f"名冊未包含現有 {removed_count} 位學生。繼續會移除他們及其座位安排，確定？",
            ) != QMessageBox.StandardButton.Yes:
                return
            self.database.replace_students(class_id, students)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "匯入失敗", str(exc))
            return
        self._load_selected_class()
        QMessageBox.information(self, "匯入", f"已匯入 {len(students)} 位學生。")
