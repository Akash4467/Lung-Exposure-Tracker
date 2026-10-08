"""Breathing rate, concentration over a segment, and dose."""

from datetime import UTC, datetime, timedelta

from lung.engine.config import EngineConfig
from lung.engine.models import Activity, Profile, Readings, Segment, Sex

HOUR = timedelta(hours=1)


class MissingReadingError(LookupError):
    """No PM2.5 value for a cell and hour the segment needs."""

    def __init__(self, cell_id: str, hour: datetime) -> None:
        super().__init__(f"no PM2.5 for cell {cell_id} at {hour.isoformat()}")
        self.cell_id = cell_id
        self.hour = hour


def _bmr_kcal_per_day(sex: Sex, age: int, weight_kg: float, cfg: EngineConfig) -> float:
    if sex == "other":
        return (
            _bmr_kcal_per_day("man", age, weight_kg, cfg)
            + _bmr_kcal_per_day("woman", age, weight_kg, cfg)
        ) / 2
    bands = [b for b in cfg.breathing_personal.bmr if b.sex == sex]
    band = next(
        (b for b in bands if b.min_age <= age <= b.max_age),
        min(bands, key=lambda b: abs(b.min_age - age)),
    )
    return band.slope * weight_kg + band.intercept


def typical_weight_kg(profile: Profile, cfg: EngineConfig) -> float:
    """Used only when exertion is measured but no weight was given."""
    if profile.weight_kg is not None:
        return profile.weight_kg
    w = cfg.breathing_personal.default_weight
    if profile.age <= w.young_max_age:
        return w.young_slope * profile.age + w.young_intercept
    adult = w.adult[profile.sex]
    if profile.age <= w.older_child_max_age:
        return min(adult, w.older_slope * profile.age + w.older_intercept)
    return adult


def _met_rate(profile: Profile, met: float, weight: float, cfg: EngineConfig) -> float:
    bp = cfg.breathing_personal
    kcal_per_h = _bmr_kcal_per_day(profile.sex, profile.age, weight, cfg) / 24
    return kcal_per_h * met * bp.oxygen_l_per_kcal * bp.ventilatory_equivalent / 1000


def breathing_rate(
    profile: Profile, activity: Activity, cfg: EngineConfig, met: float | None = None
) -> float:
    """m³/h.

    Measured exertion (`met`, from heart rate or steps): BMR × MET × O2 per kcal ×
    ventilatory equivalent (EPA EFH method), with a typical weight if none was given.
    Known weight: the same, with the activity's typical MET.
    Otherwise: the table; child column up to child_max_age, "other" averages man and woman.
    """
    if met is not None:
        return _met_rate(profile, met, typical_weight_kg(profile, cfg), cfg)
    if profile.weight_kg is not None:
        return _met_rate(profile, cfg.breathing_personal.met[activity], profile.weight_kg, cfg)

    row = cfg.inhalation_m3_per_h[activity]
    if profile.age <= cfg.child_max_age:
        return row["child"]
    if profile.sex == "other":
        return (row["man"] + row["woman"]) / 2
    return row[profile.sex]


def _hour_floor(t: datetime) -> datetime:
    return t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def outdoor_pm25(segment: Segment, readings: Readings) -> float:
    """Time-weighted outdoor PM2.5 over the segment, from hourly readings for its cell."""
    cell = readings.get(segment.cell_id, {})
    start, end = segment.start.astimezone(UTC), segment.end.astimezone(UTC)
    total_s = (end - start).total_seconds()
    if total_s <= 0:
        return 0.0

    weighted = 0.0
    hour = _hour_floor(start)
    while hour < end:
        overlap = (min(end, hour + HOUR) - max(start, hour)).total_seconds()
        if overlap > 0:
            if hour not in cell:
                raise MissingReadingError(segment.cell_id, hour)
            weighted += cell[hour] * overlap
        hour += HOUR
    return weighted / total_s


def breathed_parts(segment: Segment, readings: Readings, cfg: EngineConfig) -> tuple[float, float]:
    """(from outdoor air, from indoor sources), both after the mask, in µg/m³."""
    mask = cfg.mask_factor[segment.mask]
    return (
        outdoor_pm25(segment, readings) * segment.factor * mask,
        segment.added_ugm3 * mask,
    )


def breathed_pm25(segment: Segment, readings: Readings, cfg: EngineConfig) -> float:
    """Concentration actually breathed: outdoor × indoor/cabin factor + sources, × mask."""
    outdoor, sources = breathed_parts(segment, readings, cfg)
    return outdoor + sources


def segment_dose(
    segment: Segment, profile: Profile, readings: Readings, cfg: EngineConfig
) -> float:
    """µg inhaled over the segment."""
    rate = breathing_rate(profile, segment.activity, cfg, segment.met)
    return breathed_pm25(segment, readings, cfg) * rate * segment.hours
