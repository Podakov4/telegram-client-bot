"""Shared fixtures for all tests."""
from datetime import datetime, timedelta
from types import SimpleNamespace


def make_client(**kwargs) -> SimpleNamespace:
    """Create a minimal Client-like namespace for testing pure helpers."""
    defaults = dict(
        id=1,
        telegram_id="123456789",
        full_name="Test User",
        login=None,
        email=None,
        public_id=None,
        xui_email="cl_123456789_test_user",
        xui_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        subscription_link="vless://uuid@example.com:443?type=ws#Test",
        happ_subscription_url="https://freeth.ru/sub/token123",
        happ_subscription_token="token123",
        is_active=True,
        is_paid=True,
        status="active",
        paid_until=datetime.utcnow() + timedelta(days=30),
        notes=None,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
        referral_code="REF123",
        referrer_client_id=None,
        referral_reward_granted_at=None,
        referral_bonus_days_total=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def make_history_row(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=1,
        client_id=1,
        plan_code="1m",
        is_trial=False,
        starts_at=datetime(2025, 1, 1),
        ends_at=datetime(2025, 2, 1),
        notes="payment activation",
        created_at=datetime(2025, 1, 1),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)
