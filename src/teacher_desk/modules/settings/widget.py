from __future__ import annotations

from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from teacher_desk.db import Database
from teacher_desk.edition import IS_BILINGUAL
from teacher_desk.language import LANGUAGE_SETTING, load_language, restart_application
from teacher_desk.services.timetable_import import find_tesseract
from teacher_desk.services.word_convert import detect_engine, word_com_available, which_soffice


class SettingsWidget(QWidget):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.engine_label = QLabel()
        self.db_label = QLabel()
        self.ocr_label = QLabel()
        self.language_box = QComboBox()
        self.apply_language_button = QPushButton("套用語言並重新啟動")
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        if IS_BILINGUAL:
            layout.addWidget(QLabel("介面語言"))
            language_row = QHBoxLayout()
            self.language_box.addItem("繁體中文", "zh")
            self.language_box.addItem("English", "en")
            language_row.addWidget(self.language_box, 1)
            self.apply_language_button.clicked.connect(self._apply_language)
            language_row.addWidget(self.apply_language_button)
            layout.addLayout(language_row)
            language_hint = QLabel("選擇語言後按套用；程式會自動重新啟動。未儲存的輸入內容會清除，已儲存資料不受影響。")
            language_hint.setWordWrap(True)
            layout.addWidget(language_hint)
        layout.addWidget(QLabel("本機狀態"))
        layout.addWidget(self.engine_label)
        layout.addWidget(self.ocr_label)
        layout.addWidget(self.db_label)
        layout.addWidget(QLabel("新增模組：在 src/teacher_desk/modules 新增資料夾，並於 registry.py 註冊 ModuleSpec。"))
        layout.addStretch()

    def refresh(self) -> None:
        if IS_BILINGUAL:
            self.language_box.setCurrentIndex(self.language_box.findData(load_language(self.database)))
        engine = detect_engine()
        soffice = which_soffice()
        lines = [
            f"LibreOffice：{'找到 ' + str(soffice) if soffice else '未安裝'}",
            f"Microsoft Word COM：{'可用' if word_com_available() else '不可用'}",
            f"目前引擎：{engine.name if engine else '無'}",
        ]
        self.engine_label.setText("\n".join(lines))
        ocr = find_tesseract()
        self.ocr_label.setText(f"時間表 OCR：{ocr if ocr else '未安裝 Tesseract'}")
        self.db_label.setText(f"資料庫：{self.database.path}")

    def _apply_language(self) -> None:
        if not IS_BILINGUAL:
            return
        selected = str(self.language_box.currentData())
        previous = load_language(self.database)
        if selected == previous:
            return
        self.database.set_setting(LANGUAGE_SETTING, selected)
        if not restart_application():
            self.database.set_setting(LANGUAGE_SETTING, previous)
            QMessageBox.warning(self, "介面語言", "無法重新啟動程式，語言設定沒有更改。")
            return
        window = self.window()
        if hasattr(window, "_quit_application"):
            window._quit_application()
        else:
            QApplication.instance().quit()
