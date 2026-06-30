"""Tests for normalization functions."""

import pytest

from src.normalize.phones import normalize_phone, phones_are_equivalent
from src.normalize.dates import normalize_date, normalize_year, date_is_valid_range
from src.normalize.location import normalize_country, parse_location_string
from src.normalize.skills import normalize_skill, skills_are_duplicate


class TestPhones:
    def test_indian_number_no_code(self):
        assert normalize_phone("9876543210", "IN") == "+919876543210"

    def test_already_e164(self):
        assert normalize_phone("+919876543210") == "+919876543210"

    def test_us_number_with_spaces(self):
        assert normalize_phone("+1 415 555 2671") == "+14155552671"

    def test_us_paren_format_with_in_default(self):
        assert normalize_phone("(415) 555-2671", "IN") == "+14155552671"

    def test_uk_number_with_country_code(self):
        assert normalize_phone("+44 7911 123456") == "+447911123456"

    def test_garbage_returns_none(self):
        assert normalize_phone("call me") is None

    def test_too_short_returns_none(self):
        assert normalize_phone("555") is None

    def test_empty_returns_none(self):
        assert normalize_phone("") is None

    def test_equivalent_different_format(self):
        assert phones_are_equivalent("9876543210", "+919876543210", "IN") is True

    def test_different_numbers_not_equivalent(self):
        assert phones_are_equivalent("+919876543210", "+919876543211", "IN") is False


    def test_china_alias(self):
        assert normalize_country("中国") == "CN"
        result = parse_location_string("北京, 中国")
        assert result["country"] == "CN"
        assert result["city"] == "北京"


class TestPersonName:
    def test_collapse_internal_whitespace(self):
        from src.utils.helpers import normalize_person_name

        assert normalize_person_name("  Tarun   Khanna  ") == "Tarun Khanna"

    def test_single_word_unchanged(self):
        from src.utils.helpers import normalize_person_name

        assert normalize_person_name("Nandini") == "Nandini"


class TestDates:
    def test_iso_format(self):
        assert normalize_date("2020-01") == "2020-01"

    def test_month_abbrev(self):
        assert normalize_date("Jan 2020") == "2020-01"

    def test_full_month_name(self):
        assert normalize_date("January 2020") == "2020-01"

    def test_year_only(self):
        assert normalize_date("2020") == "2020-01"

    def test_present_returns_none(self):
        assert normalize_date("Present") is None

    def test_current_returns_none(self):
        assert normalize_date("current") is None

    def test_garbage_returns_none(self):
        assert normalize_date("some time ago") is None

    def test_valid_range(self):
        assert date_is_valid_range("2020-01", "2022-06") is True

    def test_invalid_range(self):
        assert date_is_valid_range("2022-06", "2020-01") is False

    def test_open_range(self):
        assert date_is_valid_range("2020-01", None) is True

    def test_year_extraction(self):
        assert normalize_year("Graduated in 2019") == "2019"


class TestLocation:
    def test_country_name(self):
        assert normalize_country("India") == "IN"

    def test_alpha2_passthrough(self):
        assert normalize_country("IN") == "IN"

    def test_usa_alias(self):
        assert normalize_country("USA") == "US"

    def test_uk_alias(self):
        assert normalize_country("UK") == "GB"

    def test_unknown_returns_none(self):
        assert normalize_country("Narnia") is None

    def test_three_part_location(self):
        result = parse_location_string("Bangalore, Karnataka, India")
        assert result["city"] == "Bangalore"
        assert result["country"] == "IN"

    def test_two_part_city_country(self):
        result = parse_location_string("Mumbai, India")
        assert result["city"] == "Mumbai"
        assert result["country"] == "IN"

    def test_country_only(self):
        result = parse_location_string("India")
        assert result["country"] == "IN"
        assert result["city"] is None


class TestSkills:
    def test_synonym_maps_to_canonical(self):
        assert normalize_skill("ReactJS") == "React"

    def test_case_insensitive(self):
        assert normalize_skill("python") == "Python"

    def test_js_maps_to_javascript(self):
        assert normalize_skill("JS") == "JavaScript"

    def test_unknown_skill_preserved(self):
        result = normalize_skill("SomeMadeUpLanguage2024")
        assert result is not None
        assert len(result) > 0

    def test_duplicates_detected(self):
        assert skills_are_duplicate("ReactJS", "React") is True

    def test_different_skills_not_duplicate(self):
        assert skills_are_duplicate("Python", "Java") is False
