from pathlib import Path

from teacher_desk.services.roster_import import import_students, parse_table_rows


def test_parse_chinese_headers() -> None:
    students = parse_table_rows(
        ["班別", "學號", "中文姓名", "英文姓名"],
        [["1A", "1", "陳小明", "Chan Siu Ming"], ["1B", "2", "李美華", "Lee Mei Wah"], ["", "", "", ""]],
    )
    assert students == [("1", "陳小明", "Chan Siu Ming", "1A"), ("2", "李美華", "Lee Mei Wah", "1B")]


def test_parse_english_headers_and_auto_number() -> None:
    students = parse_table_rows(["name"], [["Ada"], ["Ben"]])
    assert students[0][1] == "Ada"
    assert students[1] == ("2", "Ben", "", "")


def test_parse_english_name_only() -> None:
    students = parse_table_rows(["學號", "英文姓名"], [["7", "Ada Chan"]])
    assert students == [("7", "", "Ada Chan", "")]


def test_import_csv_handles_quoted_commas_and_newlines(tmp_path: Path) -> None:
    path = tmp_path / "students.csv"
    path.write_bytes(
        'student_no,name,english_name\n1,"Chan, Mei",Mei Chan\n2,"Lee\nWing",Wing Lee\n'.encode("utf-8-sig")
    )
    assert import_students(path) == [
        ("1", "Chan, Mei", "Mei Chan", ""),
        ("2", "Lee\nWing", "Wing Lee", ""),
    ]
