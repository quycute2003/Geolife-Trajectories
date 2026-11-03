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
research/architecture/evaluation docs; OpenAPI 3.1 và examples.

**Files Changed:** `evaluation.py`, `scripts/`, `tests/test_contract_cli.py`, `openapi.yaml`, `README.md`,
`docs/`, `reports/cp1/`, cập nhật `PLAN.md`.

**Technical Decisions:** report diagnostics và sensitivity, không đo accuracy thiếu nhãn;
unknown là success 200, invalid requests là errors; inline one-user input, limits/security là proposal.

**Validation:** final pytest **48 passed**; OpenAPI structure valid;
**14 examples/responses** qua JSON Schema + formats (gồm tám real-data model outputs);
`uv lock --check` thành công. Real user 001 rerun tái tạo output chính xác; tám real outputs
thỏa dwell/audit invariants. Kiểm tra Git ignore đối với private artifacts và môi trường.

**Limitations:** manual semantic labels/reviewer độc lập chưa có; full-dataset inference chưa chạy;
OpenAPI là bản thiết kế; không có endpoints để test auth/load/resource enforcement.

**Next Steps:** người dùng trình bày trực tiếp OpenAPI và report. Không có endpoints hoặc GitHub push.

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

## Notebook 03 — stay detection toàn cleaned dataset (2026-11-02)

NB02 đã được người dùng chạy đủ 182 users / 18.670 trajectories, còn 24.177.772 cleaned points.
Tạo `03_stay_detection.ipynb` đọc input đó theo từng trajectory, kể cả khi trajectory vắt qua
hai khối CSV. Rule baseline: anchor radius 100 m, ít nhất 10 phút, gap tối đa 5 phút.
Detector đã tôn trọng `observation_segment` của NB02 để không nối qua conflict chưa giải quyết.

Candidate stays của cùng user được sắp theo thời gian; giữ lần bắt đầu trước, lưu riêng các lần
chồng thời gian thay vì đếm trùng hoặc cắt endpoint không có GPS chứng minh.
Notebook xuất stays, overlaps, per-user counts, audit đủ phạm vi và hai chart tổng hợp toàn dataset.
Sensitivity tùy chọn đổi radius/duration từng yếu tố; mỗi cấu hình vẫn full-data.

Validation: 53 pytest tests pass; notebook hợp lệ và compile được mọi code cell. Synthetic integration
kiểm tra khối đọc 1/2/3/4/100 rows, ngắt segment, overlap, không có stay, hai chart, sensitivity
và từ chối coverage thiếu. Chỉ dùng dữ liệu giả trong kiểm tra, không thực thi GeoLife.
Chưa có số stays hoặc kết luận thực nghiệm toàn dataset. Người dùng tự chạy NB03 trước khi review
và chuyển sang clustering ở phase 4. Không tạo HTTP endpoints hoặc tự push thay đổi phase 3.

## Người dùng hoàn tất NB03; tạo NB04 — 2026-11-02

Đã đọc audit/CSV từ lượt chạy của người dùng: 182 users / 18.670 trajectories / 24.177.772 points.
Baseline 10.339 stays ở 151 users, 0 overlap, 3.592,999 giờ; 2.595.092 points thuộc stays.
Sensitivity năm cấu hình dùng toàn dataset, không overlap; kết quả chi tiết trong `results.md`.
Người dùng đã review số lượng/ý nghĩa và cho phép chuyển phase; chưa coi ngưỡng là tối ưu.

Tạo `04_location_grouping.ipynb` so heuristic-v1 với dbscan-v1 trên cùng toàn bộ stays, mỗi user riêng.
Baseline eps 100 m / min_samples 3 (tính bằng stays, có chính nó). Giữ noise trong assignments;
tạo bảng địa điểm, đợt ghé, ngày ghé Asia/Shanghai, tổng dwell và radius max/P95.
Thống kê đủ 182 users, gồm người không có stay/cluster; cân bằng clustered+noise và dwell với input.
Hai chart tổng hợp so sánh grouping, recurrence và dispersion; sensitivity DBSCAN full-input tùy chọn.
Không gán Home/Office trong NB04; bước đó dành cho NB05 sau khi cùng đọc kết quả grouping.

Validation: notebook hợp lệ, mọi cell compile được và không có outputs. Synthetic integration pass
cho nhiều user/zero-stay user, qua nửa đêm, ba stays cùng ngày, DBSCAN chain rộng, toàn noise,
empty input, input bị đổi, hai chart và bốn cấu hình sensitivity. Suite hiện tại 53 pytest tests pass.
Chỉ kiểm tra bằng dữ liệu giả; không chạy grouping trên GeoLife, không tạo thêm notebook output
hoặc helper script, không tự commit/push. Người dùng mở NB04 và tự chạy.

## Bản đồ tương tác cho NB04 — 2026-11-02

Người dùng đã chạy NB04 và yêu cầu xem dạng map. Audit completed/full_dataset, fingerprints input khớp;
10.339 stays và đủ 182 users. Địa điểm: heuristic 3.577, DBSCAN 552; DBSCAN có 3.296 noise stays.
Không chạy lại thuật toán, chỉ đọc CSV có sẵn để xuất `artifacts/locations/03_location_map.html`.

Thêm renderer `maps.py` và phần 7b trong NB04. Một HTML chứa mọi stays/locations và đủ users,
hai bản đồ cạnh nhau, chọn user hoặc toàn bộ, zoom đồng bộ, popup stay/cluster, toggle noise/extent,
nút zoom địa điểm có nhiều ngày ghé nhất. Cần internet cho Leaflet 1.9.4 và nền OpenStreetMap.
Không thêm dependencies hoặc launcher; giữ nguyên các cell/outputs và sensitivity setting của người dùng.

Validation: 57 pytest tests pass; JavaScript syntax valid. Trình duyệt hiển thị nền đường phố và markers;
chọn toàn bộ khớp 10.339 stays / 3.577 hoặc 552 địa điểm, chọn user 047 hiện 0 stays rõ ràng.
Đã kiểm tra zoom, lớp extent, toggle stays và popup thời gian/27 stays/7 ngày của một cluster thực.
Ảnh preview trong artifacts chỉ minh họa một góc nhìn; payload HTML vẫn chứa toàn bộ kết quả.

## Notebook 05 — temporal evidence và role inference (2026-11-02)

Người dùng xác nhận map xem được bằng trình duyệt, đã đọc sensitivity NB04 và yêu cầu tiếp phase 5.
Tạo `05_role_inference.ipynb`, giữ nguyên toàn bộ assignments/clusters của cả hai phương pháp,
thống kê mọi user, không train classifier, không clustering lại và không lấy mẫu.

Thêm reader timeline từ cleaned CSV theo khối, giữ nguyên trajectory; coverage nén các adjacent pairs
hợp lệ thành runs, union across files và ngắt tại observation_segment. Đọc đầy đủ mọi cleaned GPS
để tính observed days/minutes đúng mẫu số; có cache theo input/khung giờ và kiểm tra counts từng user.
Tách role_candidates để dùng lại cùng weights/logic quyết định khi xuất bảng điểm mọi ứng viên.

Notebook giải thích UTC/Asia-Shanghai, night/work overlap, eligibility, score/share/margin, alternatives,
unknown và POI recurrence. Có noise diagnostics/share gồm noise, hai charts, bảng xem từng user sau
full-data calculation, map H/O/H+O/P và sensitivity min days/dwell/score/share trên toàn users.
Giữ score semantics chưa hiệu chuẩn; không công bố accuracy hoặc loại hình doanh nghiệp.

Validation: 66 pytest tests pass; NB05 hợp lệ/compile được 14 code cells, 27 cells tổng, không có outputs.
Synthetic integration pass cả mixed Home/Office/POI, shared Home+Office, ambiguous Home, all-noise và
empty input; kiểm tra cached coverage, counts mọi users, sensitivity, exports và JavaScript syntax của map.
Không thực thi GPS hoặc inference GeoLife; chưa có nhãn/số lượng dự đoán thật. Người dùng tự chạy
NB05, đọc kết quả rồi mới chốt rule; OpenAPI vẫn là thiết kế, không triển khai endpoints/cloud.

## Đồng bộ pipeline core với notebooks — 2026-11-03

Theo yêu cầu bước 1 hoàn thiện CP1, core/CLI 0.2.0 chạy từ raw GPS đến JSON qua một hàm
`run_pipeline`, không cần artifacts notebook. Preprocessing dùng spatial_vote_context_v2, ngưỡng
20 m có config, mean nhóm gần, largest pairwise-close subset, context vote cùng trajectory và
tách nhóm hòa. Provenance giữ toàn bộ invalid/duplicate/conflict fixes, mean contributors không bị gọi deleted.
Unresolved timestamps và boundaries có sẵn ngắt observation segments, được stays/coverage tôn trọng.

`PipelineRun` thêm removed_points/conflict_points. CLI mặc định mọi users; --audit-points xuất CSV trace,
run-audit ghi expected/completed users/files và trạng thái failed nếu lỗi giữa chừng. Experiment script
cũng mặc định mọi users. NB02 chỉ đổi import helper diagnostics cho rows đã resolve; giữ nguyên
code voting hiển thị, outputs, ghi chú, thresholds và sensitivity của người dùng.

Validation thực hiện: 115 pytest tests pass. Parity gồm 12 loại fixture (gộp gần, đa số, context,
hòa, chain, dateline, invalid/duplicate, empty/all-invalid, file độc lập, Home/Office/POI lặp lại),
so cleaned points/audit/provenance với chính hàm reference NB02 và so cả hai end-to-end models
với chuỗi bước notebook. Kiểm tra thêm thresholds 0/5/50 m, inherited boundaries, CLI all-users,
point audit và lỗi giữa chừng. OpenAPI draft đồng bộ config/diagnostics/policy;
14 examples/responses (gồm 8 artifacts lịch sử) hợp lệ, uv lock --check --offline pass.

Không chạy lại preprocessing/inference trên GeoLife, không thay artifacts kết quả đã chạy,
không tạo notebook/helper script mới hoặc triển khai HTTP API. Full-data rerun CLI để người dùng
chạy theo README; chưa khẳng định parity thực nghiệm toàn dataset. Manual-review và report
vẫn là các bước tiếp theo tại thời điểm ghi chú này.

## Đối chiếu CLI DBSCAN với notebook toàn dataset — 2026-11-03

Người dùng đã chạy CLI DBSCAN 0.2.0 đủ 182 users / 18.670 files. Chỉ đọc outputs có sẵn để so với
NB02–05; không chạy lại raw GPS hoặc inference. Audit counts của mọi user, toàn bộ 10.339 stay records,
per-stay DBSCAN labels, coverage, location features và nested predictions/candidates/alternatives/POIs đều khớp
trong rtol 1e-10 / atol 1e-8 (delta float tối đa khoảng 8,9755e-9).

Trace: 709.851 conflict fixes khớp GPS/time/decision/spread và 146.915 invalid/duplicate rows khớp
multiset nội dung/reason. IDs nguồn là run-local nên không dùng để kết luận mismatch.
Validate 182 responses thật + 6 contract examples pass. Report máy đọc được ở
`artifacts/pipeline/dbscan-v1/notebook-comparison.json`, có fingerprints và scope.

Kết quả: 24.876.978 raw → 24.177.772 cleaned points, 552 clusters, 3.296 noise stays,
37 Home, 18 Office, 202 POIs. Không suy ra accuracy từ parity. CLI heuristic mới chưa chạy lại;
manual review file cũ vẫn trống labels/reviewer/notes. Các bước còn lại: ghi review hiện tại,
hoàn thiện hồ sơ báo cáo và rà soát contract để người dùng trình bày trực tiếp.
