from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class PageNumberStyle:
    format: str = "{page} / {total}"
    skip_first: bool = False
    x_ratio: float = 0.5
    y_offset: float = 28.0


def merge_pdfs(sources: list[Path], output: Path) -> None:
    writer = PdfWriter()
    for source in sources:
        reader = PdfReader(str(source))
        if reader.is_encrypted:
            raise ValueError(f"加密檔無法處理：{source.name}")
        writer.append(reader)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def reorder_and_merge(
    page_refs: list[tuple[Path, int]], output: Path, rotations: list[int] | None = None
) -> None:
    """page_refs: (pdf path, zero-based page index)."""
    if rotations is None:
        rotations = [0] * len(page_refs)
    if len(rotations) != len(page_refs) or any(angle % 90 for angle in rotations):
        raise ValueError("旋轉角度必須與每頁對應，且為 90 度的倍數")
    if any(path.resolve() == output.resolve() for path, _ in page_refs):
        raise ValueError("輸出檔不可覆蓋來源 PDF")
    cache: dict[Path, PdfReader] = {}
    writer = PdfWriter()
    for (path, index), angle in zip(page_refs, rotations, strict=True):
        reader = cache.get(path)
        if reader is None:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise ValueError(f"加密檔無法處理：{path.name}")
            cache[path] = reader
        if index < 0 or index >= len(reader.pages):
            raise IndexError(f"{path.name} 沒有第 {index + 1} 頁")
        writer.add_page(reader.pages[index])
        if angle:
            writer.pages[-1].rotate(angle)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def split_pages(
    page_refs: list[tuple[Path, int]], output_dir: Path, rotations: list[int] | None = None
) -> list[Path]:
    """Export selected pages as individual PDFs without replacing existing files."""
    if rotations is None:
        rotations = [0] * len(page_refs)
    if len(rotations) != len(page_refs):
        raise ValueError("旋轉角度數量不符")
    outputs = [
        output_dir / f"{path.stem}-p{index + 1:03d}-{number:03d}.pdf"
        for number, (path, index) in enumerate(page_refs, start=1)
    ]
    existing = next((path for path in outputs if path.exists()), None)
    if existing:
        raise FileExistsError(f"檔案已存在：{existing}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for page_ref, output, angle in zip(page_refs, outputs, rotations, strict=True):
        reorder_and_merge([page_ref], output, [angle])
    return outputs


def add_page_numbers(source: Path, output: Path, style: PageNumberStyle | None = None) -> None:
    style = style or PageNumberStyle()
    reader = PdfReader(str(source))
    if reader.is_encrypted:
        raise ValueError("加密檔無法處理")
    writer = PdfWriter()
    total = len(reader.pages)
    for index, page in enumerate(reader.pages):
        writer.add_page(page)
        if style.skip_first and index == 0:
            continue
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        text = style.format.format(page=index + 1, total=total)
        overlay = BytesIO()
        pdf = canvas.Canvas(overlay, pagesize=(width, height))
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(width * style.x_ratio, style.y_offset, text)
        pdf.save()
        overlay.seek(0)
        overlay_page = PdfReader(overlay).pages[0]
        writer.pages[index].merge_page(overlay_page)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def pdf_page_count(path: Path) -> int:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError(f"加密檔無法處理：{path.name}")
    return len(reader.pages)


def expand_pdf_pages(path: Path) -> list[tuple[Path, int]]:
    return [(path, index) for index in range(pdf_page_count(path))]
