import json
import re

import pandas as pd
import pytest

from geolife_inference.config import Config
from geolife_inference.maps import write_location_map


def map_inputs():
    stays = pd.DataFrame({
        "user_id": ["000", "001"], "stay_id": ["000_s1", "001_s1"],
        "latitude": [39.9, 40.0], "longitude": [116.3, 116.4],
        "duration_minutes": [10.0, 20.0],
        "start_time": ["2024-01-01T00:00:00Z"] * 2,
        "end_time": ["2024-01-01T00:10:00Z", "2024-01-01T00:20:00Z"],
        "heuristic-v1_cluster_id": [0, 0], "dbscan-v1_cluster_id": [-1, -1],
    })
    places = pd.DataFrame([
        dict(method="heuristic-v1", user_id=u, cluster_id=0, latitude=lat, longitude=lon,
             stay_event_count=1, visit_count=1, unique_visit_days=1,
             total_dwell_minutes=minutes, radius_max_m=0.0)
        for u, lat, lon, minutes in [("000", 39.9, 116.3, 10.0), ("001", 40.0, 116.4, 20.0)]
    ])
    return stays, places


def payload(path):
    match = re.search(r'<script type="application/json" id="map-data">(.*?)</script>',
                      path.read_text(encoding="utf-8"), re.S)
    return json.loads(match[1])


def test_map_preserves_all_users_assignments_and_noise(tmp_path):
    stays, places = map_inputs()
    original = stays.copy(deep=True)
    target = write_location_map(stays, places, ["000", "001", "empty"], tmp_path / "map.html", Config())
    data = payload(target)
    assert data["users"] == ["000", "001", "empty"]
    assert len(data["stays"]) == 2 and len(data["locations"]) == 2
    assert [r["dbscan-v1_cluster_id"] for r in data["stays"]] == [-1, -1]
    assert [r["user_id"] for r in data["locations"]] == ["000", "001"]
    assert data["stays"][0]["start_time"] == "2024-01-01T00:00:00+00:00"
    assert not target.with_suffix(".html.partial").exists()
    pd.testing.assert_frame_equal(stays, original)


def test_map_supports_no_stays_or_locations(tmp_path):
    stays, places = map_inputs()
    target = write_location_map(stays.iloc[:0], places.iloc[:0], ["000"], tmp_path / "empty.html", Config())
    data = payload(target)
    assert data["users"] == ["000"] and data["stays"] == data["locations"] == []


def test_map_embedded_text_cannot_close_data_script(tmp_path):
    stays, places = map_inputs()
    text = '</script><script>alert("test")</script>'
    stays.loc[0, "stay_id"] = text
    target = write_location_map(stays, places, ["000", "001"], tmp_path / "escaped.html", Config())
    assert text not in target.read_text(encoding="utf-8")
    assert payload(target)["stays"][0]["stay_id"] == text


def test_map_rejects_incomplete_user_list_and_duplicate_stays(tmp_path):
    stays, places = map_inputs()
    with pytest.raises(ValueError, match="outside"):
        write_location_map(stays, places, ["000"], tmp_path / "map.html", Config())
    stays["stay_id"] = "same"
    with pytest.raises(ValueError, match="stay IDs"):
        write_location_map(stays, places, ["000", "001"], tmp_path / "map.html", Config())


def test_map_can_label_same_cluster_home_and_office(tmp_path):
    stays, places = map_inputs()
    labels = pd.DataFrame([dict(method="heuristic-v1", user_id="000", cluster_id=0, role=r)
                           for r in ("home", "office")])
    target = write_location_map(stays, places, ["000", "001"], tmp_path / "roles.html", Config(), role_labels=labels)
    data = payload(target)
    assert data["has_roles"] and [r["role"] for r in data["role_labels"]] == ["home", "office"]
    assert len(data["stays"]) == 2 and len(data["locations"]) == 2


def test_map_does_not_invent_unknown_locations(tmp_path):
    stays, places = map_inputs()
    labels = pd.DataFrame(columns=["method", "user_id", "cluster_id", "role"])
    target = write_location_map(stays, places, ["000", "001"], tmp_path / "unknown.html", Config(), role_labels=labels)
    assert payload(target)["has_roles"] and payload(target)["role_labels"] == []
    bad = pd.DataFrame([dict(method="dbscan-v1", user_id="000", cluster_id=-1, role="home")])
    with pytest.raises(ValueError, match="existing non-noise"):
        write_location_map(stays, places, ["000", "001"], tmp_path / "bad.html", Config(), role_labels=bad)
