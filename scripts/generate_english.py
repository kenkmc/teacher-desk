"""Create an English source copy for the standalone English edition.

The Chinese source remains the development source of truth. Build-time AST
translation keeps behavior and formatted values identical in both editions.
"""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

from english_translations import TRANSLATIONS


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "teacher_desk"
TARGET = ROOT / "build" / "english-src" / "teacher_desk"
HAN = re.compile(r"[\u3400-\u9fff]")
SAFE_SERVICE_FILES = (
    "checkmate.py", "file_conversion.py", "pdf_export.py", "pdf_tools.py",
    "qr_scan.py", "timetable_vision.py", "word_convert.py",
)
RAISE_ONLY_FILES = ("roster_import.py", "timetable_import.py")


class EnglishLiterals(ast.NodeTransformer):
    def __init__(self) -> None:
        self.missing: set[str] = set()

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        value = node.value
        if isinstance(value, str) and HAN.search(value):
            translated = TRANSLATIONS.get(value)
            if translated is None:
                self.missing.add(value)
            else:
                return ast.copy_location(ast.Constant(translated), node)
        return node


class EnglishErrors(ast.NodeTransformer):
    """Translate raised errors while preserving Chinese import/parser terms."""

    def __init__(self) -> None:
        self.missing: set[str] = set()

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        translator = EnglishLiterals()
        translated = translator.visit(node)
        self.missing.update(translator.missing)
        return translated


def generate_english_source() -> Path:
    shutil.copytree(SOURCE, TARGET, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (TARGET / "edition.py").write_text(
        '"""English edition marker."""\n\nIS_ENGLISH = True\nIS_BILINGUAL = False\n', encoding="utf-8"
    )
    missing: set[str] = set()
    files = [
        TARGET / "app.py",
        *TARGET.joinpath("modules").rglob("*.py"),
        *TARGET.joinpath("ui").rglob("*.py"),
        *(TARGET / "services" / name for name in SAFE_SERVICE_FILES),
        *(TARGET / "services" / name for name in RAISE_ONLY_FILES),
    ]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        translator = EnglishErrors() if path.name in RAISE_ONLY_FILES else EnglishLiterals()
        translated = ast.fix_missing_locations(translator.visit(tree))
        missing.update(translator.missing)
        path.write_text(ast.unparse(translated) + "\n", encoding="utf-8")
    if missing:
        for value in sorted(missing):
            print(f"Missing English translation: {value!r}")
        raise RuntimeError(f"{len(missing)} UI strings need English translations.")
    return TARGET.parent


if __name__ == "__main__":
    print(generate_english_source())
