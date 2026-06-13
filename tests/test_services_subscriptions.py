"""Tests for pure/async helper functions in services/subscriptions.py."""
from datetime import datetime, timedelta

import pytest

from services.subscriptions import (
    is_subscription_active,
    serialize_subscription_status,
    SubscriptionStatus,
)
from tests.conftest import make_client


class TestIsSubscriptionActive:
    async def test_active_client(self):
        client = make_client(
            status="active",
            is_active=True,
            is_paid=True,
            paid_until=datetime.utcnow() + timedelta(days=5),
        )
        assert await is_subscription_active(client) is True

    async def test_none_client_returns_false(self):
        assert await is_subscription_active(None) is False

    async def test_wrong_status(self):
        client = make_client(status="blocked", is_active=True, is_paid=True,
                             paid_until=datetime.utcnow() + timedelta(days=5))
        assert await is_subscription_active(client) is False

    async def test_not_active(self):
        client = make_client(status="active", is_active=False, is_paid=True,
                             paid_until=datetime.utcnow() + timedelta(days=5))
        assert await is_subscription_active(client) is False

    async def test_not_paid(self):
        client = make_client(status="active", is_active=True, is_paid=False,
                             paid_until=datetime.utcnow() + timedelta(days=5))
        assert await is_subscription_active(client) is False

    async def test_no_paid_until(self):
        client = make_client(status="active", is_active=True, is_paid=True, paid_until=None)
        assert await is_subscription_active(client) is False

    async def test_expired(self):
        client = make_client(status="active", is_active=True, is_paid=True,
                             paid_until=datetime.utcnow() - timedelta(seconds=1))
        assert await is_subscription_active(client) is False


class TestSerializeSubscriptionStatus:
    def _make_status(self, **kwargs) -> SubscriptionStatus:
        defaults = dict(
            is_active=True,
            is_paid=True,
            paid_until=datetime(2026, 12, 31),
            is_expired=False,
            days_left=200,
            seconds_left=200 * 86400,
            plan_code="3m",
            max_devices=2,
        )
        defaults.update(kwargs)
        return SubscriptionStatus(**defaults)

    def test_all_fields_present(self):
        status = self._make_status()
        result = serialize_subscription_status(status)
        for field in ("is_active", "is_paid", "paid_until", "is_expired",
                      "days_left", "seconds_left", "plan_code", "max_devices"):
            assert field in result

    def test_paid_until_serialized_as_isoformat(self):
        dt = datetime(2026, 6, 13, 10, 0, 0)
        status = self._make_status(paid_until=dt)
        result = serialize_subscription_status(status)
        assert result["paid_until"] == dt.isoformat()

    def test_paid_until_none_serialized_as_none(self):
        status = self._make_status(paid_until=None)
        result = serialize_subscription_status(status)
        assert result["paid_until"] is None

    def test_inactive_client(self):
        status = self._make_status(is_active=False, is_paid=False, is_expired=True, days_left=0)
        result = serialize_subscription_status(status)
        assert result["is_active"] is False
        assert result["is_expired"] is True
        assert result["days_left"] == 0
