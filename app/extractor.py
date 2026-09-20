"""Field extraction from OCR lines.

Strategy: locate the NIC number via format rules (with common digit/letter
confusion correction), then use label-based matching for name / date of birth /
address / gender / date of issue. The printed date of birth is preferred when
available; the NIC-decoded date acts as a fallback and cross-check.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from .nic_parser import NicInfo, parse_nic
from .ocr_engine import OcrLine
from .schemas import ExtractedResult, NicOut, OcrLineOut

# Common OCR confusions on digit positions of the NIC number.
_DIGIT_MAP = str.maketrans(
    {
        "O": "0", "o": "0", "Q": "0", "D": "0",
        "I": "1", "l": "1", "L": "1", "|": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "G": "6",
        "T": "7",
        "B": "8",
        "F": "8",
    }
)

_NAME_LABELS = ["full name", "name", "nama", "name in full"]
_DOB_LABELS = ["date of birth", "birth date", "dob", "birthday"]
_ADDRESS_LABELS = ["address", "permanent address", "present address", "residence"]
_GENDER_LABELS = ["sex", "gender"]
_ISSUE_LABELS = ["date of issue", "issued on", "issue date", "issued date"]

_DATE_FULL = [
    re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)"),
    # 年份首位被 OCR 丢掉，如 "997.12-25" -> 1997-12-25
    re.compile(r"(?<!\d)(\d{3})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)"),
]


def _line_center_y(box) -> float:
    ys = [p[1] for p in box]
    return sum(ys) / len(ys)


def _normalize_date(s: str) -> Optional[str]:
    for pat in _DATE_FULL:
        m = pat.search(s)
        if not m:
            continue
        g = m.groups()
        if len(g[0]) == 4:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
        elif len(g[0]) == 3:
            y, mo, d = 1000 + int(g[0]), int(g[1]), int(g[2])
        else:
            d, mo, y = int(g[0]), int(g[1]), int(g[2])
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def _find_nic(lines: List[OcrLine]) -> tuple[Optional[str], Optional[str]]:
    """Return ``(nic_number, note)``.

    ``note`` is a non-empty warning when the match was lenient (OCR confusion
    correction applied, or a check digit / V-X letter appears to be missing).
    """
    ordered = sorted(lines, key=lambda l: l.confidence, reverse=True)
    for ln in ordered:
        # 1) token-level match (preferred)
        for tok in re.findall(r"[0-9A-Za-z]+", ln.text):
            if len(tok) < 8 or sum(c.isdigit() for c in tok) < 5:
                continue
            if re.fullmatch(r"\d{12}", tok):
                return tok, None
            if re.fullmatch(r"[0-9A-Za-z]{12}", tok):
                d = tok.translate(_DIGIT_MAP)
                if d.isdigit():
                    return d, "已应用 OCR 数字纠错"
            if re.fullmatch(r"[0-9A-Za-z]{9}[VXvx]", tok):
                d = tok[:9].translate(_DIGIT_MAP)
                if d.isdigit():
                    return d + tok[9].upper(), None
            if re.fullmatch(r"[0-9A-Za-z]{8}[VXvx]", tok):
                d = tok[:8].translate(_DIGIT_MAP)
                if d.isdigit():
                    return d + tok[8].upper(), "可能缺少校验位"
            if re.fullmatch(r"[0-9A-Za-z]{9}", tok):
                d = tok.translate(_DIGIT_MAP)
                if d.isdigit():
                    return d, "末尾 V/X 字母可能被 OCR 遗漏"
            if re.fullmatch(r"[0-9A-Za-z]{8}", tok):
                d = tok.translate(_DIGIT_MAP)
                if d.isdigit():
                    return d, "可能缺少校验位与末尾字母"
        # 2) whole-line scan (number split by spaces, e.g. "85542015 V")
        compact = re.sub(r"[^0-9A-Za-z]", "", ln.text)
        m = re.search(r"(\d{12})", compact)
        if m:
            return m.group(1), None
        m = re.search(r"([0-9A-Za-z]{9})([VXvx])", compact)
        if m:
            d = m.group(1).translate(_DIGIT_MAP)
            if d.isdigit():
                return d + m.group(2).upper(), None
        m = re.search(r"([0-9A-Za-z]{8})([VXvx])", compact)
        if m:
            d = m.group(1).translate(_DIGIT_MAP)
            if d.isdigit():
                return d + m.group(2).upper(), "可能缺少校验位"
    return None, None


def _value_after_label(line_text: str, labels: List[str]) -> Optional[str]:
    for lbl in labels:
        m = re.search(re.escape(lbl) + r"\s*[:：]?\s*(.+)", line_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip(" .:：-")
            if val:
                return val
    return None


def _value_from_line_below(
    idx: int, lines: List[OcrLine], label_line: OcrLine
) -> Optional[str]:
    base_y = _line_center_y(label_line.box)
    base_x = label_line.box[0][0]
    best: Optional[tuple] = None
    for j, other in enumerate(lines):
        if j == idx:
            continue
        y = _line_center_y(other.box)
        x = other.box[0][0]
        if y > base_y + 2 and abs(x - base_x) < 150:
            if best is None or y < best[0]:
                best = (y, other.text.strip())
    return best[1] if best else None


def _extract_label(lines: List[OcrLine], labels: List[str]) -> Optional[str]:
    # 1) inline value after the label (e.g. "Date of Birth : 1992-02-05")
    for i, ln in enumerate(lines):
        val = _value_after_label(ln.text, labels)
        if val:
            return val
    # 2) label on its own line, value on the line below
    for i, ln in enumerate(lines):
        t = ln.text.strip().strip(":：. ").lower()
        if any(t == lbl.lower() for lbl in labels):
            val = _value_from_line_below(i, lines, ln)
            if val:
                return val
    return None


def _find_date_anywhere(lines: List[OcrLine]) -> Optional[str]:
    """Fallback: scan all lines for any date-like string."""
    for ln in lines:
        d = _normalize_date(ln.text)
        if d:
            return d
    return None


def _normalize_gender(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    t = s.strip().lower()
    if t in ("m", "male", "l", "laki"):
        return "male"
    if t in ("f", "female", "p"):
        return "female"
    return None


def extract(lines: List[OcrLine], settings) -> ExtractedResult:
    warnings: List[str] = []

    nic_text, nic_note = _find_nic(lines)
    nic_info: Optional[NicInfo] = None
    if nic_text:
        nic_info = parse_nic(
            nic_text,
            day_mode=settings.nic_day_mode,
            old_century=settings.old_nic_century,
        )
        if not nic_info.valid:
            warnings.append(f"NIC 号码格式可疑: {nic_text}" + (f" ({nic_info.reason})" if nic_info.reason else ""))
        elif nic_note:
            warnings.append(f"NIC 号码({nic_text}) {nic_note}，请人工复核")

    name = _extract_label(lines, _NAME_LABELS)
    dob_printed = _extract_label(lines, _DOB_LABELS)
    gender_printed = _normalize_gender(_extract_label(lines, _GENDER_LABELS))
    address = _extract_label(lines, _ADDRESS_LABELS)
    issue_date = _extract_label(lines, _ISSUE_LABELS)

    dob_iso = _normalize_date(dob_printed) if dob_printed else None
    if not dob_iso:
        dob_iso = _find_date_anywhere(lines)
    gender = gender_printed or (nic_info.gender if nic_info and nic_info.gender != "unknown" else None)

    # Cross-check: decoded DOB vs printed DOB.
    if dob_iso and nic_info and nic_info.birth_date and dob_iso != nic_info.birth_date:
        warnings.append(
            f"印刷出生日期({dob_iso})与 NIC 号码解码({nic_info.birth_date})不一致"
        )

    nic_out = None
    if nic_info:
        nic_out = NicOut(
            valid=nic_info.valid,
            normalized=nic_info.normalized,
            nic_type=nic_info.nic_type,
            birth_year=nic_info.birth_year,
            gender=nic_info.gender,
            birth_date=nic_info.birth_date,
            is_voter=nic_info.is_voter,
            serial=nic_info.serial,
            check_digit=nic_info.check_digit,
            reason=nic_info.reason,
        )

    success = bool(nic_text and nic_info and nic_info.valid)

    return ExtractedResult(
        success=success,
        nic_number=nic_text,
        nic=nic_out,
        name=name,
        date_of_birth=dob_iso or (nic_info.birth_date if nic_info else None),
        gender=gender,
        address=address,
        date_of_issue=issue_date,
        lines=[
            OcrLineOut(text=l.text, confidence=l.confidence, box=l.box) for l in lines
        ],
        warnings=warnings,
    )
