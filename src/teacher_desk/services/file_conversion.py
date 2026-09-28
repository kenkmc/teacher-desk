"""Local image and video conversions used by the file conversion screen."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

from PIL import Image, ImageOps


IMAGE_INPUTS = frozenset({".heic", ".heif", ".webp"})
VIDEO_INPUTS = frozenset({".hevc", ".h265", ".mov"})
IMAGE_OUTPUTS = frozenset({".jpg", ".png"})


def next_output_path(source: Path, output_dir: Path, suffix: str) -> Path:
    """Choose a free filename without changing or replacing the source."""
    if suffix.lower() not in IMAGE_OUTPUTS | {".mp4", ".pdf"}:
        raise ValueError(f"不支援的輸出格式：{suffix}")
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / f"{source.stem}{suffix}"
    number = 2
    while candidate.exists() or candidate.resolve() == source.resolve():
        candidate = output_dir / f"{source.stem} ({number}){suffix}"
        number += 1
    return candidate


def temporary_output_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.stem}-{uuid.uuid4().hex}.tmp{destination.suffix}")


def finish_output(temporary: Path, destination: Path) -> None:
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError("轉換沒有產生有效檔案。")
    if destination.exists():
        raise FileExistsError(f"輸出檔已存在：{destination.name}")
    temporary.rename(destination)


def convert_image(source: Path, destination: Path) -> str:
    """Save the first still image as JPEG or PNG; return a frame warning, if any."""
    if source.suffix.lower() not in IMAGE_INPUTS:
        raise ValueError(f"不支援的圖片格式：{source.suffix}")
    if destination.suffix.lower() not in IMAGE_OUTPUTS:
        raise ValueError(f"不支援的圖片輸出格式：{destination.suffix}")
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() or destination.resolve() == source.resolve():
        raise FileExistsError(f"輸出檔已存在：{destination}")

    if source.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener

        register_heif_opener()

    temporary = temporary_output_path(destination)
    try:
        with Image.open(source) as original:
            frame_count = getattr(original, "n_frames", 1)
            original.seek(0)
            image = ImageOps.exif_transpose(original)
            icc_profile = image.info.get("icc_profile")
            exif = image.getexif()
            save_options: dict[str, object] = {}
            if icc_profile:
                save_options["icc_profile"] = icc_profile
            if exif:
                save_options["exif"] = exif.tobytes()

            if destination.suffix.lower() == ".jpg":
                if "A" in image.getbands() or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGB", rgba.size, "white")
                    flattened.paste(rgba, mask=rgba.getchannel("A"))
                    image = flattened
                else:
                    image = image.convert("RGB")
                image.save(temporary, format="JPEG", quality=92, subsampling=0, **save_options)
            else:
                image.save(temporary, format="PNG", **save_options)
        finish_output(temporary, destination)
        return "動態圖片只輸出首張影格" if frame_count > 1 else ""
    finally:
        temporary.unlink(missing_ok=True)


def find_ffmpeg() -> Path | None:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = sorted((Path(bundle_root) / "ffmpeg").glob("ffmpeg*.exe"))
        if bundled:
            return bundled[0]
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        executable = Path(get_ffmpeg_exe())
        return executable if executable.is_file() else None
    except (ImportError, RuntimeError):
        return None


def video_command(source: Path, temporary: Path, ffmpeg: Path, raw_fps: int = 30) -> list[str]:
    if source.suffix.lower() not in VIDEO_INPUTS:
        raise ValueError(f"不支援的影片格式：{source.suffix}")
    if temporary.suffix.lower() != ".mp4":
        raise ValueError("影片輸出必須是 MP4。")
    if not 1 <= raw_fps <= 120:
        raise ValueError("HEVC 影格率須介乎 1 至 120 FPS。")
    command = [str(ffmpeg), "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error", "-progress", "pipe:1"]
    if source.suffix.lower() in {".hevc", ".h265"}:
        command.extend(["-r", str(raw_fps)])
    command.extend([
        "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-n", str(temporary),
    ])
    return command


def convert_video(source: Path, destination: Path, raw_fps: int = 30) -> None:
    """Synchronous conversion used by checks; the UI runs the same command asynchronously."""
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() or destination.resolve() == source.resolve():
        raise FileExistsError(f"輸出檔已存在：{destination}")
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("找不到 FFmpeg 影片轉換程式。")
    temporary = temporary_output_path(destination)
    try:
        result = subprocess.run(video_command(source, temporary, ffmpeg, raw_fps), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[-1500:] or "FFmpeg 轉換失敗。")
        finish_output(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
