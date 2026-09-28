from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from teacher_desk import __version__
from teacher_desk.db import Database
from teacher_desk.edition import IS_BILINGUAL, IS_ENGLISH
from teacher_desk.language import current_language, load_language, set_language


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    english_smoke_test = "--self-test-english" in args
    bilingual_smoke_test = "--self-test-bilingual" in args
    smoke_test = "--self-test" in args or english_smoke_test or bilingual_smoke_test
    app = QApplication.instance() or QApplication([args[0]] if smoke_test else args)
    # Keep the internal name so existing local database paths remain unchanged.
    app.setApplicationName("Teacher Desk")
    app.setOrganizationName("TeacherDesk")
    database = Database()
    set_language(load_language(database) if IS_BILINGUAL else "en" if IS_ENGLISH else "zh")
    app.setApplicationDisplayName("課務台")
    app.setApplicationVersion(__version__)
    font = QFont(app.font())
    if font.pointSize() <= 0:
        font.setPointSize(10)
        app.setFont(font)
    from teacher_desk.ui.main_window import MainWindow

    window = MainWindow(database)
    if smoke_test:
        import subprocess

        from pillow_heif import register_heif_opener
        import zxingcpp

        from teacher_desk.services.file_conversion import find_ffmpeg

        if bilingual_smoke_test:
            from teacher_desk.modules.registry import available_modules

            if not IS_BILINGUAL:
                raise RuntimeError("The bilingual edition was not bundled correctly.")
            previous = current_language()
            set_language("en")
            if available_modules()[0].title != "Groups and students":
                raise RuntimeError("English UI strings are missing from the bilingual edition.")
            set_language("zh")
            if available_modules()[0].title != "組別與學生":
                raise RuntimeError("Chinese UI strings are missing from the bilingual edition.")
            set_language(previous)
        if english_smoke_test and not IS_ENGLISH:
            raise RuntimeError("The English edition was not bundled correctly.")
        if IS_ENGLISH and window.modules[0].title != "Groups and students":
            raise RuntimeError("The English UI was not bundled correctly.")
        register_heif_opener()
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            raise RuntimeError("FFmpeg is missing from the application.")
        subprocess.run([str(ffmpeg), "-version"], capture_output=True, timeout=15, check=True)
        qr_text = "Teacher Desk QR self-test"
        qr = zxingcpp.create_barcode(qr_text, zxingcpp.BarcodeFormat.QRCode)
        decoded = zxingcpp.read_barcodes(qr.to_image(scale=4), formats=zxingcpp.BarcodeFormat.QRCode)
        if len(decoded) != 1 or decoded[0].text != qr_text:
            raise RuntimeError("QR decoder failed the packaged application self-test.")
        window._quit_application()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
