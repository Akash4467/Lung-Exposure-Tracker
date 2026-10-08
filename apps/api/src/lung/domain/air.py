from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HourlyAir:
    hour: datetime  # UTC hour start
    pm25: float
    pm10: float | None
    wind_speed: float | None  # m/s
    wind_dir: float | None  # degrees the wind comes FROM
