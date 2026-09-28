"""The current interface language and persisted language setting."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment

from teacher_desk.db import Database


LANGUAGE_SETTING = "ui_language"
SUPPORTED_LANGUAGES = ("zh", "en")
_current_language = "zh"


def normalize_language(value: str) -> str:
    return value if value in SUPPORTED_LANGUAGES else "zh"


def load_language(database: Database) -> str:
    return normalize_language(database.get_setting(LANGUAGE_SETTING, "zh"))


def set_language(value: str) -> None:
    global _current_language
    _current_language = normalize_language(value)


def current_language() -> str:
    return _current_language


def is_english() -> bool:
    return _current_language == "en"


def restart_application() -> bool:
    """Launch an independent copy of this application with the saved language."""
    process = QProcess()
    process.setProgram(sys.executable)
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
    if getattr(sys, "frozen", False):
        process.setArguments([])
    else:
        process.setArguments(["-m", "teacher_desk"])
        source_root = str(Path(__file__).resolve().parents[1])
        existing = environment.value("PYTHONPATH")
        environment.insert("PYTHONPATH", source_root + (os.pathsep + existing if existing else ""))
    process.setProcessEnvironment(environment)
    result = process.startDetached()
    return bool(result[0] if isinstance(result, tuple) else result)
