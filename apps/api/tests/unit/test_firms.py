from datetime import UTC, datetime

import pytest

from lung.integrations.firms import parse_csv
from lung.services.fire_service import wind_from

HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_ti5,frp,daynight\n"
)
VIIRS = (
    HEADER
    + """30.71,75.84,334.2,0.39,0.36,2026-10-05,0812,N,VIIRS,n,2.0NRT,295.1,6.4,D
30.66,75.91,345.0,0.39,0.36,2026-10-05,812,N,VIIRS,h,2.0NRT,297.3,12.9,D
29.90,76.10,301.0,0.4,0.4,2026-10-05,2010,N,VIIRS,l,2.0NRT,280.0,,N
bad,row,,,,2026-10-05,0812,N,VIIRS,n,,,,D
"""
)


def test_parse_viirs_csv() -> None:
    fires = parse_csv(VIIRS)
    assert len(fires) == 3  # the malformed row is skipped
    a, b, c = fires
    assert (a.lat, a.lon, a.confidence, a.frp) == (30.71, 75.84, "nominal", 6.4)
    assert a.detected_at == datetime(2026, 10, 5, 8, 12, tzinfo=UTC)
    assert b.detected_at == a.detected_at  # "812" is 08:12
    assert b.confidence == "high"
    assert (c.confidence, c.frp) == ("low", None)


def test_modis_percent_confidence() -> None:
    text = "latitude,longitude,acq_date,acq_time,confidence,frp\n30,75,2026-10-05,0500,85,20\n"
    assert parse_csv(text)[0].confidence == "high"


def test_wind_direction_mean() -> None:
    # north-westerlies (from 315°) with a weaker westerly hour: mostly from the north-west
    d = wind_from([(4.0, 315.0), (4.0, 315.0), (1.0, 270.0)])
    assert d == pytest.approx(311, abs=3)
    # opposite winds cancel: no direction
    assert wind_from([(3.0, 0.0), (3.0, 180.0)]) is None
    assert wind_from([(None, 90.0), (2.0, None)]) is None
    # the mean wraps around north correctly
    assert wind_from([(2.0, 350.0), (2.0, 10.0)]) == pytest.approx(0, abs=0.5) or wind_from(
        [(2.0, 350.0), (2.0, 10.0)]
    ) == pytest.approx(360, abs=0.5)
