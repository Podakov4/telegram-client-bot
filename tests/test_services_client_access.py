"""Tests for pure helper functions in services/client_access.py."""
from datetime import datetime, timedelta

import pytest

from services.client_access import (
    build_happ_import_url,
    build_hiddify_import_url,
    ensure_happ_subscription_for_client,
    is_client_subscription_active,
    make_xui_email,
)
from tests.conftest import make_client


class TestMakeXuiEmail:
    def test_basic_name_and_telegram_id(self):
        client = make_client(full_name="John Doe", telegram_id="123")
        email = make_xui_email(client)
        assert email == "cl_123_john_doe"

    def test_cyrillic_name_preserved(self):
        client = make_client(full_name="Мария", telegram_id="456")
        email = make_xui_email(client)
        assert "мария" in email

    def test_special_chars_stripped_from_name(self):
        client = make_client(full_name="Anne-Marie!", telegram_id="789")
        email = make_xui_email(client)
        # hyphens and exclamation marks are removed
        assert "!" not in email
        assert "-" not in email

    def test_spaces_become_underscores(self):
        client = make_client(full_name="Ivan Ivanov", telegram_id="1")
        email = make_xui_email(client)
        assert "ivan_ivanov" in email

    def test_name_truncated_to_24_chars(self):
        client = make_client(full_name="A" * 50, telegram_id="1")
        email = make_xui_email(client)
        name_part = email.split("_", 2)[2]  # after cl_1_
        assert len(name_part) <= 24

    def test_falls_back_to_email_when_no_full_name(self):
        client = make_client(full_name=None, email="user@example.com", telegram_id="1")
        email = make_xui_email(client)
        assert "user" in email

    def test_falls_back_to_user_id_when_no_name_or_email(self):
        client = make_client(id=42, full_name=None, email=None, telegram_id="1")
        email = make_xui_email(client)
        assert "user_42" in email

    def test_uses_public_id_when_no_telegram_id(self):
        client = make_client(telegram_id=None, public_id="abcdef1234567890", full_name="Test")
        email = make_xui_email(client)
        assert "abcdef1234" in email  # first 10 chars of public_id

    def test_uses_client_id_as_identity_fallback(self):
        client = make_client(id=99, telegram_id=None, public_id=None, full_name="Test")
        email = make_xui_email(client)
        assert "id99" in email


class TestIsClientSubscriptionActive:
    def test_active_client_with_future_paid_until(self):
        client = make_client(
            status="active",
            is_active=True,
            is_paid=True,
            paid_until=datetime.utcnow() + timedelta(days=10),
        )
        assert is_client_subscription_active(client) is True

    def test_wrong_status_returns_false(self):
        client = make_client(
            status="disabled",
            is_active=True,
            is_paid=True,
            paid_until=datetime.utcnow() + timedelta(days=10),
        )
        assert is_client_subscription_active(client) is False

    def test_inactive_flag_returns_false(self):
        client = make_client(
            status="active",
            is_active=False,
            is_paid=True,
            paid_until=datetime.utcnow() + timedelta(days=10),
        )
        assert is_client_subscription_active(client) is False

    def test_unpaid_returns_false(self):
        client = make_client(
            status="active",
            is_active=True,
            is_paid=False,
            paid_until=datetime.utcnow() + timedelta(days=10),
        )
        assert is_client_subscription_active(client) is False

    def test_no_paid_until_returns_false(self):
        client = make_client(
            status="active",
            is_active=True,
            is_paid=True,
            paid_until=None,
        )
        assert is_client_subscription_active(client) is False

    def test_expired_paid_until_returns_false(self):
        client = make_client(
            status="active",
            is_active=True,
            is_paid=True,
            paid_until=datetime.utcnow() - timedelta(seconds=1),
        )
        assert is_client_subscription_active(client) is False


class TestBuildHiddifyImportUrl:
    def test_builds_hiddify_scheme(self):
        url = build_hiddify_import_url("https://freeth.ru/sub/tok123")
        assert url.startswith("hiddify://install-sub?url=")

    def test_url_encodes_the_subscription_url(self):
        url = build_hiddify_import_url("https://example.com/sub/a?x=1")
        encoded_part = url.split("?url=")[1]
        assert ":" not in encoded_part  # colon encoded to %3A
        assert "example.com" in encoded_part  # hostname (unreserved chars) preserved

    def test_none_returns_none(self):
        assert build_hiddify_import_url(None) is None

    def test_empty_string_returns_none(self):
        assert build_hiddify_import_url("") is None


class TestBuildHappImportUrl:
    def test_returns_url_unchanged(self):
        url = "https://freeth.ru/sub/tok"
        assert build_happ_import_url(url) == url

    def test_none_returns_none(self):
        assert build_happ_import_url(None) is None


class TestEnsureHappSubscription:
    def test_sets_token_when_missing(self):
        client = make_client(happ_subscription_token=None, happ_subscription_url=None)
        ensure_happ_subscription_for_client(client)
        assert client.happ_subscription_token is not None
        assert len(client.happ_subscription_token) > 0

    def test_preserves_existing_token(self):
        client = make_client(happ_subscription_token="existing-token")
        ensure_happ_subscription_for_client(client)
        assert client.happ_subscription_token == "existing-token"

    def test_sets_subscription_url_containing_token(self):
        client = make_client(happ_subscription_token=None, happ_subscription_url=None)
        ensure_happ_subscription_for_client(client)
        assert client.happ_subscription_token in client.happ_subscription_url

    def test_always_updates_url_from_token(self):
        client = make_client(happ_subscription_token="tok-abc", happ_subscription_url="https://old.url")
        ensure_happ_subscription_for_client(client)
        assert "tok-abc" in client.happ_subscription_url
