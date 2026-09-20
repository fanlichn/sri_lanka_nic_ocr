"""Sri Lanka National Identity Card (NIC) number parsing.

Supported formats
-----------------
* Old (pre-2016)  -> 9 digits + letter, e.g. ``912680444V``
  layout: ``YY DDD SSS C V/X``
  (8 digits + letter, i.e. missing the check digit, is also accepted)
* New (2016+)     -> 12 digits, e.g. ``198512345678``
  layout: ``YYYY DDD SSSS C``

Day-of-year code ``DDD``:
  001..366  -> male
  501..866  -> female (day code = actual day + 500)

Note: the check digit (``C``) algorithm is not publicly documented, so it is
carried through but not validated.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta

_OLD_RE = re.compile(r"^(\d{8,9})([vVxX])?$")
_NEW_RE = re.compile(r"^(\d{12})$")


@dataclass(frozen=True)
class NicInfo:
    valid: bool
    raw: str = ""
    normalized: str = ""
    nic_type: str = ""               # "old" | "new" | ""
    birth_year: int | None = None
    day_code: int | None = None
    gender: str = "unknown"          # "male" | "female" | "unknown"
    birth_date: str | None = None    # ISO "YYYY-MM-DD"
    is_voter: bool | None = None
    serial: str | None = None
    check_digit: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def day_code_to_date(year: int, day_code: int, mode: str = "literal") -> date | None:
    """Convert a NIC day-of-year code into a real ``datetime.date``.

    ``mode="literal"`` treats the code as a literal day-of-year (Jan 1 = day 001).

    ``mode="nic366"`` compensates for the fixed 366-day calendar used by the
    government ID scheme: a 29-February slot is reserved every year, so in a
    non-leap year the code is one higher than the real day-of-year for dates on
    or after 1 March. This mode recovers the real date of birth.
    """
    if day_code < 1 or day_code > 366:
        return None

    leap = _is_leap(year)

    if mode == "nic366":
        if not leap:
            if day_code == 60:
                return None  # reserved 29-Feb in a non-leap year
            if day_code > 60:
                return date(year, 1, 1) + timedelta(days=day_code - 2)
        return date(year, 1, 1) + timedelta(days=day_code - 1)

    # literal
    max_day = 366 if leap else 365
    if day_code > max_day:
        return None
    return date(year, 1, 1) + timedelta(days=day_code - 1)


def normalize_nic(text: str) -> str:
    """Strip spaces, dashes and dots; keep the trailing V/X letter."""
    if not text:
        return ""
    return (
        text.strip()
        .replace("-", "")
        .replace(" ", "")
        .replace(".", "")
        .replace("\u2013", "")
        .replace("\u2014", "")
        .upper()
    )


def parse_nic(nic: str, *, day_mode: str = "literal", old_century: int = 1900) -> NicInfo:
    raw = nic or ""
    norm = normalize_nic(raw)

    def fail(reason: str) -> NicInfo:
        return NicInfo(valid=False, raw=raw, normalized=norm, reason=reason)

    if not norm:
        return fail("empty")

    m_old = _OLD_RE.match(norm)
    if m_old:
        digits = m_old.group(1)
        letter = m_old.group(2).upper() if m_old.group(2) else None
        year = old_century + int(digits[0:2])
        ddd = int(digits[2:5])
        serial = digits[5:8]
        check = digits[8] if len(digits) == 9 else None
        return _build("old", norm, year, ddd, serial, check, letter, day_mode)

    m_new = _NEW_RE.match(norm)
    if m_new:
        digits = norm
        year = int(digits[0:4])
        ddd = int(digits[4:7])
        return _build("new", norm, year, ddd, digits[7:11], digits[11], None, day_mode)

    return fail("invalid format")


def _build(nic_type, norm, year, ddd, serial, check, letter, day_mode) -> NicInfo:
    # 367..500 is a reserved range with no valid encoding
    if 367 <= ddd <= 500:
        return NicInfo(
            valid=False, raw=norm, normalized=norm, nic_type=nic_type,
            birth_year=year, day_code=ddd, serial=serial, check_digit=check,
            reason="day code in reserved range 367-500",
        )

    gender = "female" if ddd > 500 else "male"
    effective = ddd - 500 if ddd > 500 else ddd
    dob = day_code_to_date(year, effective, mode=day_mode)
    is_voter = None if letter is None else (letter == "V")

    reasons = []
    if nic_type == "old" and check is None:
        reasons.append("missing check digit")
    if dob is None:
        reasons.append("day code out of range for birth year")

    return NicInfo(
        valid=dob is not None,
        raw=norm,
        normalized=norm,
        nic_type=nic_type,
        birth_year=year,
        day_code=ddd,
        gender=gender,
        birth_date=dob.isoformat() if dob else None,
        is_voter=is_voter,
        serial=serial,
        check_digit=check,
        reason="; ".join(reasons) or None,
    )
