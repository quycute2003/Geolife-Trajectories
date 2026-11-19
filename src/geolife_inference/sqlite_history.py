from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pandas as pd

from . import __version__
from .data import POINT_COLUMNS
from .postgres import HISTORY_POINT_LIMIT, HistoryTooLarge, HistoryUnavailable


POINTS_SCHEMA = """
CREATE TABLE snapshot (id TEXT NOT NULL);
CREATE TABLE gps_points (
    user_id TEXT NOT NULL,
    trajectory_id TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    latitude REAL,
    longitude REAL,
    altitude_m REAL,
    recorded_at_ns INTEGER,
    PRIMARY KEY (user_id, trajectory_id, source_row)
);
"""

LOOKUP_INDEX = "CREATE INDEX gps_points_lookup ON gps_points (user_id, recorded_at_ns, trajectory_id, source_row)"
SCHEMA = POINTS_SCHEMA + LOOKUP_INDEX + ";"

PRECOMPUTED_SCHEMA = """
CREATE TABLE precomputed_inference (
    user_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    config_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    PRIMARY KEY (user_id, model_version, pipeline_version, config_sha256)
) WITHOUT ROWID;
"""


class SQLiteHistory:
    def __init__(self, path: Path):
        self.uri = path.resolve().as_uri() + "?mode=ro"
        try:
            with closing(sqlite3.connect(self.uri, uri=True)) as connection:
                row = connection.execute("SELECT id FROM snapshot").fetchone()
                self.has_precomputed = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'precomputed_inference'"
                ).fetchone() is not None
        except sqlite3.Error as error:
            raise HistoryUnavailable from error
        if row is None or not row[0]:
            raise HistoryUnavailable("SQLite snapshot ID is missing")
        self.snapshot_id = row[0]

    def load_for_inference(
        self, user_id: str, model_version: str, config_sha256: str,
    ) -> dict | pd.DataFrame | None:
        stored = self.load_precomputed(user_id, model_version, config_sha256)
        return stored if stored is not None else self.load_user(user_id)

    def load_precomputed(self, user_id: str, model_version: str, config_sha256: str) -> dict | None:
        if not self.has_precomputed:
            return None
        try:
            with closing(sqlite3.connect(self.uri, uri=True)) as connection:
                row = connection.execute("""
                    SELECT result_json FROM precomputed_inference
                    WHERE user_id = ? AND model_version = ? AND pipeline_version = ? AND config_sha256 = ?
                    """, (user_id, model_version, __version__, config_sha256)).fetchone()
        except sqlite3.Error as error:
            raise HistoryUnavailable from error
        return json.loads(row[0]) if row else None

    def load_user(self, user_id: str) -> pd.DataFrame | None:
        try:
            with closing(sqlite3.connect(self.uri, uri=True)) as connection:
                rows = connection.execute("""
                    SELECT user_id, trajectory_id, latitude, longitude, altitude_m, recorded_at_ns
                    FROM gps_points
                    WHERE user_id = ?
                    ORDER BY recorded_at_ns NULLS LAST, trajectory_id, source_row
                    LIMIT ?
                    """, (user_id, HISTORY_POINT_LIMIT + 1)).fetchall()
        except sqlite3.Error as error:
            raise HistoryUnavailable from error
        if len(rows) > HISTORY_POINT_LIMIT:
            raise HistoryTooLarge
        if not rows:
            return None
        frame = pd.DataFrame.from_records(rows, columns=POINT_COLUMNS)
        for column in ("latitude", "longitude", "altitude_m"):
            frame[column] = frame[column].astype(float)
        frame["timestamp"] = pd.to_datetime(pd.array([row[-1] for row in rows], dtype="Int64"),
                                            unit="ns", utc=True)
        return frame
