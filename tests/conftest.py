from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest


@pytest.fixture
def make_points():
    def make(minutes, latitude=39.9, longitude=116.3, user="000", trajectory="t", start=None):
        start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
        return pd.DataFrame({"user_id": user, "trajectory_id": trajectory,
                             "latitude": [latitude] * len(minutes), "longitude": [longitude] * len(minutes),
                             "altitude_m": 0.0,
                             "timestamp": [start + timedelta(minutes=m) for m in minutes]})
    return make
