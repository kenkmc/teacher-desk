from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from teacher_desk.db import Database, Student
from teacher_desk.services.pdf_export import export_seating_pdf
from teacher_desk.services.seating import (
    PodiumItem,
    RoomLayout,
    SeatItem,
    default_room_layout,
    layout_to_json,
    parse_layout,
    randomize_layout,
    snap_to_neighbors,
)

STUDENT_MIME = "application/x-teacher-desk-student"


def _student_label(student: Student) -> str:
    chinese = student.name.strip()
    english = student.english_name.strip()
    class_name = student.class_name.strip()
    if chinese and english and chinese != english:
        names = f"{chinese}\n{english}"
    else:
        names = chinese or english or "空"
    if class_name:
        return f"{class_name}\n{names}"
    return names


class _MovableFrame(QFrame):
    moved = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: QPoint | None = None
        self._moving = False
        self.snapper = None

    def _begin_move(self, event: QMouseEvent) -> None:
        self._drag_offset = event.globalPosition().toPoint() - self.mapToGlobal(QPoint(0, 0))
        self._moving = False
        self.raise_()

    def _desired_pos(self, event: QMouseEvent) -> QPoint | None:
        if self._drag_offset is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return None
        parent = self.parentWidget()
        if parent is None:
            return None
        global_top_left = event.globalPosition().toPoint() - self._drag_offset
        top_left = parent.mapFromGlobal(global_top_left)
        return QPoint(max(0, top_left.x()), max(0, top_left.y()))

    def _place_at(self, x: int, y: int) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(max(0, x), max(0, y))
        needed_w = self.x() + self.width() + 24
        needed_h = self.y() + self.height() + 24
        if needed_w > parent.width() or needed_h > parent.height():
            parent.setMinimumSize(max(parent.width(), needed_w), max(parent.height(), needed_h))
            parent.resize(max(parent.width(), needed_w), max(parent.height(), needed_h))
        self.moved.emit()

    def _update_move(self, event: QMouseEvent) -> bool:
        pos = self._desired_pos(event)
        if pos is None:
            return False
        if not self._moving and (pos - QPoint(self.x(), self.y())).manhattanLength() < 4:
            return False
        self._moving = True
        x, y = pos.x(), pos.y()
        if self.snapper is not None:
            x, y = self.snapper(self, x, y, self.width(), self.height())
        self._place_at(x, y)
        return True


class PodiumFrame(_MovableFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet("QFrame { background: #1d3557; color: #f8f9fa; border: 2px solid #0d1b2a; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        label = QLabel("講台（可拖移）")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_move(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._update_move(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        self._moving = False
        super().mouseReleaseEvent(event)


class SeatCell(_MovableFrame):
    dropped = Signal(str, int)
    cleared = Signal(str)
    lock_toggled = Signal(str)
    empty_clicked = Signal(str)

    def __init__(self, seat_id: str) -> None:
        super().__init__()
        self.seat_id = seat_id
        self.student_id: int | None = None
        self.locked = False
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.Box)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.label = QLabel("空")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label)
        self._paint()

    def set_student(self, student: Student | None) -> None:
        self.student_id = student.id if student else None
        self.label.setText(_student_label(student) if student else "空")
        self._paint()

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self._paint()

    def _paint(self) -> None:
        if self.locked:
            self.setStyleSheet("QFrame { background: #e9d8a6; border: 2px solid #9b2226; }")
        elif self.student_id:
            self.setStyleSheet("QFrame { background: #d8f3dc; border: 1px solid #52796f; }")
        else:
            self.setStyleSheet("QFrame { background: white; border: 1px solid #cfc6b8; }")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(STUDENT_MIME) and not self.locked:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(STUDENT_MIME) and not self.locked:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if self.locked or not event.mimeData().hasFormat(STUDENT_MIME):
            event.ignore()
            return
        raw = bytes(event.mimeData().data(STUDENT_MIME)).decode("utf-8")
        if raw.isdigit():
            self.dropped.emit(self.seat_id, int(raw))
            event.acceptProposedAction()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_move(event)
            if self.student_id is None and not self.locked:
                self.empty_clicked.emit(self.seat_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self.student_id is not None
            and not self.locked
            and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            and self._drag_offset is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            if (event.position().toPoint() - self._drag_offset).manhattanLength() < 6:
                return
            mime = QMimeData()
            mime.setData(STUDENT_MIME, QByteArray(str(self.student_id).encode("utf-8")))
            drag = QDrag(self)
            drag.setMimeData(mime)
            self._drag_offset = None
            drag.exec(Qt.DropAction.MoveAction)
            return
        self._update_move(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        self._moving = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.locked:
            self.cleared.emit(self.seat_id)
        super().mouseDoubleClickEvent(event)

    def _menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        lock_action = menu.addAction("取消鎖定" if self.locked else "鎖定座位")
        clear_action = menu.addAction("清空學生")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is lock_action:
            self.lock_toggled.emit(self.seat_id)
        elif chosen is clear_action and not self.locked:
            self.cleared.emit(self.seat_id)


class DraggableStudentList(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)

    def startDrag(self, supported) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(STUDENT_MIME, QByteArray(str(item.data(256)).encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class SeatingWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.seats: dict[str, SeatCell] = {}
        self.students: list[Student] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("組別"))
        self.class_box = QComboBox()
        self.class_box.currentIndexChanged.connect(self._reload)
        left.addWidget(self.class_box)
        left.addWidget(QLabel("已儲存配置"))
        self.layout_box = QComboBox()
        left.addWidget(self.layout_box)
        left.addWidget(QLabel("未入座學生（拖到座位，或先選學生再按空位）"))
        self.student_list = DraggableStudentList()
        left.addWidget(self.student_list, 1)
        hint = QLabel(
            "拖移講台或座位可改位置；靠近另一座位會自動貼齊。Ctrl+拖曳已入座學生可對調。右鍵鎖定；雙擊清空學生。"
        )
        hint.setWordWrap(True)
        left.addWidget(hint)
        actions = QVBoxLayout()
        random_btn = QPushButton("隨機編排")
        reset_btn = QPushButton("重設位置")
        save_btn = QPushButton("儲存配置")
        load_btn = QPushButton("載入配置")
        export_btn = QPushButton("匯出 PDF")
        clear_btn = QPushButton("清空學生")
        random_btn.clicked.connect(self._randomize)
        reset_btn.clicked.connect(self._reset_positions)
        save_btn.clicked.connect(self._save)
        load_btn.clicked.connect(self._load)
        export_btn.clicked.connect(self._export)
        clear_btn.clicked.connect(self._clear)
        for button in (random_btn, reset_btn, save_btn, load_btn, export_btn, clear_btn):
            actions.addWidget(button)
        left.addLayout(actions)
        layout.addLayout(left, 1)

        self.canvas = QWidget()
        self.canvas.setMinimumSize(920, 720)
        self.canvas.setStyleSheet("background: #efe7d6;")
        self.podium = PodiumFrame()
        self.podium.setParent(self.canvas)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self.canvas)
        layout.addWidget(scroll, 3)

    def refresh(self) -> None:
        current = self.class_box.currentData()
        self.class_box.blockSignals(True)
        self.class_box.clear()
        for school_class in self.database.list_classes():
            self.class_box.addItem(school_class.name, school_class.id)
        self.class_box.blockSignals(False)
        if current is not None:
            index = self.class_box.findData(current)
            if index >= 0:
                self.class_box.setCurrentIndex(index)
        self._reload()

    def _current_class(self):
        class_id = self.class_box.currentData()
        if class_id is None:
            return None
        return next((item for item in self.database.list_classes() if item.id == class_id), None)

    def _reload(self) -> None:
        school_class = self._current_class()
        self.layout_box.clear()
        self.student_list.clear()
        self.students = []
        if school_class is None:
            self._apply_layout(default_room_layout(6, 7))
            return
        self.students = self.database.list_students(school_class.id)
        for name in self.database.list_layouts(school_class.id):
            self.layout_box.addItem(name)
        if self.layout_box.count() == 0:
            self.layout_box.addItem("預設")
        stored = self.database.get_layout(school_class.id, self.layout_box.currentText() or "預設")
        self._apply_layout(parse_layout(stored, school_class.rows, school_class.cols))
        self._refresh_unseated()

    def _clear_seats(self) -> None:
        for cell in self.seats.values():
            cell.deleteLater()
        self.seats.clear()

    def _apply_layout(self, layout: RoomLayout) -> None:
        self._clear_seats()
        self.podium.setGeometry(layout.podium.x, layout.podium.y, layout.podium.w, layout.podium.h)
        self.podium.show()
        lookup = {student.id: student for student in self.students}
        max_x = self.podium.x() + self.podium.width()
        max_y = self.podium.y() + self.podium.height()
        for item in layout.seats:
            cell = SeatCell(item.id)
            cell.setParent(self.canvas)
            cell.setGeometry(item.x, item.y, item.w, item.h)
            cell.set_student(lookup.get(item.student_id) if item.student_id else None)
            cell.set_locked(item.locked)
            cell.dropped.connect(self._on_dropped)
            cell.cleared.connect(self._on_cleared)
            cell.lock_toggled.connect(self._on_lock_toggled)
            cell.empty_clicked.connect(self._on_empty_clicked)
            cell.snapper = self._snap_seat
            cell.show()
            self.seats[item.id] = cell
            max_x = max(max_x, item.x + item.w)
            max_y = max(max_y, item.y + item.h)
        self.canvas.setMinimumSize(max(920, max_x + 40), max(720, max_y + 40))
        self.canvas.resize(self.canvas.minimumSize())

    def _snap_seat(self, moving: QWidget, x: int, y: int, w: int, h: int) -> tuple[int, int]:
        others = [
            (cell.x(), cell.y(), cell.width(), cell.height())
            for cell in self.seats.values()
            if cell is not moving
        ]
        return snap_to_neighbors(x, y, w, h, others)

    def _snapshot_layout(self) -> RoomLayout:
        seats = [
            SeatItem(
                id=cell.seat_id,
                x=cell.x(),
                y=cell.y(),
                w=cell.width(),
                h=cell.height(),
                student_id=cell.student_id,
                locked=cell.locked,
            )
            for cell in self.seats.values()
        ]
        return RoomLayout(
            podium=PodiumItem(self.podium.x(), self.podium.y(), self.podium.width(), self.podium.height()),
            seats=seats,
        )

    def _on_empty_clicked(self, seat_id: str) -> None:
        item = self.student_list.currentItem()
        if item is None:
            return
        self._place_student(seat_id, int(item.data(256)))

    def _place_student(self, seat_id: str, student_id: int) -> None:
        target = self.seats.get(seat_id)
        if target is None or target.locked:
            return
        lookup = {student.id: student for student in self.students}
        student = lookup.get(student_id)
        if student is None:
            return
        origin: SeatCell | None = None
        for cell in self.seats.values():
            if cell.student_id == student_id and cell is not target:
                origin = cell
                break
        occupant_id = target.student_id
        if origin is not None:
            if origin.locked:
                return
            origin.set_student(lookup.get(occupant_id) if occupant_id else None)
        target.set_student(student)
        self._refresh_unseated()

    def _on_dropped(self, seat_id: str, student_id: int) -> None:
        self._place_student(seat_id, student_id)

    def _on_cleared(self, seat_id: str) -> None:
        cell = self.seats.get(seat_id)
        if cell is not None and not cell.locked:
            cell.set_student(None)
            self._refresh_unseated()

    def _on_lock_toggled(self, seat_id: str) -> None:
        cell = self.seats.get(seat_id)
        if cell is not None:
            cell.set_locked(not cell.locked)

    def _refresh_unseated(self) -> None:
        seated = {cell.student_id for cell in self.seats.values() if cell.student_id}
        lookup = {student.id: student for student in self.students}
        for cell in self.seats.values():
            cell.set_student(lookup.get(cell.student_id) if cell.student_id else None)
        self.student_list.clear()
        for student in self.students:
            if student.id not in seated:
                extra = f" / {student.english_name}" if student.english_name else ""
                klass = f"{student.class_name}  " if student.class_name else ""
                item = QListWidgetItem(f"{klass}{student.student_no}  {student.name}{extra}")
                item.setData(256, student.id)
                self.student_list.addItem(item)

    def _randomize(self) -> None:
        school_class = self._current_class()
        if school_class is None:
            QMessageBox.information(self, "座位表", "請先在「組別與學生」新增組別及學生。")
            return
        if not self.students:
            QMessageBox.information(self, "座位表", "此組別尚未有學生。")
            return
        layout = randomize_layout(self._snapshot_layout(), self.students)
        self._apply_layout(layout)
        self._refresh_unseated()

    def _reset_positions(self) -> None:
        school_class = self._current_class()
        rows = school_class.rows if school_class else 6
        cols = school_class.cols if school_class else 7
        current = self._snapshot_layout()
        reset = default_room_layout(rows, cols)
        for index, seat in enumerate(reset.seats):
            if index < len(current.seats):
                seat.student_id = current.seats[index].student_id
                seat.locked = current.seats[index].locked
        self._apply_layout(reset)
        self._refresh_unseated()

    def _clear(self) -> None:
        layout = self._snapshot_layout()
        for seat in layout.seats:
            if not seat.locked:
                seat.student_id = None
        self._apply_layout(layout)
        self._refresh_unseated()

    def _save(self) -> None:
        school_class = self._current_class()
        if school_class is None:
            return
        name, ok = QInputDialog.getText(self, "儲存配置", "配置名稱：", text=self.layout_box.currentText() or "預設")
        if not ok or not name.strip():
            return
        self.database.save_layout(school_class.id, name.strip(), layout_to_json(self._snapshot_layout()))
        self.refresh()
        index = self.layout_box.findText(name.strip())
        if index >= 0:
            self.layout_box.setCurrentIndex(index)

    def _load(self) -> None:
        school_class = self._current_class()
        if school_class is None:
            return
        name = self.layout_box.currentText()
        stored = self.database.get_layout(school_class.id, name)
        if not stored:
            QMessageBox.information(self, "座位表", "沒有這個配置。")
            return
        self._apply_layout(parse_layout(stored, school_class.rows, school_class.cols))
        self._refresh_unseated()

    def _export(self) -> None:
        school_class = self._current_class()
        if school_class is None:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "匯出座位表", f"{school_class.name}-seating.pdf", "PDF (*.pdf)")
        if not dest:
            return
        lookup = {student.id: _student_label(student) for student in self.students}
        export_seating_pdf(
            Path(dest),
            school_class.name,
            self.layout_box.currentText() or "預設",
            self._snapshot_layout(),
            lookup,
        )
        QMessageBox.information(self, "座位表", "已匯出 PDF。")
