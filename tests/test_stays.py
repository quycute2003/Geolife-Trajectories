import pandas as pd
import pytest
from geolife_inference.config import Config
from geolife_inference.preprocessing import preprocess
from geolife_inference.stays import detect_stays


def detect(frame):
    config = Config()
    clean, _ = preprocess(frame, config)
    return detect_stays(clean, config)[0]


@pytest.mark.parametrize("minutes,count", [([0, 1, 2], 0), (list(range(11)), 1),
                                         ([0, 6, 12, 18], 0), ([0, 5, 10], 1),
                                         ([0, 0, 0], 0), ([], 0)])
def test_duration_sampling_and_duplicates(make_points, minutes, count):
    assert len(detect(make_points(minutes))) == count


def test_gap_splits_no_unobserved_dwell(make_points):
    stays = detect(make_points([0, 5, 10, 100, 105, 110]))
    assert stays.duration_minutes.tolist() == [10, 10]
    assert stays.point_count.tolist() == [3, 3]


def test_multiple_stays_jitter_and_last_boundary(make_points):
    frame = make_points(list(range(24)))
    frame.loc[:10, "latitude"] += [0, .0001, -.0001, 0, 0, 0, 0, 0, 0, 0, 0]
    frame.loc[11:, "latitude"] += .02
    stays = detect(frame)
    assert len(stays) == 2
    assert stays.duration_minutes.tolist() == [10, 12]
    assert stays.latitude.iloc[0] == pytest.approx(39.9)


def test_no_cross_trajectory_or_user_stay(make_points):
    frame = pd.concat([make_points([0, 5], trajectory="a"), make_points([10, 15], trajectory="b"),
                       make_points([0, 5], user="other")])
    assert detect(frame).empty


def test_slow_movement_known_failure(make_points):
    frame = make_points(list(range(21)))
    frame["latitude"] += [i * .00005 for i in range(21)]
    # Slow movement can satisfy an anchor radius: explicitly expose this limitation.
    assert not detect(frame).empty


def test_overlapping_files_not_double_counted(make_points):
    frame = pd.concat([make_points([0, 5, 10], trajectory="a"), make_points([1, 6, 11], trajectory="b")])
    clean, _ = preprocess(frame, Config())
    stays, audit = detect_stays(clean, Config())
    assert len(stays) == 1 and audit["overlapping_stays_removed"] == 1
