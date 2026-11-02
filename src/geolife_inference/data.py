"""Read local GeoLife ZIPs/directories without extracting raw histories."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator, TextIO
import io
import zipfile

import pandas as pd

POINT_COLUMNS = ["user_id", "trajectory_id", "latitude", "longitude", "altitude_m", "timestamp"]


def parse_plt(stream: TextIO, user_id: str, trajectory_id: str) -> pd.DataFrame:
    """Malformed field counts are rejected; invalid values remain visible for audit."""
    try:
        frame = pd.read_csv(stream, skiprows=6, header=None, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=POINT_COLUMNS)
    if frame.shape[1] != 7 or frame.isna().any().any():
        raise ValueError("PLT records must contain exactly 7 fields")
    frame.columns = ["latitude", "longitude", "unused", "altitude", "serial_day", "date", "time"]
    altitude = pd.to_numeric(frame.altitude, errors="coerce")
    result = pd.DataFrame({
        "user_id": str(user_id), "trajectory_id": str(trajectory_id),
        "latitude": pd.to_numeric(frame.latitude, errors="coerce"),
        "longitude": pd.to_numeric(frame.longitude, errors="coerce"),
        "altitude_m": altitude.mask(altitude.eq(-777)) * 0.3048,
        "timestamp": pd.to_datetime(frame.date + " " + frame.time,
                                    format="%Y-%m-%d %H:%M:%S", errors="coerce", utc=True),
    })
    return result.sort_values("timestamp", kind="stable", na_position="last").reset_index(drop=True)


class GeoLifeSource:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.is_zip = self.path.is_file()
        if self.is_zip:
            with zipfile.ZipFile(self.path) as archive:
                self.names = sorted(n for n in archive.namelist() if n.lower().endswith(".plt"))
        else:
            self.names = sorted(p.relative_to(self.path).as_posix() for p in self.path.rglob("*.plt"))
        self.by_user: dict[str, list[str]] = {}
        for name in self.names:
            p = PurePosixPath(name.replace("\\", "/"))
            if len(p.parts) < 3 or p.parent.name.lower() != "trajectory":
                raise ValueError("Expected <user_id>/Trajectory/<trajectory_id>.plt")
            self.by_user.setdefault(p.parent.parent.name, []).append(name)
        if not self.by_user:
            raise ValueError("No GeoLife trajectories found")

    def inventory(self) -> dict:
        return {"user_count": len(self.by_user), "trajectory_count": len(self.names),
                "trajectories_per_user": {u: len(n) for u, n in sorted(self.by_user.items())}}

    @contextmanager
    def _archive(self):
        if self.is_zip:
            with zipfile.ZipFile(self.path) as archive:
                yield archive
        else:
            yield None

    def trajectories(self, user_id: str) -> Iterator[pd.DataFrame]:
        if user_id not in self.by_user:
            raise ValueError(f"Unknown user_id: {user_id}")
        with self._archive() as archive:
            for name in self.by_user[user_id]:
                trajectory_id = PurePosixPath(name).stem
                if archive is not None:
                    with archive.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig") as stream:
                        yield parse_plt(stream, user_id, trajectory_id)
                else:
                    with (self.path / name).open(encoding="utf-8-sig") as stream:
                        yield parse_plt(stream, user_id, trajectory_id)

    def load_user(self, user_id: str) -> pd.DataFrame:
        return pd.concat(list(self.trajectories(user_id)), ignore_index=True).sort_values(
            ["timestamp", "trajectory_id"], kind="stable").reset_index(drop=True)
