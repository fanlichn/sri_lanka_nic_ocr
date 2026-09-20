"""Image preprocessing helpers.

A single input image is turned into several candidate variants (original color,
contrast-enhanced grayscale, and binarized) which are all fed to the OCR engine.
The results are then merged, which improves robustness against varying lighting,
blur and low resolution.
"""
from __future__ import annotations

import cv2
import numpy as np


def load_image(buf: bytes) -> np.ndarray:
    """Decode an in-memory image buffer to a BGR ``np.ndarray``."""
    arr = np.frombuffer(buf, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cannot decode image; expected JPEG/PNG/WebP etc.")
    return img


def _ensure_min_size(img: np.ndarray, min_side: int = 1200) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min_side / min(h, w)
    if scale > 1.0:
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return img


def _estimate_skew(gray: np.ndarray) -> float:
    """Estimate the dominant text skew angle (degrees)."""
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) < 200:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    return angle if abs(angle) <= 30 else 0.0


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.3:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def build_variants(img: np.ndarray) -> list[dict]:
    """Return ``[{"name": ..., "img": ndarray}, ...]`` candidates for OCR."""
    img = _ensure_min_size(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    angle = _estimate_skew(gray)

    color = _rotate(img, angle)
    gray = _rotate(gray, angle)

    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    binarized = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )

    return [
        {"name": "color", "img": color},
        {"name": "enhanced", "img": enhanced},
        {"name": "binarized", "img": binarized},
    ]
