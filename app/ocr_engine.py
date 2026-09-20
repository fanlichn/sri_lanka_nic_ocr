"""OCR engines.

A thin abstraction over PaddleOCR (default, production-recommended) with an
optional Tesseract fallback. Both expose ``recognize(image) -> list[OcrLine]``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: List[List[float]]


class PaddleOcrEngine:
    def __init__(self, settings):
        self._settings = settings
        self._ocr = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._ocr is None:
            with self._lock:
                if self._ocr is None:
                    from paddleocr import PaddleOCR

                    self._ocr = PaddleOCR(
                        use_angle_cls=self._settings.paddle_use_angle_cls,
                        lang=self._settings.ocr_lang,
                        use_gpu=self._settings.paddle_use_gpu,
                        show_log=False,
                    )
        return self._ocr

    def warmup(self):
        self._ensure()

    def recognize(self, image) -> List[OcrLine]:
        ocr = self._ensure()
        result = ocr.ocr(image, cls=self._settings.paddle_use_angle_cls)
        lines: List[OcrLine] = []
        for page in result or []:
            if not page:
                continue
            for item in page:
                box, (text, conf) = item[0], item[1]
                lines.append(OcrLine(text=text or "", confidence=float(conf), box=box))
        return lines


class TesseractOcrEngine:
    def __init__(self, settings):
        self._settings = settings

    def warmup(self):
        return None

    def recognize(self, image) -> List[OcrLine]:
        import pytesseract

        data = pytesseract.image_to_data(
            image, lang=self._settings.ocr_lang, output_type=pytesseract.Output.DICT
        )
        lines: List[OcrLine] = []
        for i in range(len(data["text"])):
            text = (data["text"][i] or "").strip()
            if not text or int(data["conf"][i]) < 0:
                continue
            x, y, w, h = (
                int(data["left"][i]),
                int(data["top"][i]),
                int(data["width"][i]),
                int(data["height"][i]),
            )
            box = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            lines.append(OcrLine(text=text, confidence=float(data["conf"][i]) / 100.0, box=box))
        return lines


def create_engine(settings):
    if settings.ocr_engine == "tesseract":
        return TesseractOcrEngine(settings)
    return PaddleOcrEngine(settings)
