"""Tests for pure helper functions in handlers/admin.py."""
from datetime import datetime

import pytest

from handlers.admin import (
    dump_client_notes,
    format_client_card,
    format_history_rows,
    html_escape,
    parse_client_notes,
    split_admin_text,
)
from tests.conftest import make_client, make_history_row


class TestHtmlEscape:
    def test_none_returns_dash(self):
        assert html_escape(None) == "—"

    def test_escapes_lt_gt(self):
        result = html_escape("<script>")
        assert "<" not in result
        assert ">" not in result

    def test_escapes_ampersand(self):
        result = html_escape("a & b")
        assert "&amp;" in result

    def test_plain_string_unchanged(self):
        assert html_escape("hello world") == "hello world"

    def test_integer_converted(self):
        assert html_escape(42) == "42"


class TestParseClientNotes:
    def test_none_returns_empty(self):
        data, raw = parse_client_notes(None)
        assert data == {}
        assert raw == []

    def test_kv_lines_go_into_data(self):
        data, raw = parse_client_notes("plan_code=1m\nmax_devices=3")
        assert data == {"plan_code": "1m", "max_devices": "3"}
        assert raw == []

    def test_non_kv_lines_go_into_raw(self):
        data, raw = parse_client_notes("plan_code=1m\nsome annotation")
        assert data["plan_code"] == "1m"
        assert "some annotation" in raw

    def test_blank_lines_ignored(self):
        data, raw = parse_client_notes("\nplan_code=1m\n\n")
        assert "plan_code" in data
        assert raw == []


class TestDumpClientNotes:
    def test_empty_returns_none(self):
        assert dump_client_notes({}, []) is None

    def test_kv_pairs_sorted_by_key(self):
        result = dump_client_notes({"z": "1", "a": "2"}, [])
        lines = result.splitlines()
        assert lines[0].startswith("a=")
        assert lines[1].startswith("z=")

    def test_raw_lines_appended_after_kv(self):
        result = dump_client_notes({"key": "val"}, ["raw note"])
        lines = result.splitlines()
        assert lines[-1] == "raw note"

    def test_roundtrip_kv_only(self):
        original = {"plan_code": "3m", "max_devices": "2"}
        dumped = dump_client_notes(original, [])
        data, raw = parse_client_notes(dumped)
        assert data == original
        assert raw == []


class TestSplitAdminText:
    def test_short_text_returned_as_single_chunk(self):
        text = "Hello"
        assert split_admin_text(text) == [text]

    def test_text_exactly_at_limit_is_single_chunk(self):
        text = "x" * 3500
        assert len(split_admin_text(text, limit=3500)) == 1

    def test_text_over_limit_is_split(self):
        # Two paragraphs each 2000 chars, limit=3500 → must split into 2
        block = "x" * 2000
        text = f"{block}\n\n{block}"
        chunks = split_admin_text(text, limit=3500)
        assert len(chunks) == 2

    def test_all_content_preserved_after_split(self):
        block = "A" * 2000
        text = f"{block}\n\n{block}"
        chunks = split_admin_text(text, limit=3500)
        combined = "".join(chunks)
        assert combined.count("A") == 4000

    def test_very_long_single_block_hard_split(self):
        text = "x" * 10000
        chunks = split_admin_text(text, limit=3500)
        for chunk in chunks:
            assert len(chunk) <= 3500


class TestFormatClientCard:
    def test_contains_client_id(self):
        client = make_client(id=42)
        card = format_client_card(client)
        assert "42" in card

    def test_contains_telegram_id(self):
        client = make_client(telegram_id="987654321")
        card = format_client_card(client)
        assert "987654321" in card

    def test_active_client_shows_yes(self):
        client = make_client(is_active=True)
        card = format_client_card(client)
        assert "Да" in card

    def test_inactive_client_shows_no(self):
        client = make_client(is_active=False)
        card = format_client_card(client)
        assert "Нет" in card

    def test_expired_shows_expired(self):
        from datetime import timedelta
        client = make_client(paid_until=datetime.utcnow() - timedelta(days=5))
        card = format_client_card(client)
        assert "Истекла" in card

    def test_no_paid_until_shows_not_set(self):
        client = make_client(paid_until=None)
        card = format_client_card(client)
        assert "Не указано" in card

    def test_trial_used_shown(self):
        client = make_client(notes="trial_used=true")
        card = format_client_card(client)
        assert "Да" in card  # trial_used=true → "Да"


class TestFormatHistoryRows:
    def test_empty_history(self):
        result = format_history_rows([])
        assert "пуста" in result.lower() or "empty" in result.lower() or "пуст" in result.lower()

    def test_contains_plan_code(self):
        row = make_history_row(plan_code="3m")
        result = format_history_rows([row])
        assert "3m" in result

    def test_trial_marker_shown(self):
        row = make_history_row(is_trial=True)
        result = format_history_rows([row])
        assert "trial" in result

    def test_paid_marker_shown(self):
        row = make_history_row(is_trial=False)
        result = format_history_rows([row])
        assert "paid" in result

    def test_multiple_rows_all_included(self):
        rows = [make_history_row(id=i, plan_code=f"{i}m") for i in range(1, 4)]
        result = format_history_rows(rows)
        for i in range(1, 4):
            assert f"{i}m" in result
