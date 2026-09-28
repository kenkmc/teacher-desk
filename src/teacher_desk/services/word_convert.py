from __future__ import annotations

import os
import shutil
import subprocess
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from pathlib import Path

from teacher_desk.services.file_conversion import finish_output, next_output_path


WORD_EXTENSIONS = {".doc", ".docx"}


@dataclass(frozen=True)
class ConversionEngine:
    name: str
    path: str | None = None


@dataclass
class ConversionResult:
    source: Path
    output: Path | None
    ok: bool
    message: str


def which_soffice() -> Path | None:
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "LibreOffice/program/soffice.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "LibreOffice/program/soffice.exe",
        Path("/usr/bin/soffice"),
        Path("/usr/lib/libreoffice/program/soffice"),
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def word_com_available() -> bool:
    if os.name != "nt":
        return False
    try:
        import win32com.client  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def detect_engine() -> ConversionEngine | None:
    soffice = which_soffice()
    if soffice:
        return ConversionEngine("LibreOffice", str(soffice))
    if word_com_available():
        return ConversionEngine("Microsoft Word")
    return None


def collect_word_files(paths: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in WORD_EXTENSIONS:
            files.append(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in path.glob(pattern):
                if child.is_file() and child.suffix.lower() in WORD_EXTENSIONS:
                    files.append(child)
    unique: list[Path] = []
    seen: set[Path] = set()
    for file in files:
        resolved = file.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(file)
    return unique


def _convert_with_libreoffice(source: Path, destination: Path, soffice: Path) -> Path:
    output_dir = destination.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="word-pdf-", dir=output_dir) as temporary_dir:
        command = [
            str(soffice),
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            temporary_dir,
            str(source),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
        temporary = Path(temporary_dir) / f"{source.stem}.pdf"
        if completed.returncode != 0 or not temporary.is_file():
            detail = (completed.stderr or completed.stdout or "轉檔失敗").strip()
            raise RuntimeError(detail)
        finish_output(temporary, destination)
    return destination


def _convert_with_word(source: Path, destination: Path) -> Path:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    destination.parent.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        try:
            document = word.Documents.Open(str(source.resolve()), ReadOnly=True)
            try:
                # 17 = wdFormatPDF
                document.SaveAs(str(destination.resolve()), FileFormat=17)
            finally:
                document.Close(False)
        finally:
            word.Quit()
    finally:
        pythoncom.CoUninitialize()
    if not destination.is_file():
        raise RuntimeError("Word 沒有產生 PDF")
    return destination


def convert_file(source: Path, output_dir: Path, engine: ConversionEngine) -> ConversionResult:
    try:
        if not source.is_file() or source.suffix.lower() not in WORD_EXTENSIONS:
            raise ValueError(f"不是有效的 Word 檔案：{source}")
        destination = next_output_path(source, output_dir, ".pdf")
        if engine.name == "LibreOffice":
            if not engine.path:
                raise RuntimeError("找不到 LibreOffice")
            output = _convert_with_libreoffice(source, destination, Path(engine.path))
        elif engine.name == "Microsoft Word":
            output = _convert_with_word(source, destination)
        else:
            raise RuntimeError(f"未知引擎：{engine.name}")
        return ConversionResult(source, output, True, "完成")
    except Exception as exc:  # noqa: BLE001 — surface conversion errors to the UI
        return ConversionResult(source, None, False, str(exc))
