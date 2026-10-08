"""Tips and the what-if simulator. Both re-run compute() with one change; no new maths."""

from dataclasses import dataclass
from datetime import date

from lung.engine.config import EngineConfig
from lung.engine.day import apply_change, build_day, is_noop
from lung.engine.dose import MissingReadingError
from lung.engine.models import Change, DayPlan, Profile, Readings, Result
from lung.engine.score import compute


@dataclass(frozen=True)
class Tip:
    id: str
    text: str
    saves_pct: float
    free: bool  # costs nothing: timing, windows


@dataclass(frozen=True)
class Simulation:
    before: Result
    after: Result

    @property
    def saves_pct(self) -> float:
        if self.before.dose_ug == 0:
            return 0.0
        return 100 * (self.before.dose_ug - self.after.dose_ug) / self.before.dose_ug


def simulate(
    profile: Profile,
    local_date: date,
    plan: DayPlan,
    change: Change,
    readings: Readings,
    cfg: EngineConfig,
) -> Simulation:
    before = compute(profile, build_day(local_date, plan, cfg), readings, cfg)
    after_plan = apply_change(plan, change)
    after = compute(profile, build_day(local_date, after_plan, cfg), readings, cfg)
    return Simulation(before=before, after=after)


def _shift_text(minutes: int) -> str:
    hours = abs(minutes) / 60
    amount = f"{hours:g} hour" + ("" if hours == 1 else "s")
    return f"Leave {amount} {'later' if minutes > 0 else 'earlier'}, both ways"


def _candidates(plan: DayPlan, cfg: EngineConfig) -> list[tuple[str, str, Change, bool]]:
    out: list[tuple[str, str, Change, bool]] = [
        (
            "close_windows_home",
            "Keep windows closed at home",
            Change(close_windows_home=True),
            True,
        ),
        ("purifier_home", "Run an air purifier at home", Change(purifier_home=True), False),
        ("purifier_office", "Run an air purifier at work", Change(purifier_office=True), False),
        (
            "n95_commute",
            "Wear a well-fitted N95 on your commute",
            Change(commute_mask="n95"),
            False,
        ),
    ]
    for kind in sorted({u.kind for u in plan.home_indoor.sources}):
        tip = cfg.indoor.source_tips.get(kind)
        if tip is not None:
            out.append(
                (f"source_{kind}", tip.text, Change(scale_sources=((kind, tip.scale),)), tip.free)
            )
    if plan.goes_to_office:
        for m in cfg.tips.commute_shift_options_minutes:
            out.append(
                (f"shift_commute_{m:+d}", _shift_text(m), Change(commute_shift_minutes=m), True)
            )
    return [c for c in out if not is_noop(plan, c[2])]


def tips(
    profile: Profile, local_date: date, plan: DayPlan, readings: Readings, cfg: EngineConfig
) -> list[Tip]:
    """The best few actions by saving. Always includes at least one free action if any helps."""
    scored: list[Tip] = []
    shifts: list[tuple[Tip, int]] = []
    for tip_id, text, change, free in _candidates(plan, cfg):
        try:
            saved = simulate(profile, local_date, plan, change, readings, cfg).saves_pct
        except (MissingReadingError, ValueError):
            continue  # no air data for the shifted hours, or the shift breaks the schedule
        if saved <= 0:
            continue
        tip = Tip(id=tip_id, text=text, saves_pct=round(saved, 1), free=free)
        if change.commute_shift_minutes:
            shifts.append((tip, abs(change.commute_shift_minutes)))
        else:
            scored.append(tip)
    if shifts:
        # Offer one commute shift: the biggest saving, and among near-ties (within 1 point)
        # the smallest change to the person's day.
        top = max(t.saves_pct for t, _ in shifts)
        scored.append(min((s for s in shifts if s[0].saves_pct >= top - 1), key=lambda s: s[1])[0])

    scored.sort(key=lambda t: t.saves_pct, reverse=True)
    picked = [t for t in scored if t.saves_pct >= cfg.tips.min_saving_pct][: cfg.tips.max_tips]
    if picked and not any(t.free for t in picked):
        # a free tip still has to be worth doing: never offer one that barely helps
        best_free = next(
            (t for t in scored if t.free and t.saves_pct >= cfg.tips.min_saving_pct), None
        )
        if best_free:
            picked = [*picked[: cfg.tips.max_tips - 1], best_free]
    return picked
