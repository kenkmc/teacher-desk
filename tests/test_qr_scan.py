from __future__ import annotations

from PIL import Image
from PySide6.QtWidgets import QApplication
import zxingcpp

from teacher_desk.db import Database
from teacher_desk.modules.qr_scan.widget import QrScanWidget
from teacher_desk.services.qr_scan import scan_qr_image


def qr_image(value: str) -> Image.Image:
    code = zxingcpp.create_barcode(value, zxingcpp.BarcodeFormat.QRCode)
    return Image.fromarray(code.to_image(scale=5)).convert("RGB")


def test_scans_multiple_codes_from_one_image(tmp_path) -> None:
    first = qr_image("https://example.org/class")
    second = qr_image("教師會議 15:30")
    canvas = Image.new("RGB", (first.width + second.width + 80, max(first.height, second.height) + 40), "white")
    canvas.paste(first, (20, 20))
    canvas.paste(second, (first.width + 60, 20))
    source = tmp_path / "codes.webp"
    canvas.save(source, format="WEBP", quality=100, lossless=True)

    assert set(scan_qr_image(source)) == {"https://example.org/class", "教師會議 15:30"}


def test_blank_image_returns_no_codes(tmp_path) -> None:
    source = tmp_path / "blank.png"
    Image.new("RGB", (200, 200), "white").save(source)
    assert scan_qr_image(source) == []


def test_widget_displays_and_copies_scanned_text(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "code.png"
    qr_image("https://example.org/qr?item=1").save(source)
    widget = QrScanWidget(Database(tmp_path / "desk.sqlite3"))

    widget.scan_path(source)
    assert widget.results == ["https://example.org/qr?item=1"]
    assert widget.detail.toPlainText() == "https://example.org/qr?item=1"
    widget.copy_button.click()
    assert app.clipboard().text() == "https://example.org/qr?item=1"
    widget.close()
