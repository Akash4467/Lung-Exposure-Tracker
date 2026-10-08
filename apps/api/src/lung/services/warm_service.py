"""Popular areas kept fresh ahead of demand (see warm_areas.yaml).

The worker's hourly tick fetches these along with every area users already use, so someone
who signs up in, say, Noida gets their first Lung Load at once instead of waiting a minute
for the first fetch. The list is read once per process; edit the YAML and restart to change it.
"""

import math
from functools import lru_cache
from pathlib import Path

import yaml

from lung.domain.geo import cell_id

WARM_FILE = Path(__file__).resolve().parent.parent / "warm_areas.yaml"


def cells_for(raw: dict, resolution_deg: float) -> list[str]:  # type: ignore[type-arg]
    out: set[str] = set()
    for box in raw.get("boxes") or []:
        south, north = float(box["south"]), float(box["north"])
        west, east = float(box["west"]), float(box["east"])
        rows = math.floor((north - south) / resolution_deg + 1e-9)
        cols = math.floor((east - west) / resolution_deg + 1e-9)
        for i in range(rows + 1):
            for j in range(cols + 1):
                out.add(
                    cell_id(south + i * resolution_deg, west + j * resolution_deg, resolution_deg)
                )
    for p in raw.get("points") or []:
        out.add(cell_id(float(p["lat"]), float(p["lon"]), resolution_deg))
    return sorted(out)


@lru_cache(maxsize=4)
def warm_cells(resolution_deg: float) -> tuple[str, ...]:
    if not WARM_FILE.exists():
        return ()
    raw = yaml.safe_load(WARM_FILE.read_text(encoding="utf-8")) or {}
    return tuple(cells_for(raw, resolution_deg))
