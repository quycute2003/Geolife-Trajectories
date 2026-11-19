"""Import and read one user's raw GeoLife history in PostgreSQL."""
import hashlib
import json

import pandas as pd

from . import __version__
from .data import POINT_COLUMNS


DEFAULT_SNAPSHOT = "geolife-1.3"
HISTORY_POINT_LIMIT = 100_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS geolife_histories (
    snapshot_id text NOT NULL,
    user_id text COLLATE "C" NOT NULL,
    source_sha256 text NOT NULL,
    PRIMARY KEY (snapshot_id, user_id)
);
CREATE TABLE IF NOT EXISTS geolife_gps_points (
    snapshot_id text NOT NULL,
    user_id text COLLATE "C" NOT NULL,
    trajectory_id text COLLATE "C" NOT NULL,
    source_row integer NOT NULL CHECK (source_row > 0),
    latitude double precision,
    longitude double precision,
    altitude_m double precision,
    recorded_at timestamp with time zone,
    PRIMARY KEY (snapshot_id, user_id, trajectory_id, source_row),
    FOREIGN KEY (snapshot_id, user_id) REFERENCES geolife_histories
);
CREATE INDEX IF NOT EXISTS geolife_gps_history_order
    ON geolife_gps_points (snapshot_id, user_id, recorded_at, trajectory_id, source_row);
CREATE TABLE IF NOT EXISTS geolife_precomputed_inference (
    snapshot_id text NOT NULL,
    user_id text COLLATE "C" NOT NULL,
    model_version text NOT NULL,
    pipeline_version text NOT NULL,
    config_sha256 text NOT NULL,
    result_json jsonb NOT NULL,
    PRIMARY KEY (snapshot_id, user_id, model_version, pipeline_version, config_sha256),
    FOREIGN KEY (snapshot_id, user_id) REFERENCES geolife_histories (snapshot_id, user_id)
);
"""

READ_POINTS_SQL = """
SELECT user_id, trajectory_id, latitude, longitude, altitude_m, recorded_at
FROM geolife_gps_points
WHERE snapshot_id = %s AND user_id = %s
ORDER BY recorded_at, trajectory_id, source_row
LIMIT %s
"""

# Enumerate the imported users using the GPS index and the Knative reader's existing SELECT grant.
READ_GPS_USERS_SQL = """
WITH RECURSIVE ids(user_id) AS (
    (SELECT user_id FROM geolife_gps_points WHERE snapshot_id = %s ORDER BY user_id LIMIT 1)
    UNION ALL
    SELECT next_id.user_id
    FROM ids CROSS JOIN LATERAL (
        SELECT user_id FROM geolife_gps_points
        WHERE snapshot_id = %s AND user_id > ids.user_id
        ORDER BY user_id LIMIT 1
    ) AS next_id
)
SELECT user_id FROM ids WHERE user_id ~ '^[0-9]{3}$' ORDER BY user_id
"""


class HistoryUnavailable(Exception):
    """PostgreSQL is unreachable or the history schema is missing."""


class HistoryTooLarge(Exception):
    """The full history exceeds the local inference limit."""


class PostgresHistory:
    def __init__(self, dsn: str, snapshot_id: str = DEFAULT_SNAPSHOT):
        import psycopg

        if not snapshot_id.strip() or len(snapshot_id) > 128:
            raise ValueError("snapshot_id must contain 1 to 128 characters")
        self.driver = psycopg
        self.dsn = dsn
        self.snapshot_id = snapshot_id

    def import_user(self, source, user_id: str) -> tuple[int, bool]:
        frame = source.load_user(user_id, include_source_row=True)
        if frame.empty:
            raise ValueError(f"No GPS records for user {user_id}")
        fingerprint = hashlib.sha256(
            pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="<u8").tobytes()
        ).hexdigest()
        with self.driver.connect(self.dsn, connect_timeout=5) as connection, connection.cursor() as cursor:
            # Serialize initialization even if several users are imported into a new DB at once.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('geolife_gps_points'))")
            cursor.execute(SCHEMA)
            cursor.execute("""
                INSERT INTO geolife_histories (snapshot_id, user_id, source_sha256)
                VALUES (%s, %s, %s)
                ON CONFLICT (snapshot_id, user_id) DO NOTHING
                RETURNING source_sha256
                """, (self.snapshot_id, user_id, fingerprint))
            if cursor.fetchone() is None:
                cursor.execute("""
                    SELECT source_sha256 FROM geolife_histories
                    WHERE snapshot_id = %s AND user_id = %s
                    """, (self.snapshot_id, user_id))
                if cursor.fetchone()[0] != fingerprint:
                    raise ValueError("This snapshot already contains different GPS records for this user.")
                return len(frame), False

            rows = frame.astype(object).where(frame.notna(), None)
            with cursor.copy("""
                COPY geolife_gps_points
                    (snapshot_id, user_id, trajectory_id, latitude, longitude, altitude_m, recorded_at, source_row)
                FROM STDIN
                """) as copy:
                for row in rows.itertuples(index=False, name=None):
                    copy.write_row((self.snapshot_id, *row))
        return len(frame), True

    def load_user(self, user_id: str) -> pd.DataFrame | None:
        return self.load_for_inference(user_id)

    def list_users(self) -> list[str]:
        try:
            with self.driver.connect(self.dsn, connect_timeout=5, autocommit=True) as connection:
                rows = connection.execute(READ_GPS_USERS_SQL, (self.snapshot_id, self.snapshot_id)).fetchall()
        except (self.driver.OperationalError, self.driver.errors.UndefinedTable,
                self.driver.errors.InsufficientPrivilege) as error:
            raise HistoryUnavailable from error
        return [user_id for (user_id,) in rows]

    def load_for_inference(
        self, user_id: str, model_version: str | None = None, config_sha256: str | None = None,
    ) -> dict | pd.DataFrame | None:
        try:
            with self.driver.connect(self.dsn, connect_timeout=5, autocommit=True) as connection:
                if model_version is not None:
                    try:
                        result = connection.execute("""
                            SELECT result_json::text FROM geolife_precomputed_inference
                            WHERE snapshot_id = %s AND user_id = %s AND model_version = %s
                              AND pipeline_version = %s AND config_sha256 = %s
                            """, (self.snapshot_id, user_id, model_version, __version__, config_sha256)).fetchone()
                    except self.driver.errors.UndefinedTable:
                        # Snapshots created before precomputed inference still serve on demand.
                        result = None
                    if result is not None:
                        return json.loads(result[0])
                rows = connection.execute(
                    READ_POINTS_SQL, (self.snapshot_id, user_id, HISTORY_POINT_LIMIT + 1)
                ).fetchall()
        except (self.driver.OperationalError, self.driver.errors.UndefinedTable) as error:
            raise HistoryUnavailable from error
        if len(rows) > HISTORY_POINT_LIMIT:
            raise HistoryTooLarge
        if not rows:
            return None
        frame = pd.DataFrame.from_records(rows, columns=POINT_COLUMNS)
        for column in ("latitude", "longitude", "altitude_m"):
            frame[column] = frame[column].astype(float)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame
