"""Core vs NB02's visible reference code, without running notebook/data jobs."""
import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from geolife_inference.clustering import group_locations
from geolife_inference.config import Config
from geolife_inference.data import POINT_COLUMNS
from geolife_inference.features import cluster_features, observation_coverage
from geolife_inference.geo import haversine_m
from geolife_inference.inference import infer_locations
from geolife_inference.pipeline import run_pipeline
from geolife_inference.preprocessing import (AUDIT_COUNTS, TIME_KEYS, diagnose_resolved_points,
                                            preprocess_with_trace)
from geolife_inference.stays import detect_stays

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def reference():
    notebook = json.loads((ROOT / "notebooks/02_preprocessing.ipynb").read_text(encoding="utf-8"))
    names = {"split_basic", "conflict_groups", "group_id", "group_diameter_m", "mean_coordinate",
             "choose_conflict_points", "clean_trajectory"}
    definitions = []
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            source = cell["source"]
            tree = ast.parse("".join(source) if isinstance(source, list) else source)
            definitions.extend(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names)
    assert {node.name for node in definitions} == names
    namespace = dict(pd=pd, np=np, haversine_m=haversine_m, POINT_COLUMNS=POINT_COLUMNS,
                     KEYS=[*TIME_KEYS, "latitude", "longitude"], TIME_KEYS=TIME_KEYS,
                     config=Config(), preprocess=diagnose_resolved_points)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "NB02-reference-functions", "exec"), namespace)

    def clean(raw, config):
        namespace["config"] = config
        raw = raw.copy().reset_index(drop=True)
        raw["record_id"] = np.arange(len(raw), dtype=np.int64)
        points, removed, traces = [], [], []
        counts = dict.fromkeys(AUDIT_COUNTS, 0)
        frames = [f for _, f in raw.groupby(["user_id", "trajectory_id"], sort=True)] or [raw]
        for frame in frames:
            distinct = namespace["split_basic"](frame)[0]
            lookup = {namespace["group_id"](g): dict(distinct_positions=len(g), spread_m=namespace["group_diameter_m"](g))
                      for _, g in namespace["conflict_groups"](distinct)}
            p, r, t, audit = namespace["clean_trajectory"](frame, config.conflict_merge_threshold_m, lookup)
            points.append(p)
            removed.append(r)
            traces.append(t)
            for k, value in audit.items():
                counts[k] += value

        def combine(frames):
            nonempty = [f for f in frames if not f.empty]
            return pd.concat(nonempty, ignore_index=True) if nonempty else frames[0].iloc[:0].copy()
        return combine(points), combine(removed), combine(traces), counts
    return clean


def case(name):
    start = pd.Timestamp("2024-01-01", tz="UTC")
    def row(minute, meters=0, trajectory="t", latitude=None, longitude=116.3, altitude=0):
        return dict(user_id="000", trajectory_id=trajectory,
                    latitude=39.9 + meters / 111195.08 if latitude is None else latitude,
                    longitude=longitude, altitude_m=altitude,
                    timestamp=start + pd.Timedelta(minutes=minute))
    if name == "near":
        rows = [row(0), row(0, 10), row(5), row(10)]
    elif name == "majority":
        rows = [row(0, m) for m in [0, 2, 4, 1000]] + [row(5), row(10)]
    elif name == "context":
        rows = [row(-1, 1000), *[row(0, m) for m in [0, 2, 1000, 1002]],
                row(1, 1000), row(5, 1000), row(10, 1000)]
    elif name == "tie":
        rows = [row(m, 10000) for m in [-11, -6, -1]] + [row(0), row(0, 1000)] + [row(m, 10000) for m in [1, 6, 11]]
    elif name == "chain":
        rows = [row(0, m) for m in [0, 15, 30]]
    elif name == "context_tie":
        rows = [row(0, m) for m in [0, 15, 30]] + [row(1, 15)]
    elif name == "dateline":
        rows = [row(0, latitude=0, longitude=lon, altitude=np.nan) for lon in [179.99995, -179.99995]]
        rows += [row(m, latitude=0, longitude=-180) for m in [5, 10]]
    elif name == "invalid":
        rows = [row(0), row(0, altitude=123), row(5), row(5, 2), row(10), row(3, latitude=np.inf), row(4)]
        rows[-1]["timestamp"] = pd.NaT
    elif name == "all_invalid":
        rows = [row(0, latitude=np.inf)]
    elif name == "other_trajectory":
        rows = [row(0), row(0, 1000), row(-1, trajectory="other"), row(1, trajectory="other")]
    elif name == "recurring":
        rows = []
        for day in [1, 2, 3, 8, 9, 10]:
            for role, offset, meters, duration in [("home", 16 * 60, 0, 120),
                                                  ("office", 26 * 60, 1000, 120),
                                                  ("poi", 35 * 60, 2000, 30)]:
                minute = (day - 1) * 1440 + offset
                trajectory = f"{day:02d}-{role}"
                rows.extend(row(minute + m, meters, trajectory) for m in range(0, duration + 1, 5))
                if role == "home":
                    rows.append(row(minute, 2, trajectory))
    elif name == "empty":
        rows = []
    else:
        raise ValueError(name)
    df = pd.DataFrame(rows, columns=POINT_COLUMNS)
    for c in ["latitude", "longitude", "altitude_m"]:
        df[c] = pd.to_numeric(df[c])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


CASES = ["near", "majority", "context", "tie", "chain", "context_tie", "dateline",
         "invalid", "all_invalid", "other_trajectory", "recurring", "empty"]


def compare_frames(actual, expected, columns, sort):
    a = actual[columns].sort_values(sort, kind="stable").reset_index(drop=True)
    b = expected[columns].sort_values(sort, kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False, atol=1e-9, rtol=1e-12)


@pytest.mark.parametrize("name", CASES)
def test_core_preprocessing_matches_nb02_reference(reference, name):
    raw, config = case(name), Config()
    expected, removed, traces, audit = reference(raw, config)
    run = preprocess_with_trace(raw, config)
    point_columns = [*POINT_COLUMNS, "record_id", "coordinate_merged", "source_point_count", "gap_seconds",
                     "distance_m", "speed_mps", "gap_over_limit", "high_speed_flag",
                     "segment_break_due_to_conflict", "observation_segment"]
    compare_frames(run.points, expected, point_columns, ["user_id", "trajectory_id", "timestamp"])
    compare_frames(run.removed_points, removed, [*POINT_COLUMNS, "record_id", "reason"], ["record_id"])
    compare_frames(run.conflict_points, traces, [*POINT_COLUMNS, "record_id", "conflict_group_id", "spread_m",
                                                "decision", "output_record_id"], ["record_id"])
    assert {k: run.audit[k] for k in audit} == audit
    assert run.audit["input_points"] == (run.audit["output_points"] + run.audit["invalid_rows_removed"]
        + run.audit["duplicate_records_removed"] + run.audit["merged_extra_points"] + run.audit["unresolved_conflict_rows"])


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("model", ["heuristic-v1", "dbscan-v1"])
def test_one_call_pipeline_matches_notebook_stages(reference, name, model):
    raw, config = case(name), Config()
    cleaned, _, _, _ = reference(raw, config)
    stays, stay_audit = detect_stays(cleaned, config)
    grouped = group_locations(stays, config, model)
    coverage = observation_coverage(cleaned, config)
    features = cluster_features(grouped, coverage, config)
    prediction = infer_locations(features, coverage, config)
    run = run_pipeline(raw, "000", config, model)
    assert run.result["coverage"] == coverage
    assert run.result["locations"] == features
    for key, value in prediction.items():
        assert run.result[key] == value
    if name == "recurring":
        assert run.result["home"]["status"] == run.result["office"]["status"] == "predicted"
        assert len(run.result["pois"]) == 1
    pd.testing.assert_frame_equal(run.stays, grouped, check_dtype=False)
    assert run.result["diagnostics"]["overlapping_stays_removed"] == stay_audit["overlapping_stays_removed"]


def test_unresolved_timestamp_breaks_both_stays_and_coverage():
    run = run_pipeline(case("tie"), "000")
    assert run.stays.duration_minutes.tolist() == [10, 10]
    assert run.result["coverage"]["observed_minutes"] == 20
    assert run.conflict_points.decision.eq("unresolved_tie").all()
    assert run.result["diagnostics"]["breaks_due_to_conflict"] == 1


def test_diagnostics_bridge_preserves_mean_provenance_and_rejects_unresolved():
    run = preprocess_with_trace(case("near"), Config())
    clean, _ = diagnose_resolved_points(run.points, Config())
    assert clean.source_point_count.tolist() == run.points.source_point_count.tolist()
    with pytest.raises(ValueError, match="must be resolved"):
        diagnose_resolved_points(case("near"), Config())


def test_pipeline_id_does_not_depend_on_row_provenance_order():
    raw = case("near")
    first = run_pipeline(raw, "000")
    second = run_pipeline(raw.sample(frac=1, random_state=9), "000")
    assert first.result["inference_id"] == second.result["inference_id"]
    assert first.result["home"] == second.result["home"]


@pytest.mark.parametrize("threshold", [0, 5, 50])
def test_configurable_conflict_threshold_matches_reference(reference, threshold):
    raw, config = case("near"), Config(conflict_merge_threshold_m=threshold)
    points, _, _, audit = reference(raw, config)
    actual = preprocess_with_trace(raw, config)
    compare_frames(actual.points, points, [*POINT_COLUMNS, "source_point_count", "coordinate_merged"], TIME_KEYS)
    assert {k: actual.audit[k] for k in audit} == audit
