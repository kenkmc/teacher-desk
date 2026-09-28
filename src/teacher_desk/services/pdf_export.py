from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from teacher_desk.services.seating import RoomLayout

_FONT_REGISTERED = False
FONT_NAME = "TeacherDeskSans"


def _register_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return FONT_NAME
    candidates = [
        Path(r"C:\Windows\Fonts\msjh.ttc"),
        Path(r"C:\Windows\Fonts\msjh.ttf"),
        Path(r"C:\Windows\Fonts\mingliu.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            subfont = 0 if path.suffix.lower() == ".ttc" else 0
            try:
                pdfmetrics.registerFont(TTFont(FONT_NAME, str(path), subfontIndex=subfont))
                _FONT_REGISTERED = True
                return FONT_NAME
            except Exception:  # noqa: BLE001
                continue
    _FONT_REGISTERED = True
    return "Helvetica"


def export_seating_pdf(
    output: Path,
    class_name: str,
    layout_name: str,
    layout: RoomLayout,
    labels: dict[int, str],
) -> None:
    font = _register_font()
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    pdf.setFont(font, 16)
    pdf.drawString(20 * mm, height - 18 * mm, f"{class_name}　座位表")
    pdf.setFont(font, 11)
    pdf.drawString(20 * mm, height - 26 * mm, f"配置：{layout_name}")
    margin_x = 15 * mm
    margin_top = 34 * mm
    usable_w = width - 2 * margin_x
    usable_h = height - margin_top - 16 * mm
    boxes = [(layout.podium.x, layout.podium.y, layout.podium.w, layout.podium.h)]
    boxes.extend((seat.x, seat.y, seat.w, seat.h) for seat in layout.seats)
    max_x = max((x + w for x, _y, w, _h in boxes), default=1)
    max_y = max((y + h for _x, y, _w, h in boxes), default=1)
    scale = min(usable_w / max(max_x, 1), usable_h / max(max_y, 1))

    def draw_box(x: int, y: int, w: int, h: int, text: str, fill: bool = False) -> None:
        px = margin_x + x * scale
        py = height - margin_top - (y + h) * scale
        pw = max(w * scale, 8)
        ph = max(h * scale, 8)
        if fill:
            pdf.setFillColorRGB(0.11, 0.21, 0.34)
            pdf.rect(px, py, pw, ph, fill=1, stroke=1)
            pdf.setFillColorRGB(1, 1, 1)
        else:
            pdf.setFillColorRGB(0, 0, 0)
            pdf.rect(px, py, pw, ph, fill=0, stroke=1)
        pdf.setFont(font, 8 if ph >= 28 else 7)
        cleaned = (text or "空").replace("\n", "  ")
        pdf.drawCentredString(px + pw / 2, py + ph / 2 - 3, cleaned)

    draw_box(layout.podium.x, layout.podium.y, layout.podium.w, layout.podium.h, "講台", fill=True)
    pdf.setFillColorRGB(0, 0, 0)
    for seat in layout.seats:
        label = labels.get(seat.student_id, "") if seat.student_id else ""
        draw_box(seat.x, seat.y, seat.w, seat.h, label)
    pdf.save()
