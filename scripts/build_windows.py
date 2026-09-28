"""Build a single-file Windows release with bundled Python and local OCR."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PyInstaller.__main__ import run
from PyInstaller.archive.readers import CArchiveReader

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from generate_english import generate_english_source
from generate_bilingual import generate_bilingual_source


ROOT = Path(__file__).resolve().parents[1]


def tesseract_files(arguments: list[str]) -> bool:
    root = Path(os.environ.get("TESSERACT_ROOT", r"C:\Program Files\Tesseract-OCR"))
    executable = root / "tesseract.exe"
    if not executable.is_file():
        print("Tesseract not found: local image OCR will need an installed Tesseract or cloud OCR.")
        return False

    for path in [executable, *sorted(root.glob("*.dll"))]:
        arguments.extend(["--add-binary", f"{path}{os.pathsep}tesseract"])
    for language in ("eng", "chi_tra", "osd"):
        path = root / "tessdata" / f"{language}.traineddata"
        if not path.is_file():
            raise FileNotFoundError(f"Required Tesseract language data is missing: {path}")
        arguments.extend(["--add-data", f"{path}{os.pathsep}tesseract/tessdata"])
    license_file = root / "doc" / "LICENSE"
    if license_file.is_file():
        arguments.extend(["--add-data", f"{license_file}{os.pathsep}tesseract"])
    return True


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Build this release on Windows.")
    # A development shell may have PDF/image tool directories on PATH. Qt
    # imports Windows ICU entry points, while those tools carry incompatible
    # ICU DLLs with the same filename.
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    os.environ["PATH"] = os.pathsep.join(
        str(path) for path in (Path(sys.executable).parent, windows / "System32", windows)
    )
    english = "--english" in sys.argv[1:]
    source = generate_english_source() if english else generate_bilingual_source()
    name = "TeacherDesk-English" if english else "TeacherDesk"
    workpath = ROOT / "build" / ("english-pyinstaller" if english else "chinese-pyinstaller")
    arguments = [
        str(source / "teacher_desk" / "app.py"),
        f"--name={name}",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        f"--paths={source}",
        f"--distpath={ROOT / 'dist'}",
        f"--workpath={workpath}",
        f"--specpath={workpath}",
    ]
    tesseract_files(arguments)
    run(arguments)
    archive = CArchiveReader(str(ROOT / "dist" / f"{name}.exe"))
    if any(name.lower().replace("/", "\\") == "icuuc.dll" for name in archive.toc):
        raise RuntimeError("Incompatible ICU DLL was bundled at the executable root.")
    if not any(name.lower().replace("/", "\\").startswith("imageio_ffmpeg\\binaries\\ffmpeg") for name in archive.toc):
        raise RuntimeError("FFmpeg is missing from the packaged application.")
    if not any(name.lower().replace("/", "\\").startswith("zxingcpp\\") and name.lower().endswith(".pyd") for name in archive.toc):
        raise RuntimeError("The QR decoder is missing from the packaged application.")
    executable = ROOT / "dist" / f"{name}.exe"
    result = subprocess.run(
        [str(executable), "--self-test-english" if english else "--self-test-bilingual"],
        timeout=90, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Packaged application self-test failed: exit code {result.returncode}.")
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    if version_match is None:
        raise RuntimeError("Could not determine the release version.")
    edition = "-English" if english else ""
    release = ROOT / "dist" / f"TeacherDesk-{version_match.group(1)}{edition}-Windows-x64.exe"
    shutil.copy2(executable, release)
    print("Packaged application self-test passed.")


if __name__ == "__main__":
    main()
