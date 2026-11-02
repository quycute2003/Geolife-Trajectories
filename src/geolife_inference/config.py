"""Validated, serializable baseline assumptions; no machine-specific paths."""
from dataclasses import asdict, dataclass, fields
import math
from pathlib import Path
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Config:
    timezone: str = "Asia/Shanghai"
    distance_m: float = 100.0
    min_stay_minutes: float = 10.0
    max_gap_minutes: float = 5.0
    eps_m: float = 100.0
    min_samples: int = 3
    speed_warning_mps: float = 100.0
    night_start_hour: int = 22
    night_end_hour: int = 6
    work_start_hour: int = 9
    work_end_hour: int = 18
    min_role_days: int = 3
    min_office_weeks: int = 2
    min_role_dwell_minutes: float = 60.0
    min_evidence_score: float = 0.5
    min_candidate_share: float = 0.5
    min_poi_days: int = 3
    max_pois: int = 10

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
            raise ValueError("timezone must be a recognized IANA timezone") from error
        for name in ("distance_m", "min_stay_minutes", "max_gap_minutes", "eps_m",
                     "speed_warning_mps", "min_role_dwell_minutes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ("min_samples", "min_role_days", "min_office_weeks", "min_poi_days", "max_pois"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("min_evidence_score", "min_candidate_share"):
            if isinstance(getattr(self, name), bool) or not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("night_start_hour", "night_end_hour", "work_start_hour", "work_end_hour"):
            if type(getattr(self, name)) is not int or not 0 <= getattr(self, name) < 24:
                raise ValueError(f"{name} must be an integer hour in [0, 23]")
        if self.night_start_hour <= self.night_end_hour or self.work_start_hour >= self.work_end_hour:
            raise ValueError("Night must cross midnight; work must be within one local day")

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        return Config()
    with Path(path).open("rb") as stream:
        values = tomllib.load(stream)
    unknown = set(values) - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError(f"Unsupported config keys: {sorted(unknown)}")
    return Config(**values)
