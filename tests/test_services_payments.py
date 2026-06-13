"""Tests for pure helper functions in services/payments.py."""
import pytest
from services.payments import (
    add_months_as_days,
    build_payment_description,
    build_receipt_item_name,
    get_amount_by_months,
    get_default_max_devices_for_months,
)


class TestAddMonthsAsDays:
    def test_1_month_is_30_days(self):
        assert add_months_as_days(1) == 30

    def test_3_months_is_90_days(self):
        assert add_months_as_days(3) == 90

    def test_12_months_is_365_days(self):
        assert add_months_as_days(12) == 365

    def test_unknown_months_uses_30_day_approximation(self):
        assert add_months_as_days(6) == 180
        assert add_months_as_days(2) == 60


class TestGetAmountByMonths:
    def test_returns_string_for_valid_months(self):
        for months in (1, 3, 12):
            result = get_amount_by_months(months)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_raises_for_unsupported_months(self):
        with pytest.raises(ValueError):
            get_amount_by_months(2)

    def test_raises_for_zero(self):
        with pytest.raises(ValueError):
            get_amount_by_months(0)


class TestGetDefaultMaxDevicesForMonths:
    def test_1_month_gives_1_device(self):
        assert get_default_max_devices_for_months(1) == 1

    def test_3_months_gives_2_devices(self):
        assert get_default_max_devices_for_months(3) == 2

    def test_12_months_gives_3_devices(self):
        assert get_default_max_devices_for_months(12) == 3

    def test_unknown_months_gives_1_device(self):
        assert get_default_max_devices_for_months(6) == 1


class TestBuildPaymentDescription:
    def test_contains_months(self):
        desc = build_payment_description(3)
        assert "3" in desc

    def test_contains_freeth(self):
        assert "Freeth" in build_payment_description(1)

    def test_is_string(self):
        assert isinstance(build_payment_description(12), str)


class TestBuildReceiptItemName:
    def test_contains_months(self):
        name = build_receipt_item_name(1)
        assert "1" in name

    def test_contains_freeth(self):
        assert "Freeth" in build_receipt_item_name(3)

    def test_is_string(self):
        assert isinstance(build_receipt_item_name(12), str)
