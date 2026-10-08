from datetime import UTC, datetime, timedelta

from lung.services.track_service import GpsPoint, build_legs, classify

T0 = datetime(2026, 10, 4, 4, 0, tzinfo=UTC)


def _line(start: datetime, minutes: int, lat: float, lon: float, dlat_per_min: float, **kw: object):
    return [
        GpsPoint(t=start + timedelta(minutes=i), lat=lat + dlat_per_min * i, lon=lon, **kw)  # type: ignore[arg-type]
        for i in range(minutes + 1)
    ]


def test_classify_by_speed() -> None:
    assert classify(0.3, None, False, "car") is None  # still
    assert classify(1.4, None, False, "car") == "walk"
    assert classify(3.5, None, False, "car") == "run"
    assert classify(6.0, None, False, "cycle") == "cycle"
    assert classify(6.0, None, False, "car") == "car"
    assert classify(15.0, None, False, "walk") == "bus_metro"  # walked to work: a bus
    assert classify(15.0, None, False, "two_wheeler") == "two_wheeler"


def test_phone_activity_wins_when_confident() -> None:
    assert classify(1.0, "automotive", True, "car") == "car"  # slow traffic, still in a car
    assert classify(6.0, "running", True, "car") == "run"
    assert classify(5.0, "stationary", True, "car") is None
    assert classify(6.0, "running", False, "car") == "car"  # low confidence: speed decides


def test_walk_then_drive_makes_two_legs() -> None:
    # 10 min walking (~80 m/min), then 15 min driving north fast (~900 m/min) across cells
    walk = _line(T0, 10, 28.6139, 77.2090, 0.00072)
    drive = _line(walk[-1].t, 15, walk[-1].lat, 77.2090, 0.0081)[1:]
    legs = build_legs(walk + drive, "car", 0.1)
    modes = [leg.mode for leg in legs]
    assert modes[0] == "walk" and "car" in modes
    assert legs[0].end_at - legs[0].start_at == timedelta(minutes=10)
    # 15 min at ~0.008° a minute: from the 28.6 cell well into the 28.7 cell
    assert {leg.cell_id for leg in legs if leg.mode == "car"} == {"28.6_77.2", "28.7_77.2"}
    assert all(len(leg.path) <= 30 for leg in legs)
    assert sum(leg.distance_m for leg in legs if leg.mode == "walk") > 700


def test_noise_and_gaps() -> None:
    blip = _line(T0, 1, 28.6, 77.2, 0.0008)  # one minute of movement: dropped
    assert build_legs(blip, "car", 0.1) == []
    a = _line(T0, 5, 28.6, 77.2, 0.0008)
    b = _line(T0 + timedelta(minutes=30), 5, 28.6, 77.2, 0.0008)  # after a 25 min gap
    assert len(build_legs(a + b, "car", 0.1)) == 2
    inaccurate = _line(T0, 10, 28.6, 77.2, 0.0008, accuracy=500)
    assert build_legs(inaccurate, "car", 0.1) == []
