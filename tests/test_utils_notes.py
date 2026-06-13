"""Tests for utils/notes.py — canonical notes key=value helpers."""
import pytest
from utils.notes import dump_notes, get_note_int, parse_notes, upsert_note


class TestParseNotes:
    def test_none_returns_empty_dict(self):
        assert parse_notes(None) == {}

    def test_empty_string_returns_empty_dict(self):
        assert parse_notes("") == {}

    def test_single_pair(self):
        assert parse_notes("max_devices=3") == {"max_devices": "3"}

    def test_multiple_pairs(self):
        result = parse_notes("plan_code=1m\nmax_devices=2\ntrial_used=true")
        assert result == {"plan_code": "1m", "max_devices": "2", "trial_used": "true"}

    def test_ignores_non_kv_lines(self):
        result = parse_notes("plan_code=1m\nsome raw note\nmax_devices=3")
        assert result == {"plan_code": "1m", "max_devices": "3"}

    def test_strips_whitespace_around_key_and_value(self):
        result = parse_notes("  plan_code = 1m  ")
        assert result == {"plan_code": "1m"}

    def test_value_may_contain_equals_sign(self):
        result = parse_notes("key=a=b")
        assert result == {"key": "a=b"}

    def test_ignores_blank_lines(self):
        result = parse_notes("plan_code=1m\n\nmax_devices=3\n")
        assert result == {"plan_code": "1m", "max_devices": "3"}

    def test_last_value_wins_on_duplicate_key(self):
        result = parse_notes("key=first\nkey=second")
        assert result["key"] == "second"


class TestDumpNotes:
    def test_empty_dict(self):
        assert dump_notes({}) == ""

    def test_single_pair(self):
        assert dump_notes({"key": "val"}) == "key=val"

    def test_multiple_pairs_joined_with_newline(self):
        result = dump_notes({"a": "1", "b": "2"})
        assert "a=1" in result
        assert "b=2" in result
        assert "\n" in result

    def test_roundtrip(self):
        original = {"plan_code": "3m", "max_devices": "2", "trial_used": "true"}
        assert parse_notes(dump_notes(original)) == original


class TestGetNoteInt:
    def test_returns_default_for_none_notes(self):
        assert get_note_int(None, "max_devices", 3) == 3

    def test_returns_default_for_missing_key(self):
        assert get_note_int("plan_code=1m", "max_devices", 5) == 5

    def test_parses_valid_positive_int(self):
        assert get_note_int("max_devices=7", "max_devices", 3) == 7

    def test_returns_default_for_zero(self):
        assert get_note_int("max_devices=0", "max_devices", 3) == 3

    def test_returns_default_for_negative(self):
        assert get_note_int("max_devices=-1", "max_devices", 3) == 3

    def test_returns_default_for_non_integer_value(self):
        assert get_note_int("max_devices=abc", "max_devices", 3) == 3

    def test_returns_default_for_empty_value(self):
        assert get_note_int("max_devices=", "max_devices", 3) == 3


class TestUpsertNote:
    def test_adds_new_key_to_empty_notes(self):
        result = parse_notes(upsert_note(None, "max_devices", "3"))
        assert result["max_devices"] == "3"

    def test_adds_new_key_preserving_existing(self):
        notes = "plan_code=1m"
        result = parse_notes(upsert_note(notes, "max_devices", "2"))
        assert result["plan_code"] == "1m"
        assert result["max_devices"] == "2"

    def test_updates_existing_key(self):
        notes = "max_devices=3"
        result = parse_notes(upsert_note(notes, "max_devices", "5"))
        assert result["max_devices"] == "5"

    def test_upsert_idempotent_when_same_value(self):
        notes = "max_devices=3"
        once = upsert_note(notes, "max_devices", "3")
        twice = upsert_note(once, "max_devices", "3")
        assert parse_notes(once) == parse_notes(twice)
