from io import StringIO
from zipfile import ZipFile
import numpy as np
import pandas as pd
import pytest

from geolife_inference.config import Config
from geolife_inference.data import GeoLifeSource, parse_plt
from geolife_inference.geo import haversine_m, representative
from geolife_inference.preprocessing import preprocess

HEADER = "\n".join(["header"] * 6) + "\n"


def test_plt_utc_altitude_order_and_invalid_values():
    text = HEADER + "39,116,0,100,0,2024-01-01,00:01:00\n39,116,0,-777,0,2024-01-01,00:00:00\nbad,116,0,0,0,bad,bad\n"
    frame = parse_plt(StringIO(text), "001", "abc")
    assert frame.user_id.tolist() == ["001"] * 3
    assert frame.trajectory_id.tolist() == ["abc"] * 3
    assert str(frame.timestamp.dtype) == "datetime64[ns, UTC]"
    assert pd.isna(frame.altitude_m.iloc[0])
    assert frame.altitude_m.iloc[1] == pytest.approx(30.48)
    clean, audit = preprocess(frame, Config())
    assert len(clean) == 2 and audit["invalid_rows_removed"] == 1


def test_empty_and_malformed_plt():
    assert parse_plt(StringIO(HEADER), "u", "t").empty
    with pytest.raises(ValueError):
        parse_plt(StringIO(HEADER + "1,2,3\n"), "u", "t")


def test_zip_and_directory_sources_equivalent(tmp_path):
    name = "Data/007/Trajectory/a.plt"
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_text(HEADER + "39,116,0,0,0,2024-01-01,00:00:00\n", encoding="utf-8")
    archive = tmp_path / "fixture.zip"
    with ZipFile(archive, "w") as z:
        z.write(path, name)
    pd.testing.assert_frame_equal(GeoLifeSource(tmp_path / "Data").load_user("007"),
                                  GeoLifeSource(archive).load_user("007"))
    assert GeoLifeSource(archive).inventory()["trajectory_count"] == 1
    with pytest.raises(ValueError, match="Unknown user"):
        GeoLifeSource(archive).load_user("008")


def test_haversine_units_and_dateline():
    assert haversine_m(0, 0, 0, 1) == pytest.approx(111195.08, abs=.1)
    assert haversine_m(90, 0, 90, 180) < 1e-6
    assert haversine_m(0, 179.999, 0, -179.999) < 223
    lat, lon = representative(np.array([[1, 179.999], [1, -179.999]]))
    assert abs(lon) == pytest.approx(180)
    assert haversine_m(0, 0, np.array([0, 0]), np.array([0, 1])).tolist() == pytest.approx([0, 111195.08], abs=.1)


def test_audit_duplicate_conflict_invalid_and_speed_not_deleted(make_points):
    frame = make_points([0, 1, 2, 3])
    frame.loc[1, "longitude"] = 120
    frame.loc[2, "latitude"] = np.inf
    frame.loc[3, "timestamp"] = pd.NaT
    duplicate = frame.iloc[[0]].copy()
    conflict = duplicate.copy()
    conflict["latitude"] = 40
    clean, audit = preprocess(pd.concat([frame, duplicate, conflict]), Config())
    assert len(clean) == 2
    assert audit["duplicate_records_removed"] == 1
    assert audit["conflicting_timestamps_removed"] == 1
    assert audit["invalid_rows_removed"] == 2
    assert audit["high_speed_segments"] == 1


def test_naive_and_non_utc_rejected(make_points):
    frame = make_points([0, 1])
    frame["timestamp"] = ["2024-01-01T00:00:00", "2024-01-01T00:00:00+08:00"]
    clean, audit = preprocess(frame, Config())
    assert clean.empty and audit["invalid_timestamps"] == 2


@pytest.mark.parametrize("kwargs", [{"distance_m": 0}, {"eps_m": float("nan")}, {"min_samples": True},
                                   {"night_start_hour": 3}, {"work_end_hour": 4}])
def test_bad_config(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)
