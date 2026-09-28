"""Locate CheckMate on local disks, or download and install from GitHub."""

from __future__ import annotations

import hashlib
import json
import os
import re
import string
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

CHECKMATE_RELEASE_PAGE = "https://github.com/kenkmc/Checkmate/releases/tag/v1.7.1"
CHECKMATE_REPO = "kenkmc/Checkmate"
CHECKMATE_FALLBACK_TAG = "v1.7.1"
GITHUB_API = "https://api.github.com"
USER_AGENT = "TeacherDesk-CheckMateLocator"
EXE_NAME = "CheckMate.exe"
DEFAULT_INSTALL_DIR = Path(r"D:\CheckMate")

SKIP_DIR_NAMES = {
    "$recycle.bin",
    "$windows.~bt",
    "$windows.~ws",
    ".git",
    "__pycache__",
    "config.msi",
    "csc",
    "msocache",
    "node_modules",
    "recovery",
    "system volume information",
    "windows",
    "windows.old",
    "winsxs",
}

ProgressFn = Callable[[str], None]


@dataclass(frozen=True)
class CheckMateHit:
    path: Path
    version: str = ""
    size: int = 0

    @property
    def is_build_tree(self) -> bool:
        return any(part.lower() in {"build", "dist"} for part in self.path.parts)


@dataclass(frozen=True)
class ReleaseAsset:
    tag: str
    name: str
    url: str
    size: int
    sha256: str = ""


def official_install_dir() -> Path:
    if sys.platform == "win32" and Path("D:/").exists():
        return DEFAULT_INSTALL_DIR
    local = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(local) / "CheckMate"


def official_exe() -> Path:
    return official_install_dir() / EXE_NAME


def windows_fixed_drives() -> list[Path]:
    if sys.platform != "win32":
        return [Path("/")]
    try:
        bitmask = int(ctypes_get_logical_drives())
    except OSError:
        bitmask = 0
        for letter in string.ascii_uppercase:
            if Path(f"{letter}:/").exists():
                bitmask |= 1 << (ord(letter) - 65)
    drives: list[Path] = []
    for i, letter in enumerate(string.ascii_uppercase):
        if not bitmask & (1 << i):
            continue
        root = Path(f"{letter}:/")
        if _drive_type(f"{letter}:\\") in {0, 2, 3, 4}:  # unknown, removable, fixed, remote
            drives.append(root)
    return drives or [Path("C:/")]


def ctypes_get_logical_drives() -> int:
    import ctypes

    return ctypes.windll.kernel32.GetLogicalDrives()


def _drive_type(root: str) -> int:
    if sys.platform != "win32":
        return 3
    import ctypes

    return int(ctypes.windll.kernel32.GetDriveTypeW(root))


def iter_checkmate_exes(
    roots: Iterable[Path],
    progress: ProgressFn | None = None,
) -> list[CheckMateHit]:
    hits: list[CheckMateHit] = []
    seen: set[str] = set()
    for root in roots:
        root = Path(root)
        if progress:
            progress(f"正在搜尋：{root}")
        if root.is_file():
            if root.name.lower() == EXE_NAME.lower():
                hits.append(_hit_from_path(root))
            continue
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda _exc: None):
            dirnames[:] = [name for name in dirnames if name.lower() not in SKIP_DIR_NAMES]
            for name in filenames:
                if name.lower() != EXE_NAME.lower():
                    continue
                path = Path(dirpath) / name
                key = str(path).lower()
                if key in seen:
                    continue
                seen.add(key)
                hits.append(_hit_from_path(path))
                if progress:
                    progress(f"找到：{path}")
    return hits


def _hit_from_path(path: Path) -> CheckMateHit:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    version = pe_product_version(path) or version_from_path(path)
    return CheckMateHit(path=path, version=version, size=size)


def version_from_path(path: Path) -> str:
    text = str(path)
    match = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
    return match.group(1) if match else ""


def pe_product_version(path: Path) -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return ""

    get_size = ctypes.windll.version.GetFileVersionInfoSizeW
    get_info = ctypes.windll.version.GetFileVersionInfoW
    query = ctypes.windll.version.VerQueryValueW
    size = get_size(str(path), None)
    if not size:
        return ""
    buf = ctypes.create_string_buffer(size)
    if not get_info(str(path), 0, size, buf):
        return ""

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
            ("dwProductVersionMS", wintypes.DWORD),
            ("dwProductVersionLS", wintypes.DWORD),
        ]

    ptr = ctypes.c_void_p()
    length = wintypes.UINT()
    if not query(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)) or not ptr.value:
        return ""
    info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    if info.dwSignature != 0xFEEF04BD:
        return ""
    ms, ls = info.dwProductVersionMS, info.dwProductVersionLS
    major, minor = (ms >> 16) & 0xFFFF, ms & 0xFFFF
    patch, build = (ls >> 16) & 0xFFFF, ls & 0xFFFF
    if build:
        return f"{major}.{minor}.{patch}.{build}"
    return f"{major}.{minor}.{patch}"


def version_key(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version or "")
    return tuple(int(p) for p in parts) if parts else (0,)


def pick_best_hit(hits: Iterable[CheckMateHit]) -> CheckMateHit | None:
    ranked = list(hits)
    if not ranked:
        return None
    official = official_exe()

    def sort_key(hit: CheckMateHit) -> tuple:
        try:
            same_official = hit.path.resolve() == official.resolve()
        except OSError:
            same_official = False
        return (
            1 if same_official else 0,
            0 if hit.is_build_tree else 1,
            version_key(hit.version),
            hit.size,
        )

    return max(ranked, key=sort_key)


def parse_sha256sums(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line.strip())
        if not match:
            continue
        mapping[Path(match.group(2).strip()).name] = match.group(1).lower()
    return mapping


def _http_json(url: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _repo_from_release_page(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return CHECKMATE_REPO


def fetch_setup_asset(
    release_page: str = CHECKMATE_RELEASE_PAGE,
    progress: ProgressFn | None = None,
) -> ReleaseAsset:
    tag = _tag_from_release_page(release_page) or CHECKMATE_FALLBACK_TAG
    repo = _repo_from_release_page(release_page)
    api_urls = [
        f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}",
        f"{GITHUB_API}/repos/{repo}/releases/latest",
    ]
    data: dict | None = None
    last_error = ""
    for url in api_urls:
        try:
            if progress:
                progress(f"讀取發行資料：{url}")
            data = _http_json(url)
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = str(exc)
    if data:
        tag_name = str(data.get("tag_name") or tag)
        assets = data.get("assets") or []
        setup = next(
            (
                item
                for item in assets
                if str(item.get("name", "")).lower().startswith("checkmate_setup")
                and str(item.get("name", "")).lower().endswith(".exe")
            ),
            None,
        )
        if not setup:
            raise RuntimeError("發行頁沒有 CheckMate 安裝檔。")
        sums_asset = next((item for item in assets if "sha256" in str(item.get("name", "")).lower()), None)
        sha256 = ""
        if sums_asset and sums_asset.get("browser_download_url"):
            try:
                mapping = parse_sha256sums(_http_text(str(sums_asset["browser_download_url"])))
                sha256 = mapping.get(str(setup["name"]), "")
            except (urllib.error.URLError, TimeoutError, OSError):
                sha256 = ""
        return ReleaseAsset(
            tag=tag_name,
            name=str(setup["name"]),
            url=str(setup["browser_download_url"]),
            size=int(setup.get("size") or 0),
            sha256=sha256,
        )
    name = f"CheckMate_Setup_{tag}.exe"
    direct = f"https://github.com/{repo}/releases/download/{tag}/{name}"
    if progress:
        progress(f"GitHub API 無法使用（{last_error}），改用直接下載：{direct}")
    return ReleaseAsset(tag=tag, name=name, url=direct, size=0, sha256="")


def _tag_from_release_page(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if "tag" in parts:
        idx = parts.index("tag")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, dest: Path, progress: ProgressFn | None = None, expected_size: int = 0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or expected_size or 0)
        copied = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            copied += len(chunk)
            if progress and total:
                pct = min(99, copied * 100 // total)
                progress(f"下載中 {pct}%（{copied // (1024 * 1024)} MB）")
            elif progress:
                progress(f"下載中 {copied // (1024 * 1024)} MB")
    if progress:
        progress("下載完成，正在核對檔案。")
    return dest


def install_setup(setup_path: Path, install_dir: Path | None = None, progress: ProgressFn | None = None) -> Path:
    target = install_dir or official_install_dir()
    target.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(f"正在安裝到 {target}")
    cmd = [
        str(setup_path),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/DIR={target}",
    ]
    completed = subprocess.run(cmd, check=False, timeout=600)
    if completed.returncode not in {0, None}:
        raise RuntimeError(f"安裝程式結束代碼 {completed.returncode}")
    exe = target / EXE_NAME
    if not exe.is_file():
        raise RuntimeError(f"安裝後找不到 {exe}")
    return exe


def download_and_install(
    release_page: str = CHECKMATE_RELEASE_PAGE,
    progress: ProgressFn | None = None,
) -> Path:
    asset = fetch_setup_asset(release_page, progress=progress)
    work = Path(tempfile.gettempdir()) / "TeacherDeskCheckMate"
    setup_path = work / asset.name
    download_file(asset.url, setup_path, progress=progress, expected_size=asset.size)
    if asset.sha256:
        actual = sha256_file(setup_path)
        if actual != asset.sha256:
            raise RuntimeError("安裝檔 SHA256 不符，已中止安裝。")
        if progress:
            progress("SHA256 核對通過。")
    return install_setup(setup_path, progress=progress)
