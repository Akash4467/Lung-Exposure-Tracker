"""Reference dose, score, band and the full daily Result."""

from collections.abc import Sequence

from lung.engine.cigarettes import cigarettes
from lung.engine.config import EngineConfig
from lung.engine.dose import breathed_parts, breathing_rate
from lung.engine.models import (
    PLACES,
    Activity,
    Band,
    Place,
    Profile,
    Readings,
    Result,
    Segment,
)


def sensitivity(profile: Profile, cfg: EngineConfig) -> float:
    """M: the highest multiplier that applies, never the product."""
    s = cfg.sensitivity
    m = s.adult
    if profile.age >= 65:
        m = max(m, s.age_65_plus)
    if profile.age <= cfg.child_max_age or profile.sensitive:
        m = max(m, s.child_or_respiratory)
    return m


def band_for(score: float, cfg: EngineConfig) -> Band:
    if score <= cfg.bands.green_max:
        return "green"
    if score <= cfg.bands.amber_max:
        return "amber"
    return "red"


def reference_dose(profile: Profile, segments: Sequence[Segment], cfg: EngineConfig) -> float:
    """The same day breathed at the WHO guideline everywhere, with no indoor or mask benefit."""
    return sum(
        cfg.who_guideline_ugm3 * breathing_rate(profile, s.activity, cfg, s.met) * s.hours
        for s in segments
    )


def compute(
    profile: Profile, segments: Sequence[Segment], readings: Readings, cfg: EngineConfig
) -> Result:
    if not segments:
        raise ValueError("a day needs at least one segment")

    by_place: dict[Place, float] = dict.fromkeys(PLACES, 0.0)
    by_activity: dict[Activity, float] = {}
    from_sources = 0.0
    conc_hours = 0.0
    total_hours = 0.0
    air = 0.0
    for seg in segments:
        outdoor, sources = breathed_parts(seg, readings, cfg)
        rate_hours = breathing_rate(profile, seg.activity, cfg, seg.met) * seg.hours
        by_place[seg.place] += (outdoor + sources) * rate_hours
        by_activity[seg.activity] = (
            by_activity.get(seg.activity, 0.0) + (outdoor + sources) * rate_hours
        )
        from_sources += sources * rate_hours
        conc_hours += (outdoor + sources) * seg.hours
        total_hours += seg.hours
        air += rate_hours

    dose = sum(by_place.values())
    ref = reference_dose(profile, segments, cfg)
    score = 100 * dose / ref * sensitivity(profile, cfg)
    avg = conc_hours / total_hours
    split: dict[Place, float] = (
        {p: d / dose for p, d in by_place.items()} if dose > 0 else dict.fromkeys(PLACES, 0.0)
    )
    return Result(
        dose_ug=dose,
        ref_ug=ref,
        score=score,
        band=band_for(score, cfg),
        cigarettes=cigarettes(avg, cfg),
        avg_pm25=avg,
        split=split,
        indoor_source_share=from_sources / dose if dose > 0 else 0.0,
        by_activity={a: d / dose for a, d in by_activity.items()} if dose > 0 else {},
        air_m3=air,
        hours=total_hours,
    )
