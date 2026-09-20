"""FastAPI application for Sri Lanka NIC OCR."""
from __future__ import annotations

import base64
import binascii
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .config import get_settings
from .extractor import extract
from .ocr_engine import create_engine
from .preprocessing import build_variants, load_image
from .schemas import ExtractedResult

_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    settings = get_settings()
    _engine = create_engine(settings)
    # Warm up the model at startup so the first request is fast and
    # configuration/model-loading errors surface immediately.
    _engine.warmup()
    yield


app = FastAPI(
    title="Sri Lanka NIC OCR",
    description="识别斯里兰卡身份证（NIC）并抽取姓名、身份证号、出生日期、性别、地址等字段。",
    version="1.0.0",
    lifespan=lifespan,
)


class Base64Request(BaseModel):
    image_base64: str


def _recognize(buf: bytes) -> ExtractedResult:
    settings = get_settings()
    if len(buf) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="文件过大")
    t0 = time.perf_counter()
    img = load_image(buf)
    lines = []
    for variant in build_variants(img):
        lines.extend(_engine.recognize(variant["img"]))

    # Deduplicate identical text, keeping the highest-confidence occurrence.
    dedup = {}
    for ln in lines:
        key = ln.text.strip().lower()
        if not key:
            continue
        if key not in dedup or ln.confidence > dedup[key].confidence:
            dedup[key] = ln
    unique = sorted(dedup.values(), key=lambda l: l.confidence, reverse=True)

    result = extract(unique, settings)
    result.elapsed_ms = (time.perf_counter() - t0) * 1000
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ocr", response_model=ExtractedResult)
async def ocr(file: UploadFile = File(...)):
    buf = await file.read()
    return _recognize(buf)


@app.post("/ocr_base64", response_model=ExtractedResult)
async def ocr_base64(req: Base64Request):
    try:
        buf = base64.b64decode(req.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="无效的 base64 图片数据")
    return _recognize(buf)
