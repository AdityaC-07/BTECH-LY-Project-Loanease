# LoanEase KYC Verification Backend (FastAPI)

Standalone KYC OCR service for PAN and Aadhaar extraction.
Runs independently on port `8003` and does not modify frontend code.

## Stack

- Python 3.10+
- FastAPI
- rapidocr-onnxruntime
- opencv-python
- Pillow
- pypdfium2
- rapidfuzz
- python-multipart
- numpy

## Optional Roboflow field mapping

You can optionally enrich PAN extraction with Roboflow workflow detections.
This is an add-on and the backend works without it.

Set either:

- `ROBOFLOW_WORKFLOW_URL` (full workflow endpoint URL), or
- both `ROBOFLOW_WORKSPACE` and `ROBOFLOW_WORKFLOW_ID`

Also set:

- `ROBOFLOW_API_KEY`

When not configured (or if the call fails), the service automatically falls back to local OCR-only extraction.

## Install

### 1) Create and activate venv

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 2) Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3) OCR engine

OCR runs via `rapidocr-onnxruntime` (Python package only).
No system Tesseract installation, PATH setup, or language pack download is required.

### 4) PDF support

PDF processing is handled by `pypdfium2` and does not require Poppler.

## Run service

From `kyc_backend` directory:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8003
```

API docs:

- Swagger UI: `http://localhost:8003/docs`
- ReDoc: `http://localhost:8003/redoc`

## Endpoints

- `POST /kyc/extract/pan`
- `POST /kyc/extract/aadhaar`
- `POST /kyc/verify`
- `POST /kyc/extract/auto`
- `GET /health`

## Example curl commands

### Extract PAN

```bash
curl -X POST "http://localhost:8003/kyc/extract/pan" \
  -F "document=@./samples/pan.jpg" \
  -F "language=en"
```

### Extract Aadhaar

```bash
curl -X POST "http://localhost:8003/kyc/extract/aadhaar" \
  -F "document=@./samples/aadhaar.jpg"
```

### Verify both documents

```bash
curl -X POST "http://localhost:8003/kyc/verify" \
  -F "pan=@./samples/pan.jpg" \
  -F "aadhaar=@./samples/aadhaar.jpg"
```

### Auto-detect document type

```bash
curl -X POST "http://localhost:8003/kyc/extract/auto" \
  -F "document=@./samples/unknown_doc.png"
```

### Health check

```bash
curl "http://localhost:8003/health"
```

## How to test with sample PAN/Aadhaar images

1. Use clear, front-facing images with all text visible.
2. Try both image and PDF input.
3. Validate low-confidence behavior by testing blurry image samples.
4. Validate age checks with DOB values outside 21-65.
5. Validate name matching by using intentionally mismatched PAN/Aadhaar pairs.

## Add a new document type

1. Add detection keywords and regex in `app/extractors.py`.
2. Implement extraction parser function similar to `extract_pan` / `extract_aadhaar`.
3. Extend response schema in `app/schemas.py`.
4. Add endpoint logic in `app/main.py` and service wiring in `app/service.py`.
5. Add endpoint test commands in this README.

## Known limitations

- Handwritten text extraction quality is limited.
- Very low-resolution images reduce OCR confidence.
- Plastic card glare/reflections can break OCR.
- Address parsing is heuristic and may need tuning for edge formats.
- Aadhaar checksum is approximated with basic rule (`first digit not 0/1`) as requested.

## CORS

CORS is enabled for:

- `http://localhost:8080`
- `http://localhost:8081`
- `http://localhost:8082`
- `http://127.0.0.1:8080`
- `http://127.0.0.1:8081`
- `http://127.0.0.1:8082`
- `http://localhost:3000`
- `FRONTEND_DOMAIN` env variable (if provided)
