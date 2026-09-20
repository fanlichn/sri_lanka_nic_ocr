"""FastAPI application for Sri Lanka NIC OCR."""
from __future__ import annotations

import base64
import binascii
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .config import get_settings
from .extractor import extract
from .ocr_engine import create_engine, create_name_engine
from .preprocessing import build_variants, load_image
from .schemas import ExtractedResult
from .url_fetch import UrlFetchError, fetch_image_bytes

_engine = None
_name_engine = None  # 多语言姓名第二引擎（僧伽罗语/泰米尔语），可为 None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _name_engine
    settings = get_settings()
    _engine = create_engine(settings)
    # Warm up the model at startup so the first request is fast and
    # configuration/model-loading errors surface immediately.
    _engine.warmup()
    # 第二引擎可选：tesseract 未安装 / 缺语言包时降级，不影响主流程
    _name_engine, name_err = create_name_engine(settings)
    if name_err:
        logging.warning("多语言姓名第二引擎未启用: %s", name_err)
    yield


app = FastAPI(
    title="Sri Lanka NIC OCR",
    description="识别斯里兰卡身份证（NIC）并抽取姓名、身份证号、出生日期、性别、地址等字段。",
    version="1.0.0",
    lifespan=lifespan,
)


class Base64Request(BaseModel):
    image_base64: str


class UrlRequest(BaseModel):
    image_url: str


def _recognize(buf: bytes) -> ExtractedResult:
    settings = get_settings()
    if len(buf) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="文件过大")
    t0 = time.perf_counter()
    img = load_image(buf)
    lines = []
    color_img = None
    for variant in build_variants(img):
        lines.extend(_engine.recognize(variant["img"]))
        if variant["name"] == "color":
            color_img = variant["img"]

    # 第二引擎仅在纠偏后的原图上跑一次，识别僧伽罗语/泰米尔语姓名；
    # 识别失败时仅记录日志，不阻断主流程。
    secondary_lines = None
    if _name_engine is not None and color_img is not None:
        try:
            secondary_lines = _name_engine.recognize(color_img)
        except Exception as exc:
            logging.warning("多语言姓名第二引擎识别失败: %s", exc)

    # Deduplicate identical text, keeping the highest-confidence occurrence.
    dedup = {}
    for ln in lines:
        key = ln.text.strip().lower()
        if not key:
            continue
        if key not in dedup or ln.confidence > dedup[key].confidence:
            dedup[key] = ln
    unique = sorted(dedup.values(), key=lambda l: l.confidence, reverse=True)

    result = extract(unique, settings, secondary_lines)
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


@app.post("/ocr_url", response_model=ExtractedResult)
def ocr_url(req: UrlRequest):
    """从图片 URL（OSS/S3/CDN 等公开链接）下载并识别。

    同步接口：下载与 OCR 均在线程池中执行，不阻塞事件循环。
    """
    try:
        buf = fetch_image_bytes(req.image_url, get_settings())
    except UrlFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _recognize(buf)
