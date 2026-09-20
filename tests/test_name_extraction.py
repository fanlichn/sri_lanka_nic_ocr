"""Tests for multi-line English name extraction (Plan A) and
multilingual (Sinhala/Tamil) name picking via the secondary engine."""
from __future__ import annotations

from types import SimpleNamespace

from app.extractor import (
    _find_full_name,
    _pick_script_name,
    _SINHALA_CLEAN_RE,
    _SINHALA_RE,
    _TAMIL_CLEAN_RE,
    _TAMIL_RE,
    _union_box,
)
from app.ocr_engine import OcrLine, create_name_engine


def _line(text: str, x: float, y: float, conf: float = 0.9, h: float = 40.0) -> OcrLine:
    box = [
        [x, y - h / 2],
        [x + len(text) * 18, y - h / 2],
        [x + len(text) * 18, y + h / 2],
        [x, y + h / 2],
    ]
    return OcrLine(text=text, confidence=conf, box=box)


def test_two_line_name_merged():
    """Mimics the real card: 'Name: A B C' + wrapped line 'D E' below."""
    lines = [
        _line("/@./N.:198428204320", 632, 220),
        _line("Name: BULATHWELLKANDURE GEDARA SAMPATH", 700, 748, conf=0.92),
        _line("KUMARA RATHNAYAKA", 850, 798, conf=0.98),
        _line("Sex: Male", 1107, 1010),
        _line("Date of Birth:1984/10/08", 1100, 1060),
    ]
    assert _find_full_name(lines)[0] == (
        "BULATHWELLKANDURE GEDARA SAMPATH KUMARA RATHNAYAKA"
    )


def test_single_line_name():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("Sex: Male", 700, 700),
    ]
    assert _find_full_name(lines)[0] == "SAMAN KUMARA"


def test_label_only_line_uses_value_below():
    lines = [
        _line("Name", 700, 400),
        _line("SAMAN KUMARA", 700, 455),
        _line("Sex: Male", 700, 700),
    ]
    assert _find_full_name(lines)[0] == "SAMAN KUMARA"


def test_non_name_line_below_not_merged():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("1984/10/08", 700, 455),
        _line("Sex: Male", 700, 700),
    ]
    assert _find_full_name(lines)[0] == "SAMAN KUMARA"


def test_far_below_line_not_merged():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("PERERA FERNANDO", 850, 700),  # too far below -> belongs elsewhere
    ]
    assert _find_full_name(lines)[0] == "SAMAN KUMARA"


def test_no_name_label():
    lines = [_line("Sex: Male", 700, 400)]
    assert _find_full_name(lines) == (None, None)


def test_name_anchor_box_covers_name_block():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("PERERA", 700, 455),
        _line("Sex: Male", 700, 700),
    ]
    name, anchor = _find_full_name(lines)
    assert name == "SAMAN KUMARA PERERA"
    assert anchor is not None
    top = min(p[1] for p in anchor)
    bottom = max(p[1] for p in anchor)
    assert top <= 380 and bottom >= 475  # covers label line + continuation line


# ---- 多语言姓名（第二引擎选取逻辑） ----


def _pick_from(secondary: list[OcrLine], anchor) -> tuple[str | None, str | None]:
    from app.extractor import _SINHALA_CLEAN_RE, _TAMIL_CLEAN_RE

    sinhala = _pick_script_name(secondary, anchor, _SINHALA_RE, _SINHALA_CLEAN_RE)
    tamil = _pick_script_name(secondary, anchor, _TAMIL_RE, _TAMIL_CLEAN_RE)
    return sinhala, tamil


def test_union_box():
    box = _union_box([[[10, 20], [30, 20], [30, 40], [10, 40]],
                      [[5, 35], [25, 35], [25, 60], [5, 60]]])
    assert box[0] == [5, 20] and box[2] == [30, 60]


def test_sinhala_name_picked_nearest_to_anchor():
    """卡片顶部还有「ශ්‍රී ලංකා」标语，应选离英文姓名最近的那一行。"""
    anchor = _find_full_name([_line("Name: SAMAN KUMARA", 700, 400)])[1]
    secondary = [
        _line("ශ්‍රී ලංකා", 600, 150),          # 顶部标语（僧伽罗语）
        _line("සමන් කුමාර", 700, 455),           # 紧邻英文姓名下方
        _line("Address: No 12, Kandy", 700, 700),  # 无僧伽罗语字符
    ]
    sinhala, tamil = _pick_from(secondary, anchor)
    assert sinhala == "සමන් කුමාර"
    assert tamil is None


def test_tamil_name_picked_nearest_to_anchor():
    anchor = _find_full_name([_line("Name: SAMAN KUMARA", 700, 400)])[1]
    secondary = [
        _line("இலங்கை", 600, 150),               # 顶部标语（泰米尔语）
        _line("சாமான் குமார", 700, 455),          # 紧邻英文姓名下方
    ]
    sinhala, tamil = _pick_from(secondary, anchor)
    assert tamil == "சாமான் குமார"
    assert sinhala is None


def test_mixed_script_line_is_cleaned():
    anchor = _find_full_name([_line("Name: SAMAN KUMARA", 700, 400)])[1]
    secondary = [_line("KUMARA9 සම්පත්", 700, 455)]
    sinhala, _ = _pick_from(secondary, anchor)
    assert sinhala == "සම්පත්"


def test_empty_secondary_returns_none():
    anchor = _find_full_name([_line("Name: SAMAN KUMARA", 700, 400)])[1]
    assert _pick_from([], anchor) == (None, None)


# ---- 第二引擎工厂 ----


def _settings(**kw):
    base = dict(
        name_ocr_engine="none",
        name_ocr_lang="sin+tam",
        name_tesseract_psm=6,
        tesseract_cmd=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_create_name_engine_disabled():
    engine, err = create_name_engine(_settings(name_ocr_engine="none"))
    assert engine is None and err is None


def test_create_name_engine_unknown():
    engine, err = create_name_engine(_settings(name_ocr_engine="bogus"))
    assert engine is None and err


def test_create_name_engine_tesseract_missing(monkeypatch):
    """tesseract 不可用时返回 (None, 原因) 而非抛异常。"""
    import sys
    import types as t

    fake = t.ModuleType("pytesseract")
    fake.get_tesseract_version = lambda: (_ for _ in ()).throw(RuntimeError("not found"))
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    engine, err = create_name_engine(_settings(name_ocr_engine="tesseract"))
    assert engine is None and err
