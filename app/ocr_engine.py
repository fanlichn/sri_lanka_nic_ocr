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


class TesseractNameEngine:
    """多语言姓名第二引擎：Tesseract（sin/tam）识别僧伽罗语/泰米尔语文本。

    与主引擎相互独立（主引擎保持 PaddleOCR 不变），仅用于补充识别
    主引擎不支持的非拉丁文字，结果按 Unicode 脚本分类填充姓名字段。
    """

    def __init__(self, settings):
        self._lang = settings.name_ocr_lang or "sin+tam"
        self._psm = settings.name_tesseract_psm
        self._cmd = settings.tesseract_cmd or None

    def _pytesseract(self):
        import pytesseract

        if self._cmd:
            pytesseract.pytesseract.tesseract_cmd = self._cmd
        return pytesseract

    def warmup(self):
        """校验 tesseract 可执行文件与语言包是否可用，缺失时抛异常。"""
        pytesseract = self._pytesseract()
        pytesseract.get_tesseract_version()
        installed = set(pytesseract.get_languages(config=""))
        missing = [l for l in self._lang.split("+") if l and l not in installed]
        if missing:
            raise RuntimeError(
                "Tesseract 缺少语言包: "
                + ", ".join(missing)
                + "（安装: apt install "
                + " ".join(f"tesseract-ocr-{l}" for l in missing)
                + "）"
            )

    def recognize(self, image) -> List[OcrLine]:
        pytesseract = self._pytesseract()
        data = pytesseract.image_to_data(
            image,
            lang=self._lang,
            config=f"--psm {self._psm}",
            output_type=pytesseract.Output.DICT,
        )
        # 按 (block, paragraph, line) 把词聚合成行，取行级外接矩形
        groups: dict = {}
        for i in range(len(data["text"])):
            text = (data["text"][i] or "").strip()
            if not text or int(data["conf"][i]) < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            groups.setdefault(key, []).append(
                (
                    data["left"][i], data["top"][i],
                    data["width"][i], data["height"][i],
                    float(data["conf"][i]), text,
                )
            )
        lines: List[OcrLine] = []
        for words in groups.values():
            words.sort(key=lambda w: w[0])
            left = min(w[0] for w in words)
            top = min(w[1] for w in words)
            right = max(w[0] + w[2] for w in words)
            bottom = max(w[1] + w[3] for w in words)
            conf = sum(w[4] for w in words) / len(words) / 100.0
            lines.append(
                OcrLine(
                    text=" ".join(w[5] for w in words),
                    confidence=conf,
                    box=[[left, top], [right, top], [right, bottom], [left, bottom]],
                )
            )
        return lines


def create_engine(settings):
    if settings.ocr_engine == "tesseract":
        return TesseractOcrEngine(settings)
    return PaddleOcrEngine(settings)


def create_name_engine(settings):
    """创建多语言姓名第二引擎，返回 ``(engine | None, error | None)``。

    永不抛异常：tesseract 未安装 / 缺语言包时返回 ``(None, 原因)``，
    由调用方降级处理（记录日志，主流程不受影响）。
    """
    name = (settings.name_ocr_engine or "none").strip().lower()
    if name in ("", "none", "off", "false"):
        return None, None
    if name == "tesseract":
        try:
            engine = TesseractNameEngine(settings)
            engine.warmup()
            return engine, None
        except Exception as exc:  # tesseract 未安装 / 缺语言包
            return None, str(exc)
    return None, f"未知的多语言姓名引擎: {settings.name_ocr_engine}"
