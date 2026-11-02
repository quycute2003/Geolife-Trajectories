# Data dictionary

## GPS point (internal)

| Field | Type / unit | Meaning |
|---|---|---|
| user_id | string | Giữ leading zeros, không trộn users |
| trajectory_id | string | Stem `.plt`, boundary của recording |
| latitude, longitude | float / decimal degrees | WGS84, lat trước lon |
| timestamp | timezone-aware UTC | Parse date/time fields, malformed → NaT trước audit |
| altitude_m | float / m, missing | Feet * 0.3048, -777 là missing |
| gap_seconds | float / s | Chênh thời gian từ điểm trước trong cùng user/trajectory |
| distance_m | float / m | Haversine cùng pair trên; first point missing |
| speed_mps | float / m/s | distance/gap, first point missing |

PLT bỏ sáu header. Fields 3 và 5 không dùng; date/time fields 6/7 là nguồn timestamp.
Malformed column counts bị từ chối; không dùng transportation labels làm Home/Office ground truth.

## Stay-event CSV (private)

`user_id`, `trajectory_id`, `latitude`, `longitude`, `start_time`, `end_time`,
`duration_minutes`, `point_count`, `cluster_id`. Times UTC; duration = end-start.
Point count là số retained GPS fixes, **không phải visit_count**. Noise label là -1.

## Location và result JSON

Schema đầy đủ ở `openapi.yaml`; xem `assumptions.md` để hiểu chính xác cách tính.

| Field group | Definition |
|---|---|
| cluster_id | Local per user/model/run, 0 không mặc định Home |
| stay_event_count | Số stay events thuộc cluster |
| visit_count | Số disjoint union intervals, không lấp GPS gaps |
| unique_visit_days / distinct_weeks | Positive dwell dates / ISO year-weeks ở local zone |
| *_dwell_minutes | Dwell overlap đúng cửa sổ; total = weekday + weekend |
| night_visit_days | Calendar dates có positive night dwell, không phải số đêm nguyên vẹn |
| weekday_daytime_visit_days / weeks | Ngày/ISO tuần có positive work-window dwell |
| mean_visit_duration | Total minutes / visit_count |
| radius_max_m / radius_p95_m | Dispersion stay centers so với representative cluster |
| location.observation_coverage | Cluster visited dates / user GPS-observed dates |
| coverage | User-level observed intervals, dates, span, fractions và role days |
| diagnostics | Input/removed/output counts, gaps/speed, stays/noise/cluster counts |
| home / office | status, reason, nullable candidate và alternatives |
| evidence_score / components | Heuristic strength [0,1], không phải probability |
| pois | Recurring locations khác selected Home/Office |
| locations | Tất cả non-noise clusters, kể cả không đủ recurrence |
| config / versions / warnings | Provenance và assumptions để tái lập |

Invalid coordinate/time counts có thể overlap; `invalid_rows_removed` là union, không cộng hai count.
`duplicate_records_removed` và `conflicting_timestamps_removed` tính sau khi loại invalid.
`noise_proportion=0` khi không có stays là convention; không diễn giải thành clustering tốt.
