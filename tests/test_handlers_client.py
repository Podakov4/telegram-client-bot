"""Tests for pure helper functions in handlers/client.py and handlers/common.py."""
from datetime import datetime, timedelta

import pytest

from handlers.common import client_has_active_access, client_has_trial_used
from handlers.client import (
    build_referral_link,
    format_access_text,
    format_device_line,
)
from tests.conftest import make_client


class TestClientHasTrialUsed:
    def test_true_when_trial_used_in_notes(self):
        client = make_client(notes="trial_used=true")
        assert client_has_trial_used(client) is True

    def test_false_when_notes_empty(self):
        client = make_client(notes=None)
        assert client_has_trial_used(client) is False

    def test_false_when_trial_not_in_notes(self):
        client = make_client(notes="plan_code=1m\nmax_devices=3")
        assert client_has_trial_used(client) is False

    def test_false_for_none_client(self):
        assert client_has_trial_used(None) is False

    def test_false_when_trial_used_false(self):
        client = make_client(notes="trial_used=false")
        assert client_has_trial_used(client) is False


class TestClientHasActiveAccess:
    def test_true_when_active_with_link(self):
        client = make_client(
            is_active=True,
            subscription_link="vless://uuid@host:443?type=ws",
        )
        assert client_has_active_access(client) is True

    def test_false_when_active_but_no_link(self):
        client = make_client(is_active=True, subscription_link=None)
        assert client_has_active_access(client) is False

    def test_true_when_not_active_but_not_expired_and_has_link(self):
        client = make_client(
            is_active=False,
            paid_until=datetime.utcnow() + timedelta(days=1),
            subscription_link="vless://uuid@host:443?type=ws",
        )
        assert client_has_active_access(client) is True

    def test_false_when_expired_no_is_active(self):
        client = make_client(
            is_active=False,
            paid_until=datetime.utcnow() - timedelta(days=1),
            subscription_link="vless://uuid@host:443",
        )
        assert client_has_active_access(client) is False

    def test_false_for_none_client(self):
        assert client_has_active_access(None) is False


class TestBuildReferralLink:
    def test_contains_bot_username(self):
        link = build_referral_link("mybot", "CODE123")
        assert "mybot" in link

    def test_contains_referral_code(self):
        link = build_referral_link("mybot", "CODE123")
        assert "CODE123" in link

    def test_uses_ref_prefix(self):
        link = build_referral_link("mybot", "CODE123")
        assert "ref_CODE123" in link

    def test_is_telegram_link(self):
        link = build_referral_link("mybot", "CODE123")
        assert link.startswith("https://t.me/")


class TestFormatAccessText:
    def _make_active_client(self):
        return make_client(
            is_active=True,
            is_paid=True,
            paid_until=datetime.utcnow() + timedelta(days=14),
            notes=None,
        )

    def test_shows_active_status(self):
        client = self._make_active_client()
        text = format_access_text(client, active_devices=1, max_devices=3, is_active=True)
        assert "активен" in text.lower()

    def test_shows_device_count(self):
        client = self._make_active_client()
        text = format_access_text(client, active_devices=2, max_devices=5, is_active=True)
        assert "2/5" in text

    def test_shows_days_left(self):
        client = self._make_active_client()
        text = format_access_text(client, active_devices=1, max_devices=3, is_active=True)
        assert "дн." in text

    def test_inactive_text_when_not_active(self):
        client = make_client(is_active=False, paid_until=None)
        text = format_access_text(client, active_devices=0, max_devices=3, is_active=False)
        assert "не активен" in text.lower()

    def test_no_paid_until_shows_placeholder(self):
        client = make_client(paid_until=None)
        text = format_access_text(client, active_devices=0, max_devices=3, is_active=False)
        assert "не указано" in text.lower()


class TestFormatDeviceLine:
    def _make_device(self, **kwargs):
        from types import SimpleNamespace
        defaults = dict(
            id=1,
            platform="android",
            device_name="My Phone",
            app_version="1.0.0",
            os_version="Android 13",
            is_active=True,
            is_revoked=False,
            last_seen_at=datetime(2026, 1, 15, 10, 30),
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_contains_device_name(self):
        device = self._make_device(device_name="Galaxy S23")
        line = format_device_line(device)
        assert "Galaxy S23" in line

    def test_active_device_shows_active_status(self):
        device = self._make_device(is_active=True, is_revoked=False)
        line = format_device_line(device)
        assert "активно" in line.lower()

    def test_revoked_device_shows_disabled(self):
        device = self._make_device(is_active=False, is_revoked=True)
        line = format_device_line(device)
        assert "отключено" in line.lower()

    def test_shows_platform(self):
        device = self._make_device(platform="ios")
        line = format_device_line(device)
        assert "ios" in line.lower()

    def test_shows_device_id(self):
        device = self._make_device(id=42)
        line = format_device_line(device)
        assert "42" in line

    def test_no_last_seen_shows_dash(self):
        device = self._make_device(last_seen_at=None)
        line = format_device_line(device)
        assert "—" in line
