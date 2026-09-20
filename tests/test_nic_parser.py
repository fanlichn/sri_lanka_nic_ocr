"""Unit tests for NIC number parsing.

Run with:  pytest -q
"""
from app.nic_parser import parse_nic


def test_old_nic_male_literal():
    info = parse_nic("912680444V")
    assert info.valid
    assert info.nic_type == "old"
    assert info.gender == "male"
    assert info.birth_year == 1991
    assert info.is_voter is True
    # literal day-of-year: day 268 in 1991 (non-leap) -> Sep 25
    assert info.birth_date == "1991-09-25"


def test_old_nic_male_nic366():
    # 366-day calendar correction recovers the real DOB (one day earlier).
    info = parse_nic("912680444V", day_mode="nic366")
    assert info.birth_date == "1991-09-24"


def test_old_nic_female():
    info = parse_nic("855010567V")
    assert info.valid
    assert info.gender == "female"
    assert info.birth_date == "1985-01-01"


def test_old_nic_non_voter():
    info = parse_nic("900012345X")
    assert info.is_voter is False


def test_new_nic_male():
    info = parse_nic("198512345678")
    assert info.valid
    assert info.nic_type == "new"
    assert info.gender == "male"
    assert info.birth_year == 1985
    assert info.birth_date == "1985-05-03"


def test_new_nic_female_nic366():
    info = parse_nic("199253600001", day_mode="nic366")
    assert info.gender == "female"
    assert info.birth_year == 1992


def test_nic366_non_leap_after_march():
    # day code 080 in 1999 (non-leap) -> real DOB Mar 20
    info = parse_nic("199908012345", day_mode="nic366")
    assert info.birth_date == "1999-03-20"


def test_invalid_format():
    info = parse_nic("ABCDE")
    assert not info.valid
    assert info.reason == "invalid format"


def test_normalization():
    info = parse_nic(" 912680444 v ")
    assert info.valid
    assert info.normalized == "912680444V"


def test_old_nic_8_digit_missing_check():
    info = parse_nic("84575796")
    assert info.valid
    assert info.nic_type == "old"
    assert info.gender == "female"
    assert info.check_digit is None
    assert info.reason and "missing check digit" in info.reason


def test_new_nic_nic366_matches_printed_dob():
    info = parse_nic("198227210059", day_mode="nic366")
    assert info.birth_date == "1982-09-28"
