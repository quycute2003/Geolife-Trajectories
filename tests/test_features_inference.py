from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dataclasses import replace
import pandas as pd
import pytest

from geolife_inference.clustering import group_locations
from geolife_inference.config import Config
from geolife_inference.features import temporal_summary, union_intervals
from geolife_inference.pipeline import run_pipeline


def stamp(text):
    return datetime.fromisoformat(text)


def test_midnight_weekend_window_overlap():
    result = temporal_summary([(stamp("2024-01-05T15:00:00+00:00"), stamp("2024-01-05T18:00:00+00:00"))], Config())
    assert result["total_dwell_minutes"] == 180
    assert result["night_dwell_minutes"] == 180
    assert result["weekday_dwell_minutes"] == 60
    assert result["weekend_dwell_minutes"] == 120
    assert result["unique_visit_days"] == 2
    assert result["visit_count"] == 1


def test_work_overlap_not_start_hour_assignment():
    result = temporal_summary([(stamp("2024-01-08T00:00:00+00:00"), stamp("2024-01-08T11:00:00+00:00"))], Config())
    assert result["weekday_daytime_dwell_minutes"] == 540
    assert result["night_dwell_minutes"] == 0


def test_union_no_double_count_or_gap_filling():
    intervals = [(stamp("2024-01-01T00:00:00Z"), stamp("2024-01-01T01:00:00Z")),
                 (stamp("2024-01-01T00:30:00Z"), stamp("2024-01-01T01:30:00Z")),
                 (stamp("2024-01-01T02:00:00Z"), stamp("2024-01-01T02:10:00Z"))]
    result = temporal_summary(intervals, Config())
    assert result["total_dwell_minutes"] == 100
    assert result["visit_count"] == 2


def test_dst_elapsed_time():
    zone = ZoneInfo("America/New_York")
    start = datetime(2024, 3, 10, tzinfo=zone)
    end = datetime(2024, 3, 11, tzinfo=zone)
    result = temporal_summary([(start, end)], Config(timezone="America/New_York"))
    assert result["total_dwell_minutes"] == 23 * 60
    assert result["night_dwell_minutes"] == 7 * 60


def test_fall_dst_fold_and_daily_duration():
    zone = ZoneInfo("America/New_York")
    # Same wall-clock hour, distinct UTC instants; must not drop the interval.
    start = datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=0)
    end = datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=1)
    config = Config(timezone="America/New_York")
    assert temporal_summary([(start, end)], config)["night_dwell_minutes"] == 60
    result = temporal_summary([(datetime(2024, 11, 3, tzinfo=zone), datetime(2024, 11, 4, tzinfo=zone))], config)
    assert result["total_dwell_minutes"] == 25 * 60
    assert result["night_dwell_minutes"] == 9 * 60


def recurring_points(make_points):
    frames = []
    # Six dates across two weeks; night and daytime at the same synthetic place.
    for day in (1, 2, 3, 8, 9, 10):
        for hour in (0, 10):
            local = datetime(2024, 1, day, hour, tzinfo=ZoneInfo("Asia/Shanghai"))
            frames.append(make_points(list(range(0, 121, 5)), trajectory=f"{day}-{hour}",
                                      start=local.astimezone(timezone.utc)))
    return pd.concat(frames, ignore_index=True)


@pytest.mark.parametrize("model", ["heuristic-v1", "dbscan-v1"])
def test_home_office_can_match_reproducible_result_and_one_visit_per_episode(make_points, model):
    points = recurring_points(make_points)
    run = run_pipeline(points, "000", model_version=model)
    result = run.result
    assert result["home"]["status"] == result["office"]["status"] == "predicted"
    assert result["home"]["candidate"]["cluster_id"] == result["office"]["candidate"]["cluster_id"]
    assert result["locations"][0]["visit_count"] == 12
    assert result["locations"][0]["stay_event_count"] == 12
    assert result["locations"][0]["unique_visit_days"] == 6
    assert result["pois"] == []
    assert result == run_pipeline(points, "000", model_version=model).result


def test_sparse_and_empty_unknown(make_points):
    for minutes in ([], [0, 5], [0, 5, 10]):
        result = run_pipeline(make_points(minutes), "000").result
        assert result["status"] == "completed"
        assert result["home"]["status"] == result["office"]["status"] == "unknown"
        assert result["home"]["candidate"] is None


def test_dbscan_independent_users_haversine_noise(make_points):
    run = run_pipeline(recurring_points(make_points), "000")
    a = run.stays.iloc[:3].copy()
    a["user_id"] = "A"
    b = run.stays.iloc[:2].copy()
    b["user_id"] = "B"
    grouped = group_locations(pd.concat([a, b], ignore_index=True), Config(), "dbscan-v1")
    assert grouped.loc[grouped.user_id == "A", "cluster_id"].tolist() == [0, 0, 0]
    assert grouped.loc[grouped.user_id == "B", "cluster_id"].tolist() == [-1, -1]
    # About 85m at this latitude: checks radians conversion and meter eps.
    a.loc[a.index[1], "longitude"] += .001
    assert set(group_locations(a, Config(), "dbscan-v1").cluster_id) == {0}


def test_ambiguous_home_abstains(make_points):
    a = recurring_points(make_points)
    b = a.copy()
    b["latitude"] += .1
    b["timestamp"] += pd.Timedelta(hours=3)
    b["trajectory_id"] += "-b"
    result = run_pipeline(pd.concat([a, b]), "000").result
    assert result["home"]["status"] == "unknown"
    assert result["home"]["reason"] == "ambiguous_candidates"
    assert len(result["pois"]) >= 1


def test_multi_user_input_rejected(make_points):
    with pytest.raises(ValueError, match="requested user"):
        run_pipeline(pd.concat([make_points([0]), make_points([0], user="001")]), "000")


def test_dwell_conserved_and_missing_gaps_excluded(make_points):
    points = make_points([0, 5, 10, 100, 105, 110])
    result = run_pipeline(points, "000", model_version="heuristic-v1").result
    assert result["coverage"]["observed_minutes"] == 20
    assert result["locations"][0]["total_dwell_minutes"] == 20
    assert result["locations"][0]["visit_count"] == 2


def test_density_chain_reports_extended_cluster(make_points):
    frames = [make_points(list(range(11)), trajectory=f"t{day}", latitude=39.9 + day * .0008,
                         start=datetime(2024, 1, day + 1, tzinfo=timezone.utc)) for day in range(10)]
    result = run_pipeline(pd.concat(frames), "000").result
    assert result["diagnostics"]["location_clusters"] == 1
    assert result["locations"][0]["radius_max_m"] > 200
    assert "extended_location_clusters" in result["warnings"]


def test_many_samples_and_visits_on_one_day_are_not_recurring_place(make_points):
    frames = [make_points(list(range(11)), trajectory=f"t{hour}",
                         start=datetime(2024, 1, 1, hour, tzinfo=timezone.utc)) for hour in (0, 1, 2, 3)]
    result = run_pipeline(pd.concat(frames), "000").result
    assert result["locations"][0]["cluster_id"] == 0
    assert result["locations"][0]["visit_count"] == 4
    assert result["locations"][0]["unique_visit_days"] == 1
    assert result["home"]["status"] == result["office"]["status"] == "unknown"
    assert result["pois"] == []
