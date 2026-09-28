from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from teacher_desk.paths import database_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    rows INTEGER NOT NULL DEFAULT 6,
    cols INTEGER NOT NULL DEFAULT 7
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    student_no TEXT NOT NULL,
    name TEXT NOT NULL,
    english_name TEXT NOT NULL DEFAULT '',
    class_name TEXT NOT NULL DEFAULT '',
    gender TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    UNIQUE (class_id, student_no)
);

CREATE TABLE IF NOT EXISTS seating_layouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    grid_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    UNIQUE (class_id, name)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timetable_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    remind_before INTEGER NOT NULL DEFAULT 10 CHECK (remind_before BETWEEN 0 AND 1440),
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    entry_id INTEGER NOT NULL,
    occurrence_date TEXT NOT NULL,
    PRIMARY KEY (entry_id, occurrence_date),
    FOREIGN KEY (entry_id) REFERENCES timetable_entries(id) ON DELETE CASCADE
);
"""


def _clear_student_ids(grid_json: str, removed_ids: set[int]) -> str:
    """Remove deleted students from both current and legacy seating layouts."""
    try:
        data = json.loads(grid_json)
    except json.JSONDecodeError:
        return grid_json

    changed = False

    def is_removed(value: object) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, str))
            and str(value).isdigit()
            and int(value) in removed_ids
        )

    def clear_grid(grid: object) -> None:
        nonlocal changed
        if not isinstance(grid, list):
            return
        for row in grid:
            if not isinstance(row, list):
                continue
            for index, student_id in enumerate(row):
                if is_removed(student_id):
                    row[index] = None
                    changed = True

    if isinstance(data, list):
        clear_grid(data)
    elif isinstance(data, dict):
        clear_grid(data.get("grid"))
        seats = data.get("seats")
        if isinstance(seats, list):
            for seat in seats:
                if isinstance(seat, dict) and is_removed(seat.get("student_id")):
                    seat["student_id"] = None
                    changed = True
    return json.dumps(data, ensure_ascii=False) if changed else grid_json


def _clear_layout_student_ids(conn: sqlite3.Connection, class_id: int, removed_ids: set[int]) -> None:
    for layout in conn.execute(
        "SELECT id, grid_json FROM seating_layouts WHERE class_id = ?", (class_id,)
    ).fetchall():
        updated = _clear_student_ids(str(layout["grid_json"]), removed_ids)
        if updated != layout["grid_json"]:
            conn.execute(
                "UPDATE seating_layouts SET grid_json = ? WHERE id = ?",
                (updated, layout["id"]),
            )


@dataclass
class SchoolClass:
    """組別（座位表單位，可跨班）。"""

    id: int
    name: str
    rows: int
    cols: int


@dataclass
class Student:
    id: int
    class_id: int
    student_no: str
    name: str
    english_name: str = ""
    class_name: str = ""
    gender: str = ""
    notes: str = ""


@dataclass(frozen=True)
class TimetableEntry:
    id: int | None
    weekday: int
    start_time: str
    end_time: str
    title: str
    location: str = ""
    remind_before: int = 10
    enabled: bool = True


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.session() as conn:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
            if "english_name" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN english_name TEXT NOT NULL DEFAULT ''")
            if "class_name" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN class_name TEXT NOT NULL DEFAULT ''")

    def get_setting(self, key: str, default: str = "") -> str:
        with self.session() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def list_classes(self) -> list[SchoolClass]:
        with self.session() as conn:
            rows = conn.execute("SELECT * FROM classes ORDER BY name").fetchall()
        return [SchoolClass(r["id"], r["name"], r["rows"], r["cols"]) for r in rows]

    def add_class(self, name: str, rows: int = 6, cols: int = 7) -> int:
        with self.session() as conn:
            cur = conn.execute(
                "INSERT INTO classes(name, rows, cols) VALUES(?, ?, ?)",
                (name.strip(), rows, cols),
            )
            return int(cur.lastrowid)

    def update_class(self, class_id: int, name: str, rows: int, cols: int) -> None:
        with self.session() as conn:
            conn.execute(
                "UPDATE classes SET name = ?, rows = ?, cols = ? WHERE id = ?",
                (name.strip(), rows, cols, class_id),
            )

    def delete_class(self, class_id: int) -> None:
        with self.session() as conn:
            conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))

    def list_students(self, class_id: int) -> list[Student]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM students WHERE class_id = ? ORDER BY student_no, name",
                (class_id,),
            ).fetchall()
        return [
            Student(
                r["id"],
                r["class_id"],
                r["student_no"],
                r["name"],
                r["english_name"] if "english_name" in r.keys() else "",
                r["class_name"] if "class_name" in r.keys() else "",
                r["gender"] or "",
                r["notes"] or "",
            )
            for r in rows
        ]

    def add_student(
        self,
        class_id: int,
        student_no: str,
        name: str,
        english_name: str = "",
        class_name: str = "",
        gender: str = "",
        notes: str = "",
    ) -> int:
        with self.session() as conn:
            cur = conn.execute(
                "INSERT INTO students(class_id, student_no, name, english_name, class_name, gender, notes) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    class_id,
                    student_no.strip(),
                    name.strip(),
                    english_name.strip(),
                    class_name.strip(),
                    gender.strip(),
                    notes.strip(),
                ),
            )
            return int(cur.lastrowid)

    def delete_student(self, student_id: int) -> None:
        with self.session() as conn:
            row = conn.execute("SELECT class_id FROM students WHERE id = ?", (student_id,)).fetchone()
            if row is not None:
                _clear_layout_student_ids(conn, int(row["class_id"]), {student_id})
            conn.execute("DELETE FROM students WHERE id = ?", (student_id,))

    def replace_students(self, class_id: int, students: list[tuple[str, str, str, str]]) -> None:
        incoming: dict[str, tuple[str, str, str]] = {}
        for no, chinese, english, class_name in students:
            student_no = no.strip()
            if not student_no:
                raise ValueError("學號不可留空")
            if student_no in incoming:
                raise ValueError(f"名冊有重複學號：{student_no}")
            incoming[student_no] = (chinese.strip(), english.strip(), class_name.strip())

        with self.session() as conn:
            existing = {
                str(row["student_no"]): int(row["id"])
                for row in conn.execute("SELECT id, student_no FROM students WHERE class_id = ?", (class_id,))
            }
            for student_no, (chinese, english, class_name) in incoming.items():
                if student_no in existing:
                    conn.execute(
                        "UPDATE students SET name = ?, english_name = ?, class_name = ? WHERE id = ?",
                        (chinese, english, class_name, existing[student_no]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO students(class_id, student_no, name, english_name, class_name) VALUES(?, ?, ?, ?, ?)",
                        (class_id, student_no, chinese, english, class_name),
                    )

            removed_ids = {student_id for no, student_id in existing.items() if no not in incoming}
            if removed_ids:
                _clear_layout_student_ids(conn, class_id, removed_ids)
                conn.executemany("DELETE FROM students WHERE id = ?", [(student_id,) for student_id in removed_ids])

    def get_layout(self, class_id: int, name: str) -> str | None:
        with self.session() as conn:
            row = conn.execute(
                "SELECT grid_json FROM seating_layouts WHERE class_id = ? AND name = ?",
                (class_id, name),
            ).fetchone()
            return str(row["grid_json"]) if row else None

    def save_layout(self, class_id: int, name: str, grid_json: str) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO seating_layouts(class_id, name, grid_json)
                VALUES(?, ?, ?)
                ON CONFLICT(class_id, name) DO UPDATE SET grid_json = excluded.grid_json
                """,
                (class_id, name, grid_json),
            )

    def list_layouts(self, class_id: int) -> list[str]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT name FROM seating_layouts WHERE class_id = ? ORDER BY name",
                (class_id,),
            ).fetchall()
        return [str(r["name"]) for r in rows]

    def list_timetable_entries(self) -> list[TimetableEntry]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM timetable_entries ORDER BY weekday, start_time, title"
            ).fetchall()
        return [
            TimetableEntry(
                id=int(row["id"]),
                weekday=int(row["weekday"]),
                start_time=str(row["start_time"]),
                end_time=str(row["end_time"]),
                title=str(row["title"]),
                location=str(row["location"]),
                remind_before=int(row["remind_before"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def replace_timetable_entries(self, entries: list[TimetableEntry]) -> None:
        with self.session() as conn:
            existing = {
                (row["weekday"], row["start_time"], row["end_time"], row["title"]): row["id"]
                for row in conn.execute(
                    "SELECT id, weekday, start_time, end_time, title FROM timetable_entries"
                )
            }
            retained_ids = set()
            seen_keys = set()
            for entry in entries:
                title = entry.title.strip()
                key = (entry.weekday, entry.start_time, entry.end_time, title)
                if key in seen_keys:
                    raise ValueError(f"時間表有重複項目：{title} {entry.start_time}")
                seen_keys.add(key)
                if key in existing:
                    entry_id = int(existing[key])
                    retained_ids.add(entry_id)
                    conn.execute(
                        "UPDATE timetable_entries SET location = ?, remind_before = ?, enabled = ? WHERE id = ?",
                        (entry.location.strip(), entry.remind_before, int(entry.enabled), entry_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO timetable_entries
                            (weekday, start_time, end_time, title, location, remind_before, enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (*key, entry.location.strip(), entry.remind_before, int(entry.enabled)),
                    )
            removed_ids = set(existing.values()) - retained_ids
            conn.executemany("DELETE FROM timetable_entries WHERE id = ?", [(item,) for item in removed_ids])

    def mark_reminder_delivered(self, entry_id: int, occurrence_date: str) -> bool:
        with self.session() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO reminder_deliveries(entry_id, occurrence_date) VALUES (?, ?)",
                (entry_id, occurrence_date),
            )
            return cursor.rowcount == 1
