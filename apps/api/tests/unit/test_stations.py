from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from lung.domain.air import HourlyAir
from lung.domain.geo import LatLon
from lung.infra.engine_config import load_config
from lung.integrations.stations import StationReading, parse_cpcb
from lung.services.station_service import apply

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
CENTER = LatLon(28.6, 77.2)


def _rows(value: float = 100.0) -> list[HourlyAir]:
    return [HourlyAir(NOW + timedelta(hours=h), value, None, 2.0, 300.0) for h in range(-24, 48)]


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(cfg=load_config())


def test_close_station_pulls_now_and_fades_with_time() -> None:
    # one official monitor 3 km away reads 150 where the model says 100
    station = StationReading(28.62, 77.22, 150.0, NOW, "cpcb", "ITO")
    out, ratio, used = apply(_rows(), CENTER, [station], _ctx())  # type: ignore[arg-type]
    assert used == 1
    assert 1.3 < ratio <= 1.5  # trust < 1, so not the full ×1.5
    by_hour = {r.hour: r.pm25 for r in out}
    now_v, plus6, plus36 = (
        by_hour[NOW],
        by_hour[NOW + timedelta(hours=6)],
        by_hour[NOW + timedelta(hours=36)],
    )
    assert now_v == pytest.approx(100 * ratio)
    assert 100 < plus6 < now_v  # fading after 6 h (tau)
    assert plus36 == pytest.approx(100, rel=0.02)  # the far forecast stays as modelled


def test_far_or_missing_stations_change_nothing() -> None:
    far = StationReading(30.0, 77.2, 300.0, NOW, "cpcb", "far away")  # ~155 km
    out, ratio, used = apply(_rows(), CENTER, [far], _ctx())  # type: ignore[arg-type]
    assert (ratio, used) == (1.0, 0)
    assert all(r.pm25 == 100.0 for r in out)
    assert apply(_rows(), CENTER, [], _ctx()) == (_rows(), 1.0, 0)  # type: ignore[arg-type]


def test_ratio_is_capped() -> None:
    wild = StationReading(28.6, 77.2, 2000.0, NOW, "cpcb", "broken monitor")
    _, ratio, _ = apply(_rows(), CENTER, [wild], _ctx())  # type: ignore[arg-type]
    assert ratio <= 4.0


def test_parse_cpcb_rows() -> None:
    rows = [
        {
            "station": "ITO, Delhi - CPCB",
            "last_update": "05-10-2026 17:00:00",  # IST
            "latitude": "28.628624",
            "longitude": "77.24106",
            "pollutant_id": "PM2.5",
            "avg_value": "142",
        },
        {
            "pollutant_id": "PM10",
            "avg_value": "300",
            "last_update": "05-10-2026 17:00:00",
            "latitude": "28.6",
            "longitude": "77.2",
            "station": "x",
        },
        {
            "pollutant_id": "PM2.5",
            "avg_value": "NA",
            "last_update": "05-10-2026 17:00:00",
            "latitude": "28.6",
            "longitude": "77.2",
            "station": "y",
        },
    ]
    (r,) = parse_cpcb(rows)
    assert (r.pm25, r.provider, r.name) == (142.0, "cpcb", "ITO, Delhi - CPCB")
    assert r.at == datetime(2026, 10, 5, 11, 30, tzinfo=UTC)  # 17:00 IST
