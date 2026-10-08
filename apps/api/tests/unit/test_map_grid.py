import pytest

from lung.domain.errors import InvalidInput
from lung.services.map_service import MAX_PER_SIDE, grid_points, grid_step


def test_step_gets_coarser_as_the_view_widens() -> None:
    assert grid_step(28.5, 77.0, 28.9, 77.4) == 0.1  # a city
    assert grid_step(20, 70, 30, 80) == 1.0  # a region
    assert grid_step(-60, -180, 80, 180) == 30.0  # the whole world


def test_grid_stays_small_and_on_a_shared_lattice() -> None:
    for box in [(28.5, 77.0, 28.9, 77.4), (8, 68, 37, 97), (-60, -180, 80, 180)]:
        step, pts = grid_points(*box)
        assert len(pts) <= (MAX_PER_SIDE + 2) ** 2
        for lat, lon in pts:
            # every point is a multiple of the step, so panning reuses cached points
            assert lat / step == pytest.approx(round(lat / step))
            assert lon / step == pytest.approx(round(lon / step))


def test_grid_covers_the_view() -> None:
    step, pts = grid_points(28.52, 77.03, 28.88, 77.37)
    lats = {p[0] for p in pts}
    lons = {p[1] for p in pts}
    assert min(lats) <= 28.52 and max(lats) >= 28.88 - step / 2
    assert min(lons) <= 77.03 and max(lons) >= 77.37 - step / 2


def test_bad_bounds() -> None:
    with pytest.raises(InvalidInput):
        grid_points(30, 70, 20, 80)  # south above north
