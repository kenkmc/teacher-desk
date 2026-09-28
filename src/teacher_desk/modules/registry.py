from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from teacher_desk.db import Database

WidgetFactory = Callable[[Database], QWidget]


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    title: str
    description: str
    factory: WidgetFactory
    group: str = "工具"


def available_modules() -> list[ModuleSpec]:
    from teacher_desk.modules.file_conversion.widget import FileConversionWidget
    from teacher_desk.modules.mc_grader.widget import McGraderPlaceholderWidget
    from teacher_desk.modules.pdf_tools.widget import PdfToolsWidget
    from teacher_desk.modules.qr_scan.widget import QrScanWidget
    from teacher_desk.modules.roster.widget import RosterWidget
    from teacher_desk.modules.seating.widget import SeatingWidget
    from teacher_desk.modules.settings.widget import SettingsWidget
    from teacher_desk.modules.timetable.widget import TimetableWidget

    return [
        ModuleSpec("roster", "組別與學生", "管理組別、每位學生班別、匯入 Excel／CSV 名冊", RosterWidget, "資料"),
        ModuleSpec("timetable", "時間表與提醒", "匯入時間表、核對辨識結果、設定每週提醒", TimetableWidget, "資料"),
        ModuleSpec("file_conversion", "檔案格式轉換", "Word 轉 PDF、HEIC／WebP 轉 JPG／PNG、HEVC／MOV 轉 MP4", FileConversionWidget, "檔案"),
        ModuleSpec("qr_scan", "QR 二維碼掃描", "從匯入圖片辨識一個或多個 QR Code 並複製內容", QrScanWidget, "檔案"),
        ModuleSpec("pdf_tools", "PDF 工具", "合併、旋轉、擷取、分拆頁面並加入頁碼", PdfToolsWidget, "檔案"),
        ModuleSpec("seating", "課室座位表", "拖放編排、隨機座位、匯出 PDF", SeatingWidget, "課室"),
        ModuleSpec("mc_grader", "選擇題批改", "全磁碟搜尋 CheckMate，找不到則下載安裝", McGraderPlaceholderWidget, "批改"),
        ModuleSpec("settings", "設定", "轉檔引擎與外部工具路徑", SettingsWidget, "系統"),
    ]
