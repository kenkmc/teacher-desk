from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths


APP_DIR_NAME = "TeacherDesk"


def app_data_dir() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    path = Path(root) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return app_data_dir() / "teacher_desk.sqlite3"
