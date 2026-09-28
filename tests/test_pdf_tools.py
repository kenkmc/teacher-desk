from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from teacher_desk.services.pdf_tools import (
    PageNumberStyle,
    add_page_numbers,
    expand_pdf_pages,
    merge_pdfs,
    pdf_page_count,
    reorder_and_merge,
    split_pages,
)


def _one_page_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)


def test_merge_and_page_count(tmp_path: Path) -> None:
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    _one_page_pdf(first)
    _one_page_pdf(second)
    merged = tmp_path / "merged.pdf"
    merge_pdfs([first, second], merged)
    assert pdf_page_count(merged) == 2


def test_add_page_numbers(tmp_path: Path) -> None:
    source = tmp_path / "src.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    with source.open("wb") as handle:
        writer.write(handle)
    output = tmp_path / "numbered.pdf"
    add_page_numbers(source, output, PageNumberStyle(skip_first=True))
    assert pdf_page_count(output) == 2


def test_expand_and_reorder_pages(tmp_path: Path) -> None:
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=210, height=210)
    with first.open("wb") as handle:
        writer.write(handle)
    _one_page_pdf(second)
    pages = expand_pdf_pages(first) + expand_pdf_pages(second)
    assert pages == [(first, 0), (first, 1), (second, 0)]
    output = tmp_path / "reordered.pdf"
    reorder_and_merge([pages[2], pages[1], pages[0]], output)
    assert pdf_page_count(output) == 3


def test_rotate_extract_and_split_pages(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.add_blank_page(width=250, height=350)
    with source.open("wb") as handle:
        writer.write(handle)

    extracted = tmp_path / "extracted.pdf"
    reorder_and_merge([(source, 1)], extracted, [90])
    page = PdfReader(str(extracted)).pages[0]
    assert len(PdfReader(str(extracted)).pages) == 1
    assert page.get("/Rotate") == 90

    outputs = split_pages([(source, 0), (source, 1)], tmp_path / "split", [0, 270])
    assert len(outputs) == 2
    assert [pdf_page_count(path) for path in outputs] == [1, 1]
    assert PdfReader(str(outputs[1])).pages[0].get("/Rotate") == 270
    with pytest.raises(FileExistsError):
        split_pages([(source, 0), (source, 1)], tmp_path / "split")
    with pytest.raises(ValueError, match="覆蓋"):
        reorder_and_merge([(source, 0)], source)
