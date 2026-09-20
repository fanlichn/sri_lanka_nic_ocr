"""Pydantic response models."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class OcrLineOut(BaseModel):
    text: str
    confidence: float
    box: List[List[float]]


class NicOut(BaseModel):
    valid: bool
    normalized: Optional[str] = None
    nic_type: Optional[str] = None
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    is_voter: Optional[bool] = None
    serial: Optional[str] = None
    check_digit: Optional[str] = None
    reason: Optional[str] = None


class ExtractedResult(BaseModel):
    success: bool
    nic_number: Optional[str] = None
    nic: Optional[NicOut] = None
    name: Optional[str] = None
    # 多语言姓名占位字段：当前 OCR 引擎仅支持拉丁文字，
    # 僧伽罗语/泰米尔语姓名需多语言 OCR 支持（见 README「多语言姓名」）
    name_sinhala: Optional[str] = None
    name_tamil: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    date_of_issue: Optional[str] = None
    lines: List[OcrLineOut] = []
    warnings: List[str] = []
    elapsed_ms: float = 0.0
