from __future__ import annotations

import subprocess

from PySide6.QtWidgets import QApplication

from teacher_desk.db import Database
from teacher_desk.modules.file_conversion.widget import FileConversionWidget
from teacher_desk.modules.registry import available_modules
from teacher_desk.services import word_convert
from teacher_desk.services.word_convert import ConversionEngine, convert_file


def test_word_to_pdf_keeps_existing_pdf(tmp_path, monkeypatch) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"sample Word file")
    output_dir = tmp_path / "Converted"
    output_dir.mkdir()
    existing = output_dir / "lesson.pdf"
    existing.write_bytes(b"existing PDF")

    def fake_run(command, **kwargs):
        temporary = command[command.index("--outdir") + 1]
        from pathlib import Path

        (Path(temporary) / "lesson.pdf").write_bytes(b"new PDF")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(word_convert.subprocess, "run", fake_run)
    result = convert_file(source, output_dir, ConversionEngine("LibreOffice", "soffice.exe"))

    assert result.ok
    assert result.output == output_dir / "lesson (2).pdf"
    assert existing.read_bytes() == b"existing PDF"
    assert result.output.read_bytes() == b"new PDF"
    assert source.read_bytes() == b"sample Word file"


def test_word_is_a_tab_in_file_conversion(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    specs = available_modules()
    assert not any(spec.id == "word_to_pdf" for spec in specs)
    widget = FileConversionWidget(Database(tmp_path / "desk.sqlite3"))
    assert widget.tabs.count() == 3
    assert widget.tabs.tabText(0) == "Word → PDF"

    source = tmp_path / "lesson.docx"
    source.write_bytes(b"sample")
    widget.word_panel.add_paths([source, source])
    assert widget.word_panel.file_list.count() == 1
    assert widget.word_panel.output_dir == tmp_path / "Converted"
    widget.word_panel.file_list.setCurrentRow(0)
    widget.word_panel._remove_selected()
    assert widget.word_panel.file_list.count() == 0
    widget.close()
    app.processEvents()
