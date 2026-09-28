"""Generate a bilingual package from the Chinese source and English catalog."""

from __future__ import annotations

import ast
import copy
import shutil
from pathlib import Path

from english_translations import TRANSLATIONS
from generate_english import HAN, RAISE_ONLY_FILES, SAFE_SERVICE_FILES, SOURCE, ROOT


TARGET = ROOT / "build" / "bilingual-src" / "teacher_desk"


class BilingualLiterals(ast.NodeTransformer):
    def __init__(self) -> None:
        self.missing: set[str] = set()
        self.changed = 0

    @staticmethod
    def _choice(node: ast.AST, english: ast.AST) -> ast.AST:
        return ast.copy_location(
            ast.IfExp(
                test=ast.Call(func=ast.Name(id="is_english", ctx=ast.Load()), args=[], keywords=[]),
                body=english,
                orelse=copy.deepcopy(node),
            ),
            node,
        )

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        value = node.value
        if isinstance(value, str) and HAN.search(value):
            translated = TRANSLATIONS.get(value)
            if translated is None:
                self.missing.add(value)
                return node
            self.changed += 1
            return self._choice(node, ast.Constant(translated))
        return node

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        if not any(isinstance(value, ast.Constant) and isinstance(value.value, str) and HAN.search(value.value)
                   for value in node.values):
            return self.generic_visit(node)
        english = copy.deepcopy(node)
        for index, value in enumerate(english.values):
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str) or not HAN.search(value.value):
                continue
            translated = TRANSLATIONS.get(value.value)
            if translated is None:
                self.missing.add(value.value)
                continue
            english.values[index] = ast.copy_location(ast.Constant(translated), value)
            self.changed += 1
        return self._choice(node, english)


class BilingualErrors(ast.NodeTransformer):
    def __init__(self) -> None:
        self.missing: set[str] = set()
        self.changed = 0

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        translator = BilingualLiterals()
        translated = translator.visit(node)
        self.missing.update(translator.missing)
        self.changed += translator.changed
        return translated


def _add_language_import(tree: ast.Module) -> None:
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom) and statement.module == "teacher_desk.language":
            if any(alias.name == "is_english" for alias in statement.names):
                return
    position = 0
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
        position = 1
    while position < len(tree.body) and isinstance(tree.body[position], ast.ImportFrom) and tree.body[position].module == "__future__":
        position += 1
    tree.body.insert(position, ast.ImportFrom(module="teacher_desk.language", names=[ast.alias(name="is_english")], level=0))


def generate_bilingual_source() -> Path:
    shutil.copytree(SOURCE, TARGET, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (TARGET / "edition.py").write_text(
        '"""Bilingual edition marker."""\n\nIS_ENGLISH = False\nIS_BILINGUAL = True\n', encoding="utf-8"
    )
    files = [
        TARGET / "app.py",
        *(TARGET / "modules").rglob("*.py"),
        *(TARGET / "ui").rglob("*.py"),
        *(TARGET / "services" / name for name in SAFE_SERVICE_FILES),
        *(TARGET / "services" / name for name in RAISE_ONLY_FILES),
    ]
    missing: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        translator = BilingualErrors() if path.name in RAISE_ONLY_FILES else BilingualLiterals()
        translated = translator.visit(tree)
        missing.update(translator.missing)
        if translator.changed:
            _add_language_import(translated)
        translated = ast.fix_missing_locations(translated)
        path.write_text(ast.unparse(translated) + "\n", encoding="utf-8")
    if missing:
        for value in sorted(missing):
            print(f"Missing English translation: {value!r}")
        raise RuntimeError(f"{len(missing)} UI strings need English translations.")
    return TARGET.parent


if __name__ == "__main__":
    print(generate_bilingual_source())
