"""Optional local vision-model extraction for photographed timetables."""

from __future__ import annotations

import base64
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps


DEFAULT_MODEL = "qwen3-vl:2b"
DEFAULT_OPENROUTER_MODEL = "google/gemma-4-31b-it:free"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
NVIDIA_OCR_URL = "https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2"
NVIDIA_POLL_URL = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/"

ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "weekday": {"type": "integer", "minimum": 0, "maximum": 6},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "title": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["weekday", "start_time", "end_time", "title", "location"],
            },
        }
    },
    "required": ["entries"],
}

PROMPT = (
    "Read this teacher's weekly timetable. Return every class or administrative event "
    "with an explicitly printed start and end time. Weekday is 0 for Monday through 6 "
    "for Sunday. Keep Traditional Chinese names exactly as printed. "
    "Combine subject and class in title; put a room in location. "
    "For a grid, use the column's weekday and row's time range for each nonempty cell. "
    "Do not invent missing times, subjects, or rooms. Omit uncertain entries. "
    "Return JSON only with an entries array. Each entry has weekday, start_time, "
    "end_time, title, and location. Times must be HH:MM in 24-hour format."
)


def _image_bytes(path: Path) -> bytes:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((3200, 3200), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def recognize_image(path: Path, model: str = DEFAULT_MODEL) -> list[dict[str, object]]:
    """Use only the local Ollama server; no timetable bytes leave this computer."""
    if not model.strip():
        raise ValueError("請輸入本機 Ollama 視覺模型名稱")
    body = json.dumps({
        "model": model.strip(),
        "messages": [{
            "role": "user",
            "content": PROMPT,
            "images": [base64.b64encode(_image_bytes(path)).decode("ascii")],
        }],
        "format": ENTRY_SCHEMA,
        "options": {"temperature": 0},
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_CHAT_URL, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        # Ignore system proxy settings so this request can only reach the loopback server.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=300) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except (UnicodeError, ValueError):
            detail = ""
        if exc.code == 404:
            raise RuntimeError(f"找不到本機模型 {model}。請先執行 ollama pull {model}") from exc
        raise RuntimeError(f"本機 Ollama 辨識失敗（{exc.code}）：{detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("無法連接本機 Ollama。請先安裝並啟動 Ollama，再下載視覺模型。") from exc
    try:
        entries = json.loads(result["message"]["content"])["entries"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("視覺模型沒有回傳可讀取的時間表資料") from exc
    if not isinstance(entries, list):
        raise RuntimeError("視覺模型沒有回傳可讀取的時間表資料")
    return [entry for entry in entries if isinstance(entry, dict)]


def recognize_image_openrouter(
    path: Path, api_key: str, model: str = DEFAULT_OPENROUTER_MODEL,
) -> list[dict[str, object]]:
    """Send one image to a free OpenRouter vision model on explicit user selection."""
    api_key = api_key.strip()
    model = model.strip()
    if not api_key:
        raise ValueError("請先輸入 OpenRouter API key")
    if not (model.endswith(":free") or model == "openrouter/free"):
        raise ValueError("請選用 OpenRouter 免費模型（名稱以 :free 結尾）或 openrouter/free")
    encoded = base64.b64encode(_image_bytes(path)).decode("ascii")
    body = json.dumps({
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ],
        }],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 4096,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("OpenRouter API key 無效或沒有使用此模型的權限") from exc
        if exc.code == 429:
            raise RuntimeError("OpenRouter 免費模型已達請求限額，請稍後再試") from exc
        if exc.code == 402:
            raise RuntimeError("OpenRouter 拒絕免費請求；請檢查模型名稱及帳戶額度") from exc
        try:
            error = json.loads(exc.read().decode("utf-8")).get("error", {})
            detail = error.get("message", "") if isinstance(error, dict) else str(error)
        except (UnicodeError, ValueError):
            detail = ""
        raise RuntimeError(f"OpenRouter 辨識失敗（{exc.code}）：{detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("無法連接 OpenRouter；請檢查網絡後重試") from exc
    try:
        entries = json.loads(result["choices"][0]["message"]["content"])["entries"]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("OpenRouter 模型沒有回傳可讀取的時間表資料") from exc
    if not isinstance(entries, list):
        raise RuntimeError("OpenRouter 模型沒有回傳可讀取的時間表資料")
    return [entry for entry in entries if isinstance(entry, dict)]


def recognize_image_nvidia(path: Path, api_key: str) -> list[dict[str, object]]:
    """Return OCR words and normalized positions from NVIDIA Nemotron OCR v2."""
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("請先輸入 NVIDIA API key")
    encoded = base64.b64encode(_image_bytes(path)).decode("ascii")
    body = json.dumps({
        "input": [{"type": "image_url", "url": f"data:image/png;base64,{encoded}"}],
        "merge_levels": ["word"],
    }).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    request = urllib.request.Request(NVIDIA_OCR_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            status = getattr(response, "status", 200)
            request_id = response.headers.get("NVCF-REQID") if status == 202 else None
            result = json.load(response) if status != 202 else None
        for _ in range(20):
            if status != 202:
                break
            if not request_id:
                raise RuntimeError("NVIDIA 正在處理圖片，但未提供查詢編號")
            time.sleep(3)
            poll = urllib.request.Request(NVIDIA_POLL_URL + request_id, headers=headers)
            with urllib.request.urlopen(poll, timeout=30) as response:
                status = getattr(response, "status", 200)
                result = json.load(response) if status != 202 else None
        if status == 202:
            raise RuntimeError("NVIDIA OCR 處理逾時，請稍後重試")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("NVIDIA API key 無效或沒有 Nemotron OCR v2 使用權限") from exc
        if exc.code == 402:
            raise RuntimeError("NVIDIA 帳戶額度不足，請檢查帳戶") from exc
        if exc.code == 429:
            raise RuntimeError("NVIDIA OCR 已達請求限額，請稍後再試") from exc
        if exc.code == 413:
            raise RuntimeError("圖片太大，請先縮小檔案再試") from exc
        raise RuntimeError(f"NVIDIA OCR 辨識失敗（{exc.code}）") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("無法連接 NVIDIA OCR；請檢查網絡後重試") from exc
    try:
        detections = result["data"][0]["text_detections"]
    except (IndexError, KeyError, TypeError) as exc:
        raise RuntimeError("NVIDIA OCR 沒有回傳可讀取的文字") from exc
    if not isinstance(detections, list):
        raise RuntimeError("NVIDIA OCR 沒有回傳可讀取的文字")
    words = []
    for detection in detections:
        try:
            prediction = detection["text_prediction"]
            word = prediction["text"].strip()
            points = detection["bounding_box"]["points"]
            x = sum(float(point["x"]) for point in points) / len(points)
            y = sum(float(point["y"]) for point in points) / len(points)
        except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
            continue
        if word and 0 <= x <= 1 and 0 <= y <= 1:
            words.append({"text": word, "x": x, "y": y})
    return words
