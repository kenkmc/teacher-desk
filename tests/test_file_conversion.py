from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

from teacher_desk.db import Database
from teacher_desk.modules.file_conversion.widget import FileConversionWidget
from teacher_desk.services.file_conversion import (
    convert_image,
    convert_video,
    find_ffmpeg,
    next_output_path,
)


def test_webp_to_jpg_and_png_preserves_source_and_alpha(tmp_path: Path) -> None:
    source = tmp_path / "picture.webp"
    image = Image.new("RGBA", (16, 16), (255, 0, 0, 0))
    image.putpixel((8, 8), (0, 0, 255, 255))
    image.save(source, format="WEBP", lossless=True)
    original = source.read_bytes()

    jpeg = next_output_path(source, tmp_path, ".jpg")
    assert convert_image(source, jpeg) == ""
    with Image.open(jpeg) as result:
        assert result.mode == "RGB"
        assert result.getpixel((0, 0)) == (255, 255, 255)

    png = next_output_path(source, tmp_path, ".png")
    assert convert_image(source, png) == ""
    with Image.open(png) as result:
        assert result.getpixel((0, 0))[3] == 0
    assert source.read_bytes() == original
    assert next_output_path(source, tmp_path, ".jpg").name == "picture (2).jpg"


def test_heic_to_png_and_animated_webp_warning(tmp_path: Path) -> None:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    source = tmp_path / "photo.heic"
    Image.new("RGB", (16, 16), (25, 100, 200)).save(source, format="HEIF")
    destination = tmp_path / "photo.png"
    assert convert_image(source, destination) == ""
    with Image.open(destination) as image:
        assert image.size == (16, 16)

    animated = tmp_path / "animated.webp"
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    frames[0].save(animated, format="WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0)
    warning = convert_image(animated, tmp_path / "animated.png")
    assert "首張影格" in warning


def test_mov_and_raw_hevc_to_mp4(tmp_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    mov = tmp_path / "clip.mov"
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x64:rate=5", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-frames:v", "5", "-c:v", "mpeg4", "-c:a", "pcm_s16le", "-shortest", "-y", str(mov),
    ], check=True, capture_output=True)
    original_mov = mov.read_bytes()
    mp4 = tmp_path / "clip.mp4"
    convert_video(mov, mp4)
    assert mp4.is_file() and mp4.stat().st_size > 0
    probe = subprocess.run([str(ffmpeg), "-hide_banner", "-i", str(mp4), "-f", "null", "-"],
                           check=True, capture_output=True, text=True)
    assert "Video: h264" in probe.stderr and "Audio: aac" in probe.stderr
    assert mov.read_bytes() == original_mov

    raw = tmp_path / "raw.hevc"
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x64:rate=5", "-frames:v", "5", "-c:v", "libx265",
        "-x265-params", "log-level=error", "-f", "hevc", "-y", str(raw),
    ], check=True, capture_output=True)
    raw_mp4 = tmp_path / "raw.mp4"
    convert_video(raw, raw_mp4, raw_fps=5)
    assert raw_mp4.is_file() and raw_mp4.stat().st_size > 0

    app = QApplication.instance() or QApplication([])
    widget = FileConversionWidget(Database(tmp_path / "ui.sqlite3"))
    panel = widget.video_panel
    panel.add_paths([mov])
    panel._start()
    deadline = time.monotonic() + 30
    while panel.active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not panel.active
    assert panel.ok_count == 1, [panel.log.item(i).text() for i in range(panel.log.count())]
    assert (tmp_path / "Converted" / "clip.mp4").is_file()
