from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bilingual_ui_switches_with_saved_language(tmp_path: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_bilingual.py")], check=True)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = os.pathsep.join([
        str(ROOT / "build" / "bilingual-src"),
        str(ROOT / "tmp" / "build-packages"),
        *(path for path in sys.path if path and "site-packages" in path),
    ])
    code = textwrap.dedent("""
        from pathlib import Path
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication, QLabel
        from teacher_desk.db import Database
        from teacher_desk.language import LANGUAGE_SETTING, load_language, set_language
        from teacher_desk.modules.timetable.widget import ApiKeyHelpDialog
        from teacher_desk.services.timetable_import import parse_timetable_text
        from teacher_desk.ui.main_window import MainWindow

        app = QApplication([])
        app.setApplicationName('Teacher Desk')
        app.setOrganizationName('TeacherDesk')
        database = Database(Path(__import__('sys').argv[1]))
        set_language('zh')
        chinese = MainWindow(database)
        assert chinese.modules[0].title == '組別與學生'
        chinese_help = ApiKeyHelpDialog(chinese)
        assert chinese_help.windowTitle() == '申請雲端 AI 與取得 API key'
        chinese_help.close()
        database.set_setting(LANGUAGE_SETTING, 'en')
        set_language(load_language(database))
        english = MainWindow(database)
        assert english.modules[0].title == 'Groups and students'
        assert english.quit_button.text() == 'Exit application'
        settings = english.stack.widget(english.stack.count() - 1)
        assert settings.language_box.itemText(0) == 'Traditional Chinese'
        assert settings.apply_language_button.text() == 'Apply language and restart'
        timetable = english.stack.widget(1)
        assert timetable.api_key_help_button.text() == 'How to get an API key'
        help_dialog = ApiKeyHelpDialog(english)
        assert help_dialog.windowTitle() == 'Sign up for cloud AI and get an API key'
        help_labels = help_dialog.findChildren(QLabel)
        assert any('Sign in to OpenRouter' in label.text() for label in help_labels)
        assert any('Get API Key' in label.text() for label in help_labels)
        links = [label for label in help_labels if label.openExternalLinks()]
        assert any('https://openrouter.ai/settings/keys' in label.text() for label in links)
        assert any('https://build.nvidia.com/nvidia/nemotron-ocr-v2' in label.text() for label in links)
        help_dialog.close()
        timetable.ocr_method.setCurrentIndex(timetable.ocr_method.findData('standard'))
        assert timetable.api_key_help_button.isHidden()
        timetable.ocr_method.setCurrentIndex(timetable.ocr_method.findData('nvidia'))
        assert not timetable.api_key_help_button.isHidden()
        timetable._add_blank_row()
        assert timetable.table.cellWidget(0, 0).itemText(0) == 'Monday'
        assert parse_timetable_text('星期一 08:30-09:15 1A 中文 201室')
        chinese._quit_application()
        settings.language_box.setCurrentIndex(settings.language_box.findData('zh'))
        with patch('teacher_desk.modules.settings.widget.restart_application', return_value=True) as restart:
            settings.apply_language_button.click()
            restart.assert_called_once_with()
        assert database.get_setting(LANGUAGE_SETTING) == 'zh'
        set_language(load_language(database))
        reopened = MainWindow(database)
        assert reopened.modules[0].title == '組別與學生'
        assert reopened.stack.widget(reopened.stack.count() - 1).language_box.currentData() == 'zh'
        reopened._quit_application()
    """)
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "language.sqlite3")],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
