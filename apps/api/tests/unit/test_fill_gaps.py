from datetime import UTC, datetime, timedelta

from lung.services.score_service import fill_gaps

H = timedelta(hours=1)
T0 = datetime(2026, 10, 4, 0, tzinfo=UTC)


def test_fills_from_earlier_hour_first() -> None:
    out = fill_gaps({"c": {T0: 10.0, T0 + 2 * H: 30.0}}, T0, T0 + 3 * H)
    assert out["c"][T0 + H] == 10.0


def test_fills_from_later_when_nothing_earlier() -> None:
    out = fill_gaps({"c": {T0 + H: 20.0}}, T0, T0 + 2 * H)
    assert out["c"][T0] == 20.0


def test_gap_longer_than_six_hours_stays_missing() -> None:
    out = fill_gaps({"c": {T0: 10.0}}, T0, T0 + 10 * H)
    assert T0 + 6 * H in out["c"]
    assert T0 + 7 * H not in out["c"]


def test_does_not_overwrite_real_readings() -> None:
    out = fill_gaps({"c": {T0: 10.0, T0 + H: 99.0}}, T0, T0 + 2 * H)
    assert out["c"][T0 + H] == 99.0
