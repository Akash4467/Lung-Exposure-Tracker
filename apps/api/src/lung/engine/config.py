"""Typed view of config.yaml. Parsing only; reading the file is infra's job."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lung.engine.models import Activity, CommuteMode, Mask, Sex, Windows


@dataclass(frozen=True)
class Bands:
    green_max: float
    amber_max: float


@dataclass(frozen=True)
class Sensitivity:
    adult: float
    age_65_plus: float
    child_or_respiratory: float


@dataclass(frozen=True)
class BmrBand:
    sex: Sex
    min_age: int
    max_age: int
    slope: float
    intercept: float


@dataclass(frozen=True)
class DefaultWeight:
    adult: Mapping[Sex, float]
    young_max_age: int
    young_slope: float
    young_intercept: float
    older_child_max_age: int
    older_slope: float
    older_intercept: float


@dataclass(frozen=True)
class BreathingPersonal:
    oxygen_l_per_kcal: float
    ventilatory_equivalent: float
    met: Mapping[Activity, float]
    bmr: tuple[BmrBand, ...]
    default_weight: DefaultWeight


@dataclass(frozen=True)
class ActivityConfig:
    resting_hr_default: float
    hr_max_intercept: float
    hr_max_slope: float
    vo2max_factor: float
    cadence_met: tuple[tuple[float, float], ...]
    kind_thresholds: Mapping[str, float]


@dataclass(frozen=True)
class SourceTip:
    text: str
    scale: float
    free: bool


@dataclass(frozen=True)
class IndoorConfig:
    penetration: float
    deposition_per_h: float
    air_exchange_per_h: Mapping[Windows, float]
    default_purifier_removal_per_h: float
    volume_m3: Mapping[str, float]
    default_home_size: str
    default_office_size: str
    sources: Mapping[str, float]  # mg/min
    source_tips: Mapping[str, SourceTip]


@dataclass(frozen=True)
class AirCorrection:
    radius_km: float
    distance_floor_km: float
    prior_weight: float
    max_ratio: float


@dataclass(frozen=True)
class ForecastConfig:
    nowcast_tau_h: float
    nowcast_max_ratio: float
    fire_risk_upwind_count: Mapping[str, int]
    fire_pm25_uplift_per_fire: float
    fire_radius_km: float = 400.0
    fire_upwind_half_angle_deg: float = 45.0
    fire_window_h: float = 48.0


@dataclass(frozen=True)
class UncertaintyConfig:
    runs: int
    air_model: float
    air_corrected: float
    breathing_table: float
    breathing_personal: float
    penetration: float
    deposition: float
    air_exchange: float
    volume_unknown: float
    volume_known: float
    cadr_unknown: float
    cadr_known: float
    source_emission: float
    mask: float
    road: float


@dataclass(frozen=True)
class TipsConfig:
    max_tips: int
    commute_shift_options_minutes: tuple[int, ...]
    min_saving_pct: float


@dataclass(frozen=True)
class EngineConfig:
    who_guideline_ugm3: float
    cigarette_ugm3: float
    bands: Bands
    child_max_age: int
    inhalation_m3_per_h: Mapping[Activity, Mapping[str, float]]
    breathing_personal: BreathingPersonal
    commute_activity: Mapping[CommuteMode, Activity]
    commute_factor: Mapping[CommuteMode, float]
    road_factor: Mapping[str, float]
    mask_factor: Mapping[Mask, float]
    indoor: IndoorConfig
    sensitivity: Sensitivity
    air_correction: AirCorrection
    forecast: ForecastConfig
    uncertainty: UncertaintyConfig
    activity: ActivityConfig
    tips: TipsConfig


def parse_config(raw: Mapping[str, Any]) -> EngineConfig:
    bp = raw["breathing_personal"]
    ind = raw["indoor"]
    fc = raw["forecast"]
    tips = raw["tips"]
    return EngineConfig(
        who_guideline_ugm3=float(raw["who_guideline_ugm3"]),
        cigarette_ugm3=float(raw["cigarette_ugm3"]),
        bands=Bands(**raw["bands"]),
        child_max_age=int(raw["child_max_age"]),
        inhalation_m3_per_h=raw["inhalation_m3_per_h"],
        breathing_personal=BreathingPersonal(
            oxygen_l_per_kcal=float(bp["oxygen_l_per_kcal"]),
            ventilatory_equivalent=float(bp["ventilatory_equivalent"]),
            met=bp["met"],
            bmr=tuple(BmrBand(**b) for b in bp["bmr"]),
            default_weight=DefaultWeight(**bp["default_weight"]),
        ),
        commute_activity=raw["commute_activity"],
        commute_factor=raw["commute_factor"],
        road_factor=raw["road_factor"],
        mask_factor=raw["mask_factor"],
        indoor=IndoorConfig(
            penetration=float(ind["penetration"]),
            deposition_per_h=float(ind["deposition_per_h"]),
            air_exchange_per_h=ind["air_exchange_per_h"],
            default_purifier_removal_per_h=float(ind["default_purifier_removal_per_h"]),
            volume_m3=ind["volume_m3"],
            default_home_size=ind["default_home_size"],
            default_office_size=ind["default_office_size"],
            sources=ind["sources"],
            source_tips={k: SourceTip(**v) for k, v in ind["source_tips"].items()},
        ),
        sensitivity=Sensitivity(**raw["sensitivity"]),
        air_correction=AirCorrection(**raw["air_correction"]),
        forecast=ForecastConfig(
            nowcast_tau_h=float(fc["nowcast_tau_h"]),
            nowcast_max_ratio=float(fc["nowcast_max_ratio"]),
            fire_risk_upwind_count=fc["fire_risk_upwind_count"],
            fire_pm25_uplift_per_fire=float(fc["fire_pm25_uplift_per_fire"]),
            fire_radius_km=float(fc.get("fire_radius_km", 400)),
            fire_upwind_half_angle_deg=float(fc.get("fire_upwind_half_angle_deg", 45)),
            fire_window_h=float(fc.get("fire_window_h", 48)),
        ),
        uncertainty=UncertaintyConfig(**raw["uncertainty"]),
        activity=ActivityConfig(
            **{k: v for k, v in raw["activity"].items() if k != "cadence_met"},
            cadence_met=tuple((float(x), float(y)) for x, y in raw["activity"]["cadence_met"]),
        ),
        tips=TipsConfig(
            max_tips=int(tips["max_tips"]),
            commute_shift_options_minutes=tuple(tips["commute_shift_options_minutes"]),
            min_saving_pct=float(tips["min_saving_pct"]),
        ),
    )
