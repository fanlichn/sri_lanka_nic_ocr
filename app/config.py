"""Application configuration.

All values can be overridden via environment variables prefixed with ``NIC_OCR_``
or via a ``.env`` file placed next to the application.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NIC_OCR_", extra="ignore")

    # ---- OCR engine ----
    # "paddle" (PP-OCR, recommended) or "tesseract"
    ocr_engine: str = "paddle"
    # PaddleOCR: "en"; Tesseract: "eng" (add "sin" for Sinhala if needed)
    ocr_lang: str = "en"
    paddle_use_gpu: bool = False
    paddle_use_angle_cls: bool = True

    # ---- NIC decoding ----
    # "literal": read day-of-year code literally (Jan 1 == day 001)
    # "nic366":  compensate the fixed 366-day calendar used by SL NICs
    #            (recovers real DOB for non-leap-year births on/after 1 Mar)
    nic_day_mode: str = "literal"
    old_nic_century: int = 1900

    # ---- HTTP server ----
    host: str = "0.0.0.0"
    port: int = 8000
    max_upload_bytes: int = 15 * 1024 * 1024  # 15 MB
    workers: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
