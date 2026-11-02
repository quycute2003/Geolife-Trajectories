# Phase reports — CP1, 2026-10-31

## Phase 1 — Setup, loader, EDA

**Completed:** package Python, ZIP/directory loader, source review và real subset EDA; full ZIP inventory/CRC.

**Files Changed:** `pyproject.toml`, `uv.lock`, `.gitignore`, `.gitattributes`, `configs/baseline.toml`,
`data.py`, `config.py`, loader tests, `docs/research_notes.md`, `docs/data_dictionary.md`.

**Technical Decisions:** dùng `py`, isolated `.venv`, dependency lock; không giải nén toàn bộ;
UTC timestamp và feet→meters; raw invalid values được giữ tới preprocessing audit.

**Validation:** imports, synthetic ZIP/directory equivalence, real EDA users 000/001/002;
182 users / 18.670 PLT / 24.876.978 record lines thực tế. Tests Phase 1 nằm trong final suite.

**Limitations:** toàn ZIP mới đếm dòng/CRC; không validate mọi coordinate/time. Labels không phải Home/Office.

**Next Steps:** preprocessing audit, distances và gap semantics; đã thực hiện ở Phase 2.

## Phase 2 — Preprocessing

**Completed:** coordinate/time validation, duplicates/conflicts, Haversine, sampling/speed diagnostics.

**Files Changed:** `preprocessing.py`, `geo.py`, `tests/test_data_preprocessing.py`, `docs/assumptions.md`.

**Technical Decisions:** không xóa high-speed points; tie-break conflicting timestamps deterministic;
không nối các trajectory. Invalid-removal counts tách rõ union và overlapping rule counts.

**Validation:** distance units, vector/scalar broadcasting, date line, poles, malformed/naive/non-UTC time,
invalid/duplicate/conflicting records. EDA thật ghi audit và quantiles; tham chiếu results.md.

**Limitations:** invalid fix removal có thể để lại short adjacent intervals; tốc độ chỉ là diagnostic.

**Next Steps:** stay detector tôn trọng gaps/boundaries; đã thực hiện ở Phase 3.

## Phase 3 — Stay detection

**Completed:** anchor scan, robust representative, last in-radius end, boundary flush, overlap audit.

**Files Changed:** `stays.py`, `tests/test_stays.py`, assumptions và experiment script.

**Technical Decisions:** initial 100m/10min/5min, không coi là optimal; reject later overlapping stays.

**Validation:** short/long stays, jitter, duplicates, sparse sampling, long gaps, multiple stays,
user/trajectory separation và end boundary. Suite Phase 2–3 đầu tiên: 22 passed.
Real baseline: 120/44/188/0 stays ở users 000/001/002/049.

**Limitations:** slow movement có thể trở thành stay; greedy reset có thể bỏ lỡ một số stops.

**Next Steps:** grouping và temporal inference; đã thực hiện ở Phase 4.

## Phase 4 — Grouping, temporal features, inference

**Completed:** hai model versions, local windows, coverage, score components, abstention/POI, CLI JSON/CSV.

**Files Changed:** `clustering.py`, `features.py`, `inference.py`, `pipeline.py`, `cli.py`, `__main__.py`,
`tests/test_features_inference.py`.

**Technical Decisions:** stay-level Haversine DBSCAN per user; heuristic nearest fixed-anchor grouping;
time-window overlap và interval unions; score không phải probability; Home/Office có thể trùng.

**Validation:** noise/per-user clustering, radians/meters, midnight/weekend, spring/fall DST,
shared Home/Office synthetic case, unknown/empty, ambiguity và deterministic outputs.
Trước API tests: 33 passed. Real baseline Home candidates ở 3/4 users, Office unknown 4/4.

**Limitations:** night/work windows, missing indoor data, travel và confidence weights cần review.

**Next Steps:** sensitivity experiments, manual support và contract; đã thực hiện ở Phase 5.

## Phase 5 — Evaluation, documentation, OpenAPI

**Completed:** 32 actual experiment runs; offline maps và review template; mở xem bốn baseline DBSCAN maps;
research/architecture/evaluation docs; OpenAPI 3.1, examples và mentor checklist.

**Files Changed:** `evaluation.py`, `scripts/`, `tests/test_contract_cli.py`, `openapi.yaml`, `README.md`,
`docs/`, `reports/cp1/`, cập nhật `PLAN.md`.

**Technical Decisions:** report diagnostics và sensitivity, không đo accuracy thiếu nhãn;
unknown là success 200, invalid requests là errors; inline one-user input, limits/security là proposal.

**Validation:** final pytest **48 passed**; OpenAPI structure valid;
**14 examples/responses** qua JSON Schema + formats (gồm tám real-data model outputs);
`uv lock --check` thành công. Real user 001 rerun tái tạo output chính xác; tám real outputs
thỏa dwell/audit invariants. Kiểm tra Git ignore đối với private artifacts và môi trường.

**Limitations:** manual semantic labels/reviewer độc lập chưa có; full-dataset inference chưa chạy;
OpenAPI chưa mentor-approved; không có endpoints để test auth/load/resource enforcement.

**Next Steps:** người dùng chuyển OpenAPI và report cho mentor, ghi feedback/approval.
**Dừng tại API approval gate.** Không gửi mentor tự động, không push GitHub.

## Cập nhật notebook 02 — 2026-11-02

**Completed:** tạo và chạy `02_preprocessing.ipynb` (25 cells/13 code), hai chart trước–sau;
đồng thời bỏ các câu hỏi tự kiểm tra trong notebook 01 theo yêu cầu.

**Files Changed:** notebook 01/02, hướng dẫn notebooks, README và PLAN. Artifacts preprocessing chứa
hai PNG, audit JSON, cleaned CSV gzip và removed rows CSV; không thêm helper scripts hoặc bản notebook phụ.

**Technical Decisions:** cùng subset users 000/001/002; giữ missing altitude; invalid → duplicate → timestamp conflict;
tie-break lat/lon của baseline có ghi giới hạn và đối chiếu phương án bỏ toàn nhóm. Gap/speed là flags, không lọc rows.

**Validation:** cả hai notebook chạy từ kernel mới không cần GEOLIFE_DATASET, không có cell errors.
Notebook 02 khớp core preprocessing; 530.694 input → 530.691 retained + 3 removed.
Đọc lại CSV kiểm tra đủ counts/leading-zero IDs, một altitude missing, 94 high-speed pairs và 1.425 long gaps.
Hai chart đã xem; audit/source rows conserved; không sửa PLT gốc.

**Limitations:** không có nhãn xác nhận fix nào đúng trong conflict; chưa kết luận quality toàn bộ 182 users.
Before/after positive intervals không phải calendar time coverage hoặc accuracy.

**Next Steps:** stay detection trên các đoạn quan sát, khi người dùng yêu cầu tiếp; chưa tạo notebook 03.

## Thay phạm vi notebook 02 — chờ người dùng chạy

Người dùng yêu cầu bỏ giới hạn ba users: mọi xử lý mới phải áp dụng toàn dataset.
Đã sửa notebook 02 duyệt toàn bộ source.by_user và mọi trajectory, ghi CSV nén theo luồng,
audit từng user/tổng hợp và ECDF từ mọi positive pair. Outputs subset trong notebook đã được bỏ.
**Theo yêu cầu, chỉ sửa notebook, không chạy dữ liệu.** Chỉ validate cấu trúc notebook và compile cú pháp các cells.
Chưa có số liệu preprocessing toàn dataset; artifact subset cũ chỉ là lịch sử, không phải kết quả full.
Người dùng chạy notebook và xác nhận audit completed với đủ users/trajectory files trước khi kết luận.

## Sửa timestamp-conflict policy trong NB02

Đã thay chọn lat/lon nhỏ nhất bằng hai bước: scan maximum pairwise spread của mọi conflict group
trên toàn dataset; sau khi đặt ngưỡng, mean nhóm gần và cách ly nhóm xa có truy vết.
Ngưỡng mặc định None; Run All chưa đặt ngưỡng chỉ scan, không báo cleaning hoàn tất.
Counts tách invalid/duplicate removals, merged extras và unresolved rows; points gộp có source_point_count,
nhóm chưa giải quyết được lưu và làm ngắt observation segment.

Validation: cấu trúc/cú pháp notebook hợp lệ, outputs clear. Bảy synthetic cases pass: near mean,
far quarantine/segment break, duplicates+invalid, date line+missing altitude, all-invalid, empty input,
unset threshold. Không đọc/chạy dữ liệu GeoLife. Core/CLI raw và stay detector chưa đổi policy;
chỉ gọi core preprocessing sau khi notebook đã xử lý hết conflicts.
