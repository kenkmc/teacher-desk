"""Read QR codes from an image without uploading it."""

from __future__ import annotations

from pathlib import Path

import zxingcpp
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener


IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif"})


def open_image(path: Path) -> Image.Image:
    """Load and orient one supported image for preview or QR decoding."""
    path = Path(path)
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("不支援此圖片格式。")
    if not path.is_file():
        raise FileNotFoundError(f"找不到圖片：{path}")
    register_heif_opener()
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def scan_qr_image(path: Path) -> list[str]:
    """Return the text from every valid QR code found in the image."""
    image = open_image(path)
    try:
        barcodes = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode)
        return [barcode.text for barcode in barcodes]
    finally:
        image.close()
