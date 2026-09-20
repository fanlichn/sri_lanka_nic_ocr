"""Tests for multi-line English name extraction (Plan A)."""
from __future__ import annotations

from app.extractor import _find_full_name
from app.ocr_engine import OcrLine


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
    assert (
        _find_full_name(lines)
        == "BULATHWELLKANDURE GEDARA SAMPATH KUMARA RATHNAYAKA"
    )


def test_single_line_name():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("Sex: Male", 700, 700),
    ]
    assert _find_full_name(lines) == "SAMAN KUMARA"


def test_label_only_line_uses_value_below():
    lines = [
        _line("Name", 700, 400),
        _line("SAMAN KUMARA", 700, 455),
        _line("Sex: Male", 700, 700),
    ]
    assert _find_full_name(lines) == "SAMAN KUMARA"


def test_non_name_line_below_not_merged():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("1984/10/08", 700, 455),
        _line("Sex: Male", 700, 700),
    ]
    assert _find_full_name(lines) == "SAMAN KUMARA"


def test_far_below_line_not_merged():
    lines = [
        _line("Name: SAMAN KUMARA", 700, 400),
        _line("PERERA FERNANDO", 850, 700),  # too far below -> belongs elsewhere
    ]
    assert _find_full_name(lines) == "SAMAN KUMARA"


def test_no_name_label():
    lines = [_line("Sex: Male", 700, 400)]
    assert _find_full_name(lines) is None
