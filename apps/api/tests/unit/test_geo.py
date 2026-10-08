import pytest

from lung.domain.geo import LatLon, cell_center, cell_id, haversine_km, midpoint, sample_line


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (28.6139, 77.2090, "28.6_77.2"),
        (28.66, 77.24, "28.7_77.2"),
        (28.65, 77.25, "28.6_77.2"),  # round-half-even at the edge is fine: stable either way
        (-33.86, 151.21, "-33.9_151.2"),
        (0.04, -0.04, "0.0_0.0"),  # never "-0.0"
    ],
)
def test_cell_id(lat: float, lon: float, expected: str) -> None:
    assert cell_id(lat, lon) == expected


def test_cell_id_other_resolution() -> None:
    assert cell_id(28.6139, 77.2090, 0.05) == "28.60_77.20"
    assert cell_id(28.6139, 77.2090, 0.25) == "28.50_77.25"


def test_cell_center_round_trip() -> None:
    assert cell_center("28.6_77.2") == LatLon(28.6, 77.2)


def test_haversine_delhi_to_noida() -> None:
    # Connaught Place to Noida Sector 18: about 12.6 km in a straight line
    d = haversine_km(LatLon(28.6315, 77.2167), LatLon(28.5708, 77.3261))
    assert 12 < d < 13.5


def test_sample_line_spacing_and_cap() -> None:
    a, b = LatLon(28.6, 77.2), LatLon(28.6, 77.4)  # about 19.5 km
    samples = sample_line([a, b], every_km=1.0, max_points=20)
    assert 15 <= len(samples) <= 20
    assert samples[0][0].lon < samples[-1][0].lon  # in travel order
    assert len(sample_line([a, b], every_km=1.0, max_points=5)) == 5
    assert len(sample_line([a, LatLon(28.6, 77.2001)], every_km=1.0, max_points=20)) == 1


def test_sample_line_reports_vertex_index() -> None:
    pts = [LatLon(0, 0), LatLon(0, 0.1), LatLon(0, 1.0)]
    samples = sample_line(pts, every_km=10, max_points=20)
    assert samples[0][1] == 0  # first sample is on the first leg
    assert samples[-1][1] == 1


def test_midpoint() -> None:
    assert midpoint(LatLon(0, 0), LatLon(2, 4)) == LatLon(1, 2)
