"""The air fetch must cover the user's local "tomorrow", whatever their time zone and hour.

Open-Meteo counts forecast days from the current UTC date. Just after local midnight in a
zone ahead of UTC (India, 00:00-05:30 IST) the UTC date is still yesterday, so "today + 1
forecast day" in UTC ended hours before the local tomorrow did: scores couldn't be computed
and the app showed "Getting the air data for your area" until 05:30 (found 6 Oct 2026).
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from lung.settings import Settings


def _last_fetched_hour(now_utc: datetime, forecast_days: int) -> datetime:
    """Open-Meteo returns whole UTC days: today (UTC) plus forecast_days - 1 more."""
    first_day = now_utc.date()
    return datetime.combine(first_day + timedelta(days=forecast_days - 1), time(23), tzinfo=UTC)


def _needed_until(now_utc: datetime, tz: str) -> datetime:
    """The end of the local tomorrow, plus the hour of margin the plan reads."""
    local_today: date = now_utc.astimezone(ZoneInfo(tz)).date()
    end = datetime.combine(local_today + timedelta(days=2), time(0), tzinfo=ZoneInfo(tz))
    return (end + timedelta(hours=1)).astimezone(UTC)


@pytest.mark.parametrize(
    "now_utc,tz",
    [
        (datetime(2026, 10, 5, 18, 45, tzinfo=UTC), "Asia/Kolkata"),  # 00:15 IST, the bug
        (datetime(2026, 10, 5, 23, 59, tzinfo=UTC), "Asia/Kolkata"),  # 05:29 IST
        (datetime(2026, 10, 5, 12, 0, tzinfo=UTC), "Asia/Kolkata"),  # 17:30 IST
        (datetime(2026, 10, 5, 23, 0, tzinfo=UTC), "Pacific/Auckland"),  # +13: worst case
        (datetime(2026, 10, 5, 3, 0, tzinfo=UTC), "America/Los_Angeles"),  # behind UTC
    ],
)
def test_default_fetch_covers_local_tomorrow(now_utc: datetime, tz: str) -> None:
    days = Settings.model_fields["air_forecast_days"].default
    needed = _needed_until(now_utc, tz)
    # the last fetched hour starts at 23:00 and gap-filling may stretch up to 6 h past it
    assert _last_fetched_hour(now_utc, days) + timedelta(hours=6) >= needed


def test_two_days_was_not_enough_for_india_after_midnight() -> None:
    now = datetime(2026, 10, 5, 18, 45, tzinfo=UTC)
    assert _last_fetched_hour(now, 2) + timedelta(hours=6) < _needed_until(now, "Asia/Kolkata")
