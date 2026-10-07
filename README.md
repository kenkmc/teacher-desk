# 課務台

本機優先的教師課務軟件套件（Python 3.10+、PySide6）。左側選單可擴充，可掛入現有的 Python 選擇題批改軟件。原有 `teacher_desk` Python 模組與資料庫路徑保留，以兼容舊版本。

## 功能（MVP）

- 組別與學生：組別可跨班；每位學生填班別。匯入 Excel／CSV（欄位：班別、學號、中文姓名、英文姓名）
- 時間表與提醒：匯入圖片、PDF、Excel、Word 時間表；核對及編輯辨識結果，設定每週課堂提醒
- 檔案格式轉換：同一頁面批次把 Word 轉 PDF、HEIC／HEIF／WebP 圖片轉 JPG／PNG、HEVC／H.265／MOV 影片轉 MP4
- QR 二維碼掃描：從 PNG、JPG、HEIC、WebP、BMP 或 TIFF 圖片辨識多個 QR Code，查看及複製內容
- PDF 工具：合併、逐頁調整順序、旋轉、擷取、分拆及加入頁碼
- 課室座位表：講台與座位可拖移位置、學生拖放入座、鎖定後隨機、匯出 A4 PDF
- 選擇題批改：全磁碟搜尋 CheckMate；找不到則從 GitHub 發行頁下載並安裝
- 設定：切換繁體中文／英文介面，查看轉檔引擎與本機資料庫位置

學生與已儲存的時間表資料存在本機 SQLite。一般 OCR 和 Ollama 辨識在本機進行；選擇 NVIDIA 或 OpenRouter 雲端辨識時，所選圖片或 PDF 頁面會上傳至相應服務。

## 系統需求

- Windows 10/11（主要支援）
- Python 3.10 或以上（建議 3.11+）
- Word 轉 PDF：安裝 [LibreOffice](https://www.libreoffice.org/) 或 Microsoft Word
- 圖片及掃描 PDF 時間表：可安裝 [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) 及繁體中文（`chi_tra`）／英文（`eng`）語言資料；複雜版面可選用下述本機 AI
- 舊版 `.doc`／`.xls` 時間表：需要 LibreOffice 或 Microsoft Office

## 安裝與執行

### Windows 免安裝版本

下載 [TeacherDesk-0.9.1-Windows-x64.exe](https://github.com/kenkmc/teacher-desk/releases/download/v0.9.1/TeacherDesk-0.9.1-Windows-x64.exe) 後，在 Windows 10／11（64 位元）雙擊執行即可；不需要預先安裝 Python 或 Python 模組。這個版本內建繁體中文與英文介面，可在「設定」選擇語言並按「套用語言並重新啟動」。程式會自動重啟，語言選擇保存在本機，已儲存的資料不會清除。未儲存的輸入內容會在切換時清除。

免安裝版已連同英文和繁體中文 Tesseract OCR、HEIC 解碼器、FFmpeg 影片轉換器和本機 QR 解碼器打包。NVIDIA／OpenRouter 雲端辨識仍需要自行輸入 API key 和網絡連線。

按視窗右上角的 X 會將課務台收至 Windows 通知區，時間表提醒繼續運作。要完全退出並停止提醒，按左側底部的「完全結束程式」，或在通知區圖示選「結束課務台」。資料保存在 Windows 使用者的本機應用程式資料夾，不會因更新可執行檔而清除。

Word 轉 PDF、舊版 `.doc`／`.xls` 匯入仍需要電腦已有 Microsoft Word 或 LibreOffice；選擇題批改使用另一個獨立的 CheckMate 程式。

如需自行重建 Windows 版本，在已安裝 Python、專案依賴和 PyInstaller 的 Windows 電腦執行 `python scripts/build_windows.py`。若建置電腦有 `C:\Program Files\Tesseract-OCR`（包含 `eng`、`chi_tra`、`osd` 語言資料），腳本會把本機 OCR 一同打包；也可用 `TESSERACT_ROOT` 指定其他安裝路徑。英語介面文字由 `scripts/english_translations.py` 提供；時間表讀取仍支援中文原稿。

### 從原始碼執行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,word]"
kewutai
```

開發時也可：

```powershell
python -m pytest
```

VS Code：使用「Run 課務台」啟動設定，或執行工作「Run 課務台」。`python -m teacher_desk` 仍可使用。

## 檔案格式轉換

在左側選「檔案格式轉換」，再於「Word」、「圖片」或「影片」分頁加入一個或多個檔案；亦可從檔案總管拖放檔案到清單。預設把結果存入原檔旁的 `Converted` 資料夾，也可自行選擇或開啟輸出資料夾。進度和每個檔案的結果會在同一頁顯示。同名結果會自動加上編號，原檔和既有輸出檔不會被覆蓋。

- Word：`.doc`／`.docx` → `.pdf`。可加入資料夾及子資料夾；需要電腦安裝 LibreOffice 或 Microsoft Word。可在目前檔案完成後取消餘下轉換。
- 圖片：`.heic`／`.heif`／`.webp` → `.jpg` 或 `.png`。透明圖片轉 JPG 時會填白色背景；動態 WebP 只輸出首張影格，結果清單會提示。
- 影片：`.hevc`／`.h265` 原始影片及 `.mov` → `.mp4`，使用 H.264 影像與 AAC 音訊。原始 HEVC 沒有容器影格率資料，預設 30 FPS，可在轉換前調整。影片轉換期間可按「取消轉換」。

## QR 二維碼掃描

在左側選「QR 二維碼掃描」，按「匯入圖片並掃描」選擇圖片。程式會在本機讀取圖片上的 QR Code；如有多個，可在清單點選查看完整內容，再複製所選或全部內容。掃描結果不會自動開啟網址，也不會上傳圖片。

## 匯入名冊

Excel／CSV 第一列標題可為：`班別`、`學號`、`中文姓名`、`英文姓名`（英文 `class_name`、`student_no`、`chinese_name`／`name`、`english_name` 亦可）。可參考 `sample_data/students.csv`。

重新匯入同一組別時，程式會按學號更新現有學生並保留其座位；名冊未列出的學生會被移除。移除前會先顯示確認提示。

## 時間表與提醒

在「時間表與提醒」匯入 `.png`、`.jpg`、`.pdf`、`.xlsx`、`.xlsm`、`.xls`、`.docx` 或 `.doc`。列表式時間表可用「星期／開始／結束／科目／班別／課室」欄位；方格式時間表可在頂行放星期、首欄放 `08:30-09:15` 一類時段。圖片及掃描 PDF 可選一般 OCR、本機 AI 或雲端 AI 辨識；Excel／Word 仍會直接讀取文件資料。對有框線的每週時間表，程式會先偵測各日課堂格及合併課節，再讀取格內文字；PDF 若有可提取的時間文字，會優先使用原始時間。

如一般 OCR 未能讀好方格式時間表，可安裝 [Ollama](https://ollama.com/download)，並在命令列執行 `ollama pull qwen3-vl:2b`。在匯入前選「本機 AI（Ollama）」及模型 `qwen3-vl:2b`；模型在本機運行，首次下載約需數 GB 空間，CPU 辨識可能較慢。若已下載其他 Ollama 視覺模型，可在模型欄輸入其名稱。AI 只會輸出帶有明確開始及結束時間的項目；辨識結果仍須人工核對。

### 申請雲端 AI 平台與取得 API key

在程式的「時間表與提醒」頁，API key 欄旁也可按「如何申請及取得 API key？」查看這些步驟及開啟官方網站。

**OpenRouter** 透過單一 API 提供多種 AI 模型。本程式只接受免費模型；匯入圖片或掃描 PDF 時須選用支援圖片輸入的模型。

1. 在 [OpenRouter](https://openrouter.ai/) 建立帳戶或登入。
2. 打開官方 [API Keys 頁](https://openrouter.ai/settings/keys)，建立新的 API key，並立即複製保存。
3. 返回程式，選「雲端 AI（OpenRouter）」並把 key 貼到遮蔽欄位。詳見 [OpenRouter 官方入門說明](https://openrouter.ai/docs/quickstart)。

**NVIDIA API Catalog** 提供 Nemotron OCR v2 圖片文字辨識服務。

1. 開啟 [Nemotron OCR v2 模型頁](https://build.nvidia.com/nvidia/nemotron-ocr-v2)，按 **Get API Key**。
2. 登入或建立 NVIDIA 帳戶，依畫面提示取得並複製 key。
3. 返回程式，選「NVIDIA Nemotron OCR v2（雲端）」並貼上 key。詳見 [NVIDIA 官方申請教學](https://docs.api.nvidia.com/nim/re/docs/api-quickstart)。

兩個平台的使用額度、限速及費用可能改變，請以各平台顯示為準。不要把 key 放進公開文件或 GitHub；本程式只在執行期間把輸入的 key 保留於記憶體。

取得 NVIDIA API key 後，選「NVIDIA Nemotron OCR v2（雲端）」並匯入圖片或 PDF。OCR 文字會按辨識座標重組為時間表，請在預覽表核對後儲存。每個 PDF 頁面都會送至 NVIDIA 進行辨識；Excel 和 Word 則直接讀取檔案資料。

取得 OpenRouter API key 後，選「雲端 AI（OpenRouter）」並貼上 key。預設模型是 `google/gemma-4-31b-it:free`；亦可填入其他以 `:free` 結尾的視覺模型，或 `openrouter/free`。選用雲端辨識時，圖片及 PDF 頁面會送到 OpenRouter；PDF 每頁各用一次請求。免費模型有請求次數限制，模型供應及辨識品質可能變動。

匯入後會自動建立可編輯的時間表及提醒草稿，每項預設提前 10 分鐘提醒。文字擠疊而無法可靠辨識的格會標示「需核對」，並暫停該項提醒。請核對星期、時間和課堂名稱，必要時直接編輯或新增一列，最後按「儲存時間表及提醒」。按 X 後，課務台仍在系統通知區執行並顯示提醒；按左側底部「完全結束程式」或在通知區選擇「結束課務台」才會完全退出。電腦關機或程式完全退出時不會發出提醒。

## 加入其他軟件

1. 在 `src/teacher_desk/modules/` 新增資料夾與 `widget.py`（建構函式接受 `Database`）。
2. 於 `src/teacher_desk/modules/registry.py` 的 `available_modules()` 加入一個 `ModuleSpec`。
3. 若工具已是獨立 Python 程式，可仿 `mc_grader` 用選單啟動外部檔案。

## 注意

- 加密或 DRM 的 Word／PDF 無法處理。
- 舊版 `.doc` 的版面取決於 LibreOffice 或 Word。
- OCR 和 AI 可能因掃描品質或版面而讀錯、漏讀，AI 也可能猜測內容；儲存前請對照原稿核對星期、時間及課堂內容。
