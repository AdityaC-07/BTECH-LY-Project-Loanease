from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import cv2

from app.preprocess import load_document_rgb, run_ocr


def _extract_predictions(payload: object) -> list[dict]:
    if isinstance(payload, list):
        preds: list[dict] = []
        for item in payload:
            preds.extend(_extract_predictions(item))
        return preds

    if isinstance(payload, dict):
        if "predictions" in payload and isinstance(payload["predictions"], list):
            return [p for p in payload["predictions"] if isinstance(p, dict)]

        preds: list[dict] = []
        for value in payload.values():
            preds.extend(_extract_predictions(value))
        return preds

    return []


def _class_name(pred: dict) -> str:
    return str(pred.get("class") or pred.get("label") or "").strip().lower()


def _crop_from_prediction(image, pred: dict):
    h, w = image.shape[:2]

    if all(k in pred for k in ("x", "y", "width", "height")):
        cx = float(pred["x"])
        cy = float(pred["y"])
        bw = float(pred["width"])
        bh = float(pred["height"])
        x1 = int(max(0, cx - bw / 2))
        y1 = int(max(0, cy - bh / 2))
        x2 = int(min(w, cx + bw / 2))
        y2 = int(min(h, cy + bh / 2))
    elif all(k in pred for k in ("x1", "y1", "x2", "y2")):
        x1 = int(max(0, float(pred["x1"])))
        y1 = int(max(0, float(pred["y1"])))
        x2 = int(min(w, float(pred["x2"])))
        y2 = int(min(h, float(pred["y2"])))
    else:
        return None

    if x2 <= x1 or y2 <= y1:
        return None

    return image[y1:y2, x1:x2]


def _ocr_crop(crop) -> tuple[str, float]:
    if crop is None or crop.size == 0:
        return "", 0.0

    # Enlarge tiny crops for better OCR readability.
    if crop.shape[1] < 220:
        scale = 220 / max(1, crop.shape[1])
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    text, conf = run_ocr(crop)
    text = " ".join(text.split())
    return text, conf


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _append_api_key(url: str, api_key: str) -> str:
    if not api_key:
        return url

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "api_key" not in query:
        query["api_key"] = api_key

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


def _build_candidate_urls(custom_url: str, workspace: str, workflow_id: str) -> list[str]:
    candidates: list[str] = []

    if custom_url:
        candidates.append(custom_url)

    if workspace and workflow_id:
        candidates.extend(
            [
                f"https://serverless.roboflow.com/{workspace}/workflows/{workflow_id}",
                f"https://serverless.roboflow.com/workflows/{workspace}/{workflow_id}",
                f"https://serverless.roboflow.com/{workspace}/{workflow_id}",
            ]
        )

    # Preserve order while removing duplicates.
    seen = set()
    unique: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _encode_multipart(file_bytes: bytes, filename: str) -> tuple[bytes, str]:
    boundary = f"----LoanEaseBoundary{uuid.uuid4().hex}"
    crlf = "\r\n"

    parts = [
        f"--{boundary}",
        'Content-Disposition: form-data; name="confidence"',
        "",
        "0.1",
        f"--{boundary}",
        f'Content-Disposition: form-data; name="image"; filename="{filename}"',
        f"Content-Type: {_guess_mime(filename)}",
        "",
    ]

    body = crlf.join(parts).encode("utf-8") + crlf.encode("utf-8")
    body += file_bytes + crlf.encode("utf-8")
    body += f"--{boundary}--{crlf}".encode("utf-8")

    return body, boundary


def _post_workflow(url: str, api_key: str, file_bytes: bytes, filename: str) -> dict | list | None:
    full_url = _append_api_key(url, api_key)
    body, boundary = _encode_multipart(file_bytes=file_bytes, filename=filename)

    request = Request(
        url=full_url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError):
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_pan_hints_with_roboflow(file_bytes: bytes, filename: str) -> dict | None:
    api_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
    workspace = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
    workflow_id = os.getenv("ROBOFLOW_WORKFLOW_ID", "").strip()
    workflow_url = os.getenv("ROBOFLOW_WORKFLOW_URL", "").strip()

    urls = _build_candidate_urls(workflow_url, workspace, workflow_id)
    if not urls:
        return None

    extension = Path(filename).suffix.lstrip(".") or "jpg"
    image = load_document_rgb(file_bytes, f".{extension}")

    response = None
    for url in urls:
        response = _post_workflow(url=url, api_key=api_key, file_bytes=file_bytes, filename=filename)
        if response is not None:
            break

    if response is None:
        return None

    predictions = _extract_predictions(response)
    if not predictions:
        return None

    hints = {
        "pan_number": None,
        "name": None,
        "fathers_name": None,
        "date_of_birth": None,
        "document_markers": set(),
        "avg_confidence": 0.0,
        "source": "roboflow",
    }

    conf_vals = []
    for pred in predictions:
        cls = _class_name(pred)
        crop = _crop_from_prediction(image, pred)
        text, conf = _ocr_crop(crop)
        if conf > 0:
            conf_vals.append(conf)

        if any(k in cls for k in ["pan", "pan number", "pan_number"]):
            if text:
                hints["pan_number"] = text
        elif cls == "name" or "name" in cls:
            if "father" in cls:
                if text:
                    hints["fathers_name"] = text
            elif text:
                hints["name"] = text
        elif any(k in cls for k in ["dob", "date of birth", "birth"]):
            if text:
                hints["date_of_birth"] = text
        elif any(k in cls for k in ["income logo", "income_tax", "emblem"]):
            hints["document_markers"].add(cls)

    if conf_vals:
        hints["avg_confidence"] = sum(conf_vals) / len(conf_vals)

    return hints
