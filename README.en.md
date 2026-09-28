# Teacher Desk

Teacher Desk is a Windows desktop app for teaching administration and document tasks. You can switch between English and Traditional Chinese inside the app. It reads Chinese timetables and keeps class and student names exactly as entered.

## Download and use

Download [TeacherDesk-0.9.0-Windows-x64.exe](https://github.com/kenkmc/teacher-desk/releases/download/v0.9.0/TeacherDesk-0.9.0-Windows-x64.exe) and double-click it on Windows 10 or 11 (64-bit). Python and its modules are bundled. The app includes both English and Traditional Chinese. Open **Settings**, select **Interface language**, and click **Apply language and restart**. The app restarts automatically and remembers your choice. Saved data is preserved; unsaved inputs are cleared when switching.

Closing the window with **X** keeps reminders running in the system tray. Use **Exit application** in the sidebar, or **Exit Teacher Desk** in the tray menu, to stop the app completely.

## Main tools

- **Groups and students:** Manage groups and import an Excel/CSV roster.
- **Timetable and reminders:** Import an image, PDF, spreadsheet, or Word timetable. Review extracted lessons before saving weekly reminders. Cloud OCR uploads selected images or PDF pages to the chosen provider.
- **File conversion:** Convert Word documents to PDF, HEIC/WebP images to JPG/PNG, and HEVC/MOV video to MP4. Add files by button or drag and drop. Existing output files are preserved with numbered filenames.
- **QR code scanner:** Read one or more QR codes from an image locally and copy their contents. Links are not opened automatically.
- **PDF tools:** Merge, reorder, rotate, extract, split, and number pages.
- **Seating plan:** Arrange seats, assign students, and export a PDF.
- **Multiple-choice grading:** Find or install the separate CheckMate grader.

Word-to-PDF conversion and legacy `.doc`/`.xls` imports need Microsoft Office or LibreOffice installed. NVIDIA and OpenRouter recognition need your API key and an internet connection. The keys are kept in memory only.

## Build from source

Install the project dependencies and PyInstaller, then run `python scripts/build_windows.py` on Windows. The build creates a bilingual source copy using `scripts/english_translations.py`, packages it, and checks that both languages are available in the executable.
