from lung.services.warm_service import cells_for, warm_cells


def test_box_covers_every_cell_inside() -> None:
    raw = {"boxes": [{"south": 28.4, "west": 76.9, "north": 28.6, "east": 77.0}]}
    assert cells_for(raw, 0.1) == [
        "28.4_76.9",
        "28.4_77.0",
        "28.5_76.9",
        "28.5_77.0",
        "28.6_76.9",
        "28.6_77.0",
    ]


def test_points_snap_to_their_cell_and_duplicates_merge() -> None:
    raw = {"points": [{"lat": 19.076, "lon": 72.878}, {"lat": 19.08, "lon": 72.91}]}
    assert cells_for(raw, 0.1) == ["19.1_72.9"]
    assert cells_for({}, 0.1) == []


def test_shipped_list_has_delhi_ncr_and_stays_within_budget() -> None:
    cells = warm_cells(0.1)
    assert "28.6_77.2" in cells  # central Delhi
    assert "28.5_77.3" in cells  # Noida
    assert "19.1_72.9" in cells  # Mumbai
    # 2 Open-Meteo calls per area per hour, free plan ~10,000/day: keep plenty of room for users
    assert len(cells) * 2 * 24 < 5000
