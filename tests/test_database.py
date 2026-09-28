from pathlib import Path

import pytest

from teacher_desk.db import Database
from teacher_desk.services.seating import layout_to_json, parse_layout


def test_class_and_student_crud(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.sqlite3")
    class_id = db.add_class("跨班小組", 5, 6)
    db.add_student(class_id, "01", "陳小明", "Chan Siu Ming", "1A")
    students = db.list_students(class_id)
    assert len(students) == 1
    assert students[0].name == "陳小明"
    assert students[0].english_name == "Chan Siu Ming"
    assert students[0].class_name == "1A"
    db.replace_students(class_id, [("02", "李美華", "Lee Mei Wah", "1B")])
    assert db.list_students(class_id)[0].student_no == "02"
    assert db.list_students(class_id)[0].english_name == "Lee Mei Wah"
    assert db.list_students(class_id)[0].class_name == "1B"
    db.save_layout(class_id, "測驗", "[[1,null]]")
    assert db.get_layout(class_id, "測驗") == "[[1,null]]"
    db.set_setting("mc_grader_path", "C:/tools/grader.py")
    assert db.get_setting("mc_grader_path") == "C:/tools/grader.py"


def test_reimport_preserves_seats_and_clears_removed_students(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.sqlite3")
    class_id = db.add_class("跨班小組", 1, 2)
    retained_id = db.add_student(class_id, "01", "陳小明", notes="跟進中")
    removed_id = db.add_student(class_id, "02", "李美華")
    layout = parse_layout(None, 1, 2)
    layout.seats[0].student_id = retained_id
    layout.seats[1].student_id = removed_id
    db.save_layout(class_id, "新版", layout_to_json(layout))
    db.save_layout(class_id, "舊版", f"[[{retained_id},{removed_id}]]")

    db.replace_students(class_id, [("01", "陳小明更新", "Chan", "1A"), ("03", "新學生", "", "1B")])

    students = {student.student_no: student for student in db.list_students(class_id)}
    assert students["01"].id == retained_id
    assert students["01"].name == "陳小明更新"
    assert students["01"].notes == "跟進中"
    assert students["03"].id not in {retained_id, removed_id}
    for name in ("新版", "舊版"):
        stored = parse_layout(db.get_layout(class_id, name), 1, 2)
        assert [seat.student_id for seat in stored.seats] == [retained_id, None]

    db.replace_students(class_id, [("01", "陳小明更新", "Chan", "1A"), ("03", "新學生", "", "1B")])
    assert {student.student_no: student.id for student in db.list_students(class_id)} == {
        no: student.id for no, student in students.items()
    }


def test_duplicate_import_does_not_change_roster(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.sqlite3")
    class_id = db.add_class("組別")
    original_id = db.add_student(class_id, "01", "原學生")

    with pytest.raises(ValueError, match="重複學號"):
        db.replace_students(class_id, [("01", "更新", "", ""), (" 01 ", "重複", "", "")])

    assert [(student.id, student.name) for student in db.list_students(class_id)] == [(original_id, "原學生")]


def test_delete_student_clears_saved_seat(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.sqlite3")
    class_id = db.add_class("組別", 1, 1)
    student_id = db.add_student(class_id, "01", "學生")
    db.save_layout(class_id, "座位", f"[[{student_id}]]")

    db.delete_student(student_id)

    assert db.list_students(class_id) == []
    assert parse_layout(db.get_layout(class_id, "座位"), 1, 1).seats[0].student_id is None
