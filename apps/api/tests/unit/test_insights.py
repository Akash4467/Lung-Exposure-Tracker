from datetime import UTC, date, datetime, timedelta

from lung.repositories.daily_scores import ScoreRow
from lung.services.score_service import insights

TODAY = date(2026, 10, 5)


def _day(days_ago: int, score: float, band: str, run: float = 0.0, lpm: float = 10.0) -> ScoreRow:
    return ScoreRow(
        date=TODAY - timedelta(days=days_ago),
        is_forecast=False,
        dose_ug=score,
        score=score,
        score_p10=score,
        score_p90=score,
        band=band,
        cigarettes=0.0,
        avg_pm25=0.0,
        home_share=1.0,
        commute_share=0.0,
        office_share=0.0,
        indoor_source_share=0.0,
        fire_risk=None,
        data_as_of=datetime(2026, 10, 5, tzinfo=UTC),
        engine_version="test",
        details={"by_activity": {"run": run, "light": 1 - run}, "breathing_lpm": lpm},
    )


def test_this_week_against_last_week() -> None:
    days = [_day(d, 200, "red") for d in range(7, 14)] + [_day(d, 150, "amber") for d in range(7)]
    ins = insights(days, TODAY)
    assert ins["avg_score_7d"] == 150 and ins["avg_score_prev_7d"] == 200
    assert ins["change_pct"] == -25.0
    assert ins["bands"] == {"green": 0, "amber": 7, "red": 7}


def test_best_worst_exercise_and_breathing() -> None:
    days = [
        _day(2, 90, "green", run=0.2, lpm=12),
        _day(1, 300, "red", lpm=8),
        _day(0, 120, "amber"),
    ]
    ins = insights(days, TODAY)
    assert ins["worst_day"] == {"date": TODAY - timedelta(days=1), "score": 300}
    assert ins["best_day"] == {"date": TODAY - timedelta(days=2), "score": 90}
    assert ins["exercise_share"] == round(0.2 / 3, 3)
    assert ins["avg_breathing_lpm"] == 10.0
    assert ins["change_pct"] is None  # no last week to compare with


def test_no_days() -> None:
    ins = insights([], TODAY)
    assert ins["days"] == 0 and ins["worst_day"] is None and ins["avg_breathing_lpm"] is None
