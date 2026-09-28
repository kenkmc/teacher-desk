from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile(r"[\u3400-\u9fff]")


def test_generated_english_edition_has_no_chinese_ui_literals() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_english.py")], check=True)
    package = ROOT / "build" / "english-src" / "teacher_desk"
    assert "IS_ENGLISH = True" in (package / "edition.py").read_text(encoding="utf-8")
    files = [package / "app.py", *(package / "modules").rglob("*.py"), *(package / "ui").rglob("*.py")]
    remaining = {
        node.value
        for path in files
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and HAN.search(node.value)
    }
    assert not remaining
