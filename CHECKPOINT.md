# Checkpoint dự án — GeoLife Home / Office / POI

Cập nhật **2026-11-19**, Asia/Saigon. File này bàn giao ngữ cảnh sang chat mới.
Đọc file này trước, sau đó xem code/artifacts liên quan đến yêu cầu mới. Một số mục trong
PLAN/reports là nhật ký lịch sử; không coi trạng thái subset hoặc yêu cầu cũ là trạng thái hiện tại.

## Bàn giao giao diện đặt xe · 2026-11-19

- **Đã chốt luồng, cách đo và thiết kế.** Đọc [plan giao diện đặt xe](docs/ride-booking-ui-plan.md),
  đặc biệt mục 4 (thứ tự thực hiện) và mục 5 (thiết kế). Mục tiêu là web demo trên điện thoại,
  dùng kết quả GeoLife để gợi ý Nhà, Công ty và nơi hay đến khi chọn điểm đến.
- **Giao diện đặt xe có chế độ PostgreSQL local.** Từ gốc repo, chạy
  `.\.venv\Scripts\python.exe -m geolife_inference.ride_booking --open`.
  Lệnh dùng snapshot `geolife-1.3-full-v1` đã nạp tại `artifacts/cp2/postgres-local` hoặc dùng
  `GEOLIFE_POSTGRES_DSN` và `GEOLIFE_SNAPSHOT_ID` nếu đã cấu hình. Mở trang chọn `user_id` từ DB,
  rồi gọi `POST /v2/locations/infer`. Gợi ý hiển thị tọa độ GPS trên bản đồ OpenStreetMap khi có mạng.
  Khi không tải được bản đồ nền, lưới tọa độ vẫn hiển thị ghim. Điểm đón và xác nhận chuyến là mô phỏng.
- **Chế độ demo Knative** chạy bằng `.\.venv\Scripts\python.exe -m geolife_inference.ride_booking --knative --open`.
  Danh sách người dùng đọc từ PostgreSQL. Request gợi ý đi qua Kourier tới URL chính của Knative Service
  trong `geolife-knative-postgres`, theo traffic của Route. Mục **Phiên bản gợi ý** hiển thị model thực tế
  và đối chiếu metadata với alias MLflow. Registry hiện đăng ký snapshot `geolife-1.3-demo-v1`, còn Revision
  PostgreSQL phục vụ `geolife-1.3-full-v1`.
  Launcher đọc kết nối PostgreSQL từ Secret của Knative hoặc `GEOLIFE_POSTGRES_DSN`. DB phục hồi cho
  lượt rehearsal nằm ở `artifacts/cp2/postgres-knative-rehearsal/data` và dùng cổng 55433.
- **Chế độ offline** khi mở trực tiếp [ride-booking/index.html](ride-booking/index.html) bằng trình duyệt.
  Ba hồ sơ mẫu cho các tình huống đủ gợi ý, thiếu gợi ý và không có gợi ý.
- **Đã kiểm tra trên khung điện thoại 360 × 780 px với thao tác chạm mô phỏng.** Chọn **Nhà** tự điền
  điểm đến. Có thể tìm địa chỉ khác, sửa điểm đón và xác nhận chuyến. Hồ sơ trống đặt được chuyến bằng
  ghim bản đồ. Đã kiểm tra địa chỉ tiếng Việt dài, cỡ chữ 125% và thao tác kéo bảng đặt xe.
- **Đã kiểm tra giao diện PostgreSQL với user `101`** trên khung điện thoại 360 × 780 px.
  API đọc 13.738 điểm, trả gợi ý Nhà và kết quả `unknown` cho Công ty. Đã chọn Nhà, sửa ghim và
  xác nhận chuyến mô phỏng. Kiểm thử dùng WSGI và PostgreSQL standalone vì môi trường Codex chặn TCP loopback.
  Xem [OpenAPI](openapi.yaml) và [hướng dẫn Knative](docs/cp2-knative-deploy.md) khi triển khai.
- **Đo lường ở chặng 3–4.** A/B 50/50, giữ nhóm theo người thử, cân bằng hồ sơ và nhiệm vụ.
  Tách fixture và lượt trình bày. Tính dùng gợi ý khi xác nhận chuyến và điểm đến vẫn lấy từ thẻ.
  Chi tiết về phiên, mẫu số, sửa điểm đến và phản hồi muộn nằm trong plan.

Tin nhắn để mở lại chặng 1 trong cùng workspace:

> Đọc `CHECKPOINT.md`, phần “Bàn giao giao diện đặt xe”, rồi đọc `docs/ride-booking-ui-plan.md`.
> Chạy `geolife_inference.ride_booking` với PostgreSQL. Kiểm tra luồng chọn người dùng, chọn gợi ý,
> sửa điểm đến và xác nhận chuyến mô phỏng trên màn hình điện thoại theo thiết kế ở mục 5.

## 1. Mục tiêu và trạng thái hiện tại

Dự án MLE Track B1 suy luận các địa điểm có thể là Home, Office và nơi thường ghé (POI) từ GPS.
Luồng: **GPS points → làm sạch → stays → clusters → temporal evidence → Home/Office/POI**.

- **CP1 offline đã hoàn tất phần benchmark và tổng hợp để bàn giao.** B1–B5 có kết quả thực nghiệm,
  B6 có bảng quyết định và giới hạn trong [báo cáo benchmark](reports/cp1/benchmark.md).
- CLI heuristic và DBSCAN 0.2.0 đã chạy toàn bộ 182 user và đối chiếu với notebook.
- Giữ vote20 và score Home/Office hiện tại. Người dùng chọn **fixed-anchor 150 m/10 phút** để tiếp tục
  khảo sát, dùng **100 m/10 phút** làm đối chứng. Mặc định core/config 0.2.0 hiện là 100 m/10 phút.
- B4 đã có kết quả so sánh, còn lượt xác nhận cuối chưa sinh và chưa mở. Home/Office trên GPS thật
  chưa có nhãn độc lập để đo accuracy.
- **CP2 đã kiểm chứng API v1 qua Docker và API v2 qua HTTP local.** V1 dùng lại pipeline 0.2.0,
  có mặc định 100 m/10 phút và preset thử nghiệm 150 m/10 phút. V2 nhận `user_id`, đọc PostgreSQL và đã
  trả kết quả khớp JSON CLI cho user `101`. [Plan CP02](docs/cp2-implementation-plan.md)
- **Hướng CP2 hiện tại là Kubernetes local với Knative Serving + Kourier.** Hai Revision HTTP dùng
  cùng snapshot SQLite. Blue là `heuristic-v1`, Green là `dbscan-v1`. Hai model trên cluster đã
  khớp CLI, canary có 100 request thành công và rollback về Blue đã được kiểm tra qua HTTP.
  Đã đo riêng hai bản sau warmup, xác minh promote sang Green và quan sát cả hai Revision từ 0 pod
  đến có pod Ready sau request suy luận. MLflow 3.18.0 tại localhost:5001 đã đăng ký hai bản `READY` và đối chiếu
  cả hai với JSON CLI cho toàn bộ snapshot demo.
  [Bàn giao CP2 hiện tại](#bàn-giao-cp2-ngày-2026-11-17)
- **Snapshot SQLite full cho bước cloud:** `geolife-1.3-full-v1` chứa 182 user, 18.670 trajectory
  và 24.876.978 điểm GPS tại `artifacts/cp2/sqlite-full/geolife.sqlite3` (3,51 GB).
  54 user vượt 100.000 điểm phục vụ từ kết quả CLI đã tính trên lịch sử đầy đủ của từng model.
  API suy luận theo request cho 128 user còn lại. Kiểm tra qua WSGI local trả HTTP 200 và
  khớp CLI cả 364 cặp user/model. Chi tiết trong `artifacts/cp2/sqlite-full/verification.json`.
  Dùng file full đã kiểm chứng để nạp PostgreSQL cho cloud.
  Xem [lệnh tạo snapshot](docs/cp2-knative-deploy.md#tạo-snapshot-phục-vụ-toàn-bộ-geolife).
- **PostgreSQL cho bản cloud:** `scripts/import_postgres.py --sqlite` đã nạp snapshot
  `geolife-1.3-full-v1` vào PostgreSQL 18.1 thử nghiệm tại `artifacts/cp2/postgres-local/data`.
  Đã kiểm đếm 182 user, 24.876.978 điểm, 108 kết quả dài cho 54 user. Lần import lặp
  dùng lại snapshot. API v2 qua WSGI local trả HTTP 200 và khớp CLI cả 364 cặp user/model.
  Chi tiết trong `artifacts/cp2/postgres-local/verification.json`. DB thử nghiệm đã dừng sau khi
  kiểm tra. Image cloud dùng target `postgres` và manifest
  `infra/knative/geolife-postgres.yaml`, đọc DSN từ Secret.
  Xem [hướng dẫn PostgreSQL](docs/cp2-knative-deploy.md#postgresql-cho-bản-cloud).
- **Demo Knative với PostgreSQL local (19/11):** hai Revision dùng image
  `dev.local/geolife-api:0.2.0-postgres` và Secret chỉ đọc trong `geolife-knative-postgres`.
  Cả hai khớp CLI cho `101` và `153` qua Kourier. Canary 90/10 cho **88 Blue / 12 Green**, 0 lỗi.
  Cùng URL live đã chuyển sang Green rồi trở về Blue. Rollback và kiểm tra API mất **8,55 giây**.
  Đã trả traffic về Blue 100% và giữ URL preview Green. Instance phục hồi từ snapshot full nằm
  ở `artifacts/cp2/postgres-knative-rehearsal/data`. DB và port-forward đã dừng sau diễn tập.
  Xem [hướng dẫn chạy lại](docs/cp2-knative-deploy.md#demo-postgresql-trên-docker-desktop),
  [kết quả rollout](reports/cp2/release.md#canary-knative-với-postgresql-ngày-2026-11-19)
  và [slide Checkpoint 2](exports/GeoLife-Checkpoint-2.html).
- **Đợt đầu trên Google Cloud (22/11):** triển khai API nội bộ trên GKE + Knative/Kourier,
  kéo image private từ GHCR và nạp snapshot đầy đủ vào Cloud SQL for PostgreSQL. Sau khi kiểm tra
  hai Revision, canary và rollback, triển khai giao diện đặt xe và MLflow. Đã chuẩn bị
  render manifest với image theo digest. Cần project và cụm GKE để chạy bản cloud.
  [Hướng dẫn triển khai](docs/cp2-knative-deploy.md#postgresql-cho-bản-cloud)
- **Chiến lược phát hành CP2:** demo canary trên cùng URL. Kiểm tra ứng viên qua URL có tag,
  đưa 10% traffic sang ứng viên rồi chọn promote hoặc rollback. Tag `blue` là bản hiện tại,
  tag `green` là bản thử nghiệm trong các lệnh diễn tập.
- Người dùng đã yêu cầu bỏ quy trình/checklist/gate mentor review/approval.

## 2. Cách làm việc người dùng muốn

- Trả lời **tiếng Việt, ngắn, dễ hiểu**, dùng ví dụ cụ thể; người dùng muốn hiểu bản chất từng bước.
- Làm chậm, tỉ mỉ: xem dữ liệu/charts, giải thích lựa chọn rồi mới chuyển bước. Không làm quá nhiều phase một lượt.
- Mọi phân tích/xử lý thực tế mới mặc định **toàn bộ dataset**. Không âm thầm lấy 1–3 users làm thử hay lấy mẫu points.
  Có thể xử lý tuần tự theo user/trajectory để tiết kiệm RAM; phải xác nhận đủ phạm vi.
- Thông thường **assistant sửa notebook/code, người dùng chạy các job full-data**. Đừng tự chạy lại pipeline tốn thời gian
  chỉ để trả lời câu hỏi đã có saved outputs. Nếu câu hỏi cần scan mới, nêu phạm vi và tận dụng kết quả đã có.
- Không thêm quiz/câu hỏi kiểm tra kiến thức vào notebook. Chỉ viết giải thích và nội dung cần thiết.
- Chỉ **một notebook làm việc cho mỗi bài trong `notebooks/`**. Không tạo bản source/executed/rendered trùng nhau.
- Giữ outputs/settings/ghi chú người dùng đã lưu; không clear outputs hoặc ghi đè notebook để tiện commit.
- Không sinh helper scripts, ảnh/folder trùng hoặc scaffolding nếu không cần cho bài.
- Người dùng đã xác nhận dataset public; không thêm cảnh báo nhạy cảm không cần thiết. Dataset và artifacts vẫn Git ignored.
- Không tự gửi email/tin nhắn cho người khác, tạo cloud resources hoặc phát sinh chi phí.
- Dùng **`py`**, không dùng lệnh `python` trực tiếp trên Windows.

## 3. Môi trường, đường dẫn, Git

- Workspace: `E:\QUY\Geolife-Trajectories`, PowerShell, kernel **Python (GeoLife)**, môi trường `.venv`.
- Repo: https://github.com/quycute2003/Geolife-Trajectories.git, branch `main`, remote `origin`.
- `HEAD` và ref `origin/main` lưu trên máy cùng ở **`24f05a1` — `chore: remove CP01 benchmark tests`**.
  Các thay đổi CP2 đang ở working tree local. `CHECKPOINT.md` chưa được commit.
- Phiên bản package/core: **0.2.0**, khóa dependencies bằng `uv.lock`; Python hỗ trợ 3.11–3.13.
- Dataset ZIP gốc: `C:\Users\QUY\Downloads\Geolife Trajectories 1.3.zip`.
- Đã giải nén local tại **`data/Geolife Trajectories 1.3/`**. Không cần extract/download lại.
- ZIP SHA256: `1107c5ac064d0a23c8d021a8736a77e53abc75b227062e6260342c6a8d86bdb6`.
- Prompt gốc do người dùng cung cấp: `C:\Users\QUY\.codex\attachments\9e0a258d-15f9-474c-9496-b72fcbc61019\Pasted text.txt`.
  Các yêu cầu mới trong chat (đặc biệt full dataset, notebook và bỏ mentor approval gate) đã điều chỉnh cách làm ban đầu.
- `.gitignore` bỏ qua `data/`, `artifacts/`, `tmp/`, `.venv/`, ZIP/PLT và build/cache files.

Từ gốc repo, nếu cần tạo hoặc đồng bộ `.venv`, dùng `uv sync --locked --group api --group notebook`
với Python 3.11–3.13. Sau đó kiểm tra `py` trỏ vào `.venv\Scripts\python.exe`:

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
$env:PYTHONDONTWRITEBYTECODE = '1'
py -X utf8 -c "import sys; print(sys.executable)"
```

Khi source module đã đổi mà notebook vẫn giữ code cũ trong RAM: chọn **Python (GeoLife)**,
**Restart Kernel → Run All**. Notebook mở trực tiếp bằng VS Code/Jupyter; không có launcher script riêng.
Nếu VS Code báo file trên đĩa mới hơn: Revert bỏ bản chưa lưu trong tab; Overwrite ghi bản đang mở lên đĩa.
Phải xét người dùng có sửa/outputs chưa lưu trước khi chọn.

## 4. Các notebook baseline

| Notebook | Vai trò | Input / output chính |
|---|---|---|
| `01_dataset_overview.ipynb` | Hiểu file PLT, inventory, phân bố dữ liệu/users, sampling/gaps, quality audit | Inventory toàn dataset; quality audit chi tiết ban đầu chỉ 3 users. Có 2 charts; các chart 3–6 và quiz đã bỏ theo yêu cầu |
| `02_preprocessing.ipynb` | Quét conflicts, xem phân phối độ lệch, chọn ngưỡng, làm sạch mọi user, lưu trace | Raw → `artifacts/preprocessing/cleaned_points.csv.gz`, removed/conflict CSV, audit và charts |
| `03_stay_detection.ipynb` | Tìm stays, kiểm tra overlap, phân phối thời lượng, sensitivity radius/duration | Cleaned GPS → `artifacts/stays/stays.csv`, per-user/audit/sensitivity |
| `04_location_grouping.ipynb` | So radius matching và DBSCAN, recurrence/dispersion/noise, bản đồ, sensitivity | Stays → `artifacts/locations/` assignments, locations, comparison, map |
| `05_role_inference.ipynb` | Coverage từ mọi cleaned GPS; temporal features, score/unknown, POIs, map và sensitivity | `artifacts/inference/` coverage, features, candidates, decisions, predictions, map |

**NB02–05 đã xử lý toàn dataset**. Chọn một user trên bản đồ chỉ lọc hiển thị sau khi đã tính toàn bộ.
Không nói NB01 quality audit 3 users là toàn dataset, cũng không nói NB05 chưa chạy.

## 5. Rules của baseline core 0.2.0

### Dữ liệu và timestamp

- PLT có 6 header lines; timestamp đọc thành **UTC**, độ chính xác dữ liệu tới giây.
- Altitude gốc feet đổi sang meters; `-777` là missing, giữ NaN chứ không loại cả point.
- Timestamp conflict xét **cùng user + cùng trajectory + cùng timestamp chính xác**, khác tọa độ.
  Hai timestamp chỉ cùng phút nhưng khác giây không phải cùng conflict group.
- Nội bộ giữ UTC. Khi xét night/work mới đổi sang múi giờ cấu hình bằng pandas `tz_convert`.
- Baseline dùng **Asia/Shanghai (UTC + 8)** cho mọi user. Đây là giả định: points ở nước khác có thể cần múi giờ khác;
  hiện chưa tự suy timezone từ tọa độ. Việt Nam UTC + 7 không phải timezone mặc định của dữ liệu này.

### NB02 / preprocessing 0.2.0 — `spatial_vote_context_v2`

1. Loại coordinate/timestamp không hợp lệ. Exact duplicates theo user/trajectory/time/lat/lon giữ một dòng.
2. Với conflict group, tính khoảng cách Haversine **mọi cặp điểm**, không dùng point đầu làm anchor.
3. Nếu mọi cặp ≤ **20 m**: lấy mean tọa độ. Longitude xử lý vòng ±180°; altitude mean các giá trị finite.
4. Nếu có các điểm xa: tìm **nhóm đông nhất mà mọi cặp trong nhóm đều ≤20 m** (largest clique).
   Các nhóm ứng viên có thể chồng nhau; không dùng connected-components nối dây chuyền.
5. Nếu nhiều nhóm lớn nhất hòa: các timestamps không-conflict trong **cùng trajectory**, trong **±5 phút**, bỏ phiếu
   cho candidate mean gần nhất và trong 20 m. Vote gần nhất bị hòa thì bỏ qua. Chỉ chọn khi có winner duy nhất, số vote >0.
6. Winner được lấy mean và giữ trong cleaned output; minority ngoài winner lưu trace `rejected_by_vote`.
   Nếu vẫn chưa phân biệt được thì lưu riêng toàn group `unresolved_tie`; timestamp đó làm ngắt observation segment.
   Không bỏ cả timestamp khi đã có winner, cũng không giữ nguyên mọi conflicting point trong cleaned data.

Số khoảng cách không lặp là `n*(n-1)/2`; tìm largest clique có thể tốn theo tổ hợp/hàm mũ trong trường hợp xấu.
Chỉ xét bên trong từng conflict timestamp, không so mọi GPS point toàn dataset. Nhóm thực tế lớn nhất đã quan sát có 14 fixes.

- High speed >100 m/s chỉ là flag, **không tự xóa**. Gaps >5 phút làm ngắt segment.
- `preprocess_with_trace` là raw entry point; `preprocess` giữ interface `(points,audit)`.
- NB02 dùng `diagnose_resolved_points` qua alias để tính diagnostics sau khi notebook đã vote; không vote hai lần.
- `unresolved_conflict_rows` trong audit legacy bao gồm cả minority bị tách, không chỉ toàn-group ties.
- Công thức counts: `input = output + invalid + duplicates + merged_extra_points + unresolved_conflict_rows`.
- `record_id` chỉ có nghĩa trong lượt đọc; không so IDs global NB02 với IDs local từng user của CLI.

### NB03 — stay detection

- Trong cùng user/trajectory/observation_segment: anchor là **point đầu** của candidate stay, cố định.
- Mọi point nhận vào cách anchor ≤ **100 m**; hai point liên tiếp cách thời gian ≤ **5 phút**.
- Từ first đến last accepted point ≥ **10 phút** thì thành stay; không kéo end tới điểm departure và không bù gaps.
- Tọa độ đại diện stay là median. Flush candidate ở cuối trajectory.
- Nếu stays khác files cùng user chồng thời gian: giữ sự kiện có start sớm hơn, tách riêng toàn sự kiện overlap sau.
  Chạm endpoint không tính overlap. Dataset baseline thực tế có 0 overlap.
- Stay detector có thể nhận đi bộ chậm thành stay; thresholds chưa được tối ưu bằng nhãn.

### NB04 — gom địa điểm

- Gom **tọa độ đại diện stays**, riêng từng user, qua tất cả ngày; không cluster theo ngày.
- `heuristic-v1`: ghép vào anchor cố định gần nhất trong 100 m, nếu không có thì mở cluster mới; mọi stay được gán.
- `dbscan-v1`: Haversine/radians, eps **100 m**, min_samples **3** (tính cả chính stay), noise label `-1`.
- DBSCAN có thể nối chuỗi nên cluster có bán kính lớn hơn eps; nhiều clusters/noise ít hơn không chứng minh chính xác hơn.
- Cluster ID chỉ local trong user/model/config; không so trực tiếp ID giữa hai model.
- Popup “Xa median nhất” = khoảng cách lớn nhất từ **tọa độ đại diện stay** tới median cluster,
  không phải độ lệch của mọi raw GPS points hay ranh giới thật của địa điểm.

### NB05 — Home / Office / POI

- Night: **22:00–06:00**, work: **09:00–18:00 thứ Hai–thứ Sáu**, theo timezone cấu hình.
- Dwell tính đúng phần overlap windows, gồm giây; intervals `[start,end)`, không bù các positive gaps.
- Coverage tính từ **toàn bộ cleaned GPS**, cả đang di chuyển, union các intervals hợp lệ qua files;
  không lấy stays thay cho coverage và không cộng overlap hai lần.
- Đủ điều kiện role: ≥**3 role visit days**, ≥**60 role dwell minutes**. Office cần thêm ≥**2 ISO weeks**;
  2 ISO weeks không đồng nghĩa đủ 14 ngày.
- Evidence score (các component chặn tối đa 1):
  - 30% recurrence = role visit days / 5.
  - 25% duration = role dwell minutes / 600.
  - 20% temporal consistency = role visit days / role observed days.
  - 15% coverage = mọi GPS observed minutes / 1440.
  - 10% relative strength = role dwell / tổng role dwell ở mọi non-noise clusters.
- Chọn best eligible khi score ≥**0.5**, share ≥**0.5**, và score hơn mọi competitor ≥**0.05**.
  Competitors gồm cả candidate chưa eligible. Nếu không đạt: `insufficient_evidence`, `low_evidence_score`,
  hoặc `ambiguous_candidates` (reason này bao gồm share thấp).
- Home/Office độc lập, có thể cùng cluster. POIs là clusters còn lại ghé ≥3 ngày, sort days/dwell, tối đa 10.
  Candidate Home/Office bị unknown vẫn có thể xuất hiện trong POIs.
- Score không phải xác suất và `unknown` là kết quả hoàn thành hợp lệ.

## 6. Kết quả thật đã có

| Mục | Kết quả baseline |
|---|---:|
| Dataset users / PLT | 182 / 18.670 |
| Raw points | 24.876.978 |
| Cleaned points | 24.177.772 |
| Invalid removed / duplicates removed | 1 / 146.914 |
| Merged extras / conflict rows tách riêng | 551.156 / 1.135 |
| Conflict groups / unresolved toàn group | 157.865 / 305 |
| Minority bị tách / rows trong toàn-group ties | 384 / 751 |
| Stays / users có stay | 10.339 / 151 |
| Overlapping stays | 0 |
| Tổng giờ trong stays | 3.592,999444 |
| Heuristic locations / noise | 3.577 / 0 |
| DBSCAN locations / noise stays | 552 / 3.296 (31,8793%) |
| Heuristic Home / Office predicted users | 28 / 8 |
| DBSCAN Home / Office predicted users | 37 / 18 |
| DBSCAN POIs tổng cộng | 202 |

NB03 sensitivity đã chạy full input: radius 50 m → 6024 stays; radius 200 m → 14371;
duration 5 min → 27605; duration 20 min → 3174. NB04 sensitivity eps 50/200 m, min_samples 2/5 đã chạy;
NB05 có 20 rows sensitivity (5 settings × 2 models × 2 roles). Không dùng counts để tuyên bố model tốt nhất.

User **003** từng được xem kỹ: DBSCAN Home và Office đều unknown `ambiguous_candidates` vì share thấp
(Home cluster 0 score ≈ 0.7498/share ≈ 0.3583; Office score ≈ 0.7502/share ≈ 0.3195), không phải vì score thấp.
Cluster 0 có độ phân tán max ≈ 425.6 m nên cần thận trọng. Có 10 POIs, 22 clusters, 436 stays, 90 noise stays.

## 7. Artifact và nguồn code cần tìm

- `artifacts/preprocessing/`: cleaned_points.csv.gz (~920 MB), removed_points.csv, conflict_points.csv,
  conflict_groups.csv, audit.json, charts.
- `artifacts/stays/`: stays.csv, per_user.csv, overlap/audit/sensitivity và charts.
- `artifacts/locations/`: stay_assignments.csv, locations.csv, comparison/per_user/audit/sensitivity;
  **`03_location_map.html`**.
- `artifacts/inference/`: coverage.csv/cache audit, location_features.csv, candidate_scores.csv,
  decisions.csv, pois.csv, predictions.json, user_diagnostics/summary/audit/sensitivity;
  **`03_role_map.html`**.
- `artifacts/pipeline/dbscan-v1/`: 182 `<user>-dbscan-v1.json`, stays/removed/conflicts CSV,
  run-audit.json và **notebook-comparison.json**.
- `artifacts/evaluation/manual-review-sample.csv`: 8 users × 2 models × 2 roles =32 rows;
  **reviewer/plausibility/notes còn trống**. Không tự điền labels từ predictions.
  Các bảng manual-review/template 130 dòng là thí nghiệm subset cũ, không dùng làm review hiện tại.

Map dùng Leaflet/OpenStreetMap và cần Internet. Nếu VS Code iframe chỉ hiện nền xám nhưng có markers,
**mở HTML bằng trình duyệt riêng**: người dùng đã thử và thành công. Không cần đổi tile provider.

`src/geolife_inference/` gồm loader (`data`), khoảng cách (`geo`), preprocessing/trace, stays, clustering,
features/coverage, inference, orchestration (`pipeline`), CLI, evaluation, maps và package entrypoints.
`run_pipeline(raw_points, user_id, config, model_version)` là hàm chạy mọi bước cho đúng một user.
Trả `PipelineRun` có `result`, `points`, `stays`, `removed_points`, `conflict_points`.
CLI xử lý lần lượt mọi user mặc định; mỗi user ở RAM, không hứa streaming bên trong user rất lớn.
Inference ID deterministic dựa trên semantic cleaned input/config/model/version; không dùng làm access token.

## 8. Kiểm chứng và lệnh chạy

- Test suite tại mốc baseline CP1: **115 passed**. Parity fixtures trích reference functions NB02 bằng AST,
  kiểm tra cả hai model trên dữ liệu giả, không chạy lại notebook GeoLife để test.
- Full DBSCAN CLI vs NB02–05: **matched, difference_count = 0** với `rtol=1e-10`, `atol=1e-8`,
  max observed delta≈`8.9755e-9`. So từng user, stays, labels, coverage/features,
  predictions/candidates/components/alternatives/POIs, 709.851 conflict fixes và 146.915 removed fixes.
  Không tuyên bố đã so từng cleaned GPS row qua một cleaned export CLI khác (CLI không xuất bản đó mặc định).
- OpenAPI validation gần nhất: **188 pass =182 real CLI responses +6 contract examples**.

```powershell
$dataset = Join-Path (Get-Location) 'data\Geolife Trajectories 1.3'
py -X utf8 -m geolife_inference inventory --dataset $dataset
py -X utf8 -m geolife_inference eda --dataset $dataset --output artifacts/eda-full

# Hai model đã chạy toàn dataset. Chỉ chạy lại khi cần và chọn output riêng để giữ kết quả cũ.
py -X utf8 -m geolife_inference infer --dataset $dataset --model dbscan-v1 --config configs/baseline.toml --output artifacts/pipeline/dbscan-v1-rerun --audit-points
py -X utf8 -m geolife_inference infer --dataset $dataset --model heuristic-v1 --config configs/baseline.toml --output artifacts/pipeline/heuristic-v1-rerun --audit-points
py -X utf8 scripts/run_experiments.py --dataset $dataset --output artifacts/evaluation-rerun

# Kiểm tra contract bằng kết quả đã có.
py -X utf8 scripts/validate_contract.py --results artifacts/pipeline/dbscan-v1
py -X utf8 -m pytest -q
```

CLI nhận GeoLife ZIP hoặc thư mục chứa `<user_id>/Trajectory/*.plt`, kể cả thư mục cha. Mỗi user có
JSON kết quả và CSV lần dừng. `--audit-points` xuất thêm `-removed.csv` và `-conflicts.csv` để truy vết
điểm bị loại hoặc gộp. `run-audit.json` phân biệt running/failed/completed và full/selected scope.
Không dùng `artifacts/evaluation/` subset cũ để khẳng định CLI 0.2.0 full-data đã kiểm chứng cả hai model.

Khi gọi từ Python, truyền DataFrame GPS thô của một user vào `run_pipeline`, với các cột `user_id`,
`trajectory_id`, `latitude`, `longitude`, `altitude_m` và `timestamp`. Timestamp là UTC có timezone,
altitude thiếu dùng `NaN`. NB02 có helper riêng cho dữ liệu đã resolve để tránh cleaning hai lần.

## 9. OpenAPI và báo cáo

- `openapi.yaml`: OpenAPI 3.1, contract 0.2.0-draft. API CP2 có `POST /v1/locations/infer`, `GET /health`
  và `GET /version`. Container local mở cổng `127.0.0.1:8001`.
- V1 nhận GPS history của một user (trajectory_id, lat/lon, timestamp UTC, optional altitude và model/config).
  V2 nhận `user_id`, truy vấn GPS PostgreSQL và chạy suy luận với `dbscan-v1`, `baseline-v1`.
- Output Home/Office candidate hoặc unknown, alternatives/evidence, POIs, locations, coverage/diagnostics/warnings.
- Local xử lý lỗi 400/413/415/422/500, giới hạn 20 MiB và 100.000 điểm. Xác thực, rate limit và
  giới hạn thời gian xử lý là phần thiết kế production.
- `/health` trả `200` và `{"status":"ok"}` khi API phản hồi được. `/version` trả model và cấu hình mặc định
  của instance, phiên bản pipeline và `config_sha256`. Response suy luận ghi bản thực chạy của từng request.
- `reports/cp1/summary.md`: báo cáo ngắn để trình bày; `results.md`, `phase_log.md`: chi tiết và lịch sử.
- `docs/architecture.md`, `assumptions.md`, `data_dictionary.md`, `evaluation.md`, `research_notes.md`.
  Một số phần reproduce/historical subset trong docs cũ có thể chưa phản ánh lời mô tả mới nhất;
  kiểm tra code và audit thay vì lặp lại các claim cũ.

## 10. Bàn giao benchmark CP1 và bước đầu CP2

| Bước | Kết quả bàn giao |
|---|---|
| B1 · NB06 | Kiểm kê và phân tích GPS toàn bộ 182 user, 69 file nhãn phương tiện. CLI heuristic đã chạy và khớp notebook. |
| B2 · NB07 | 162 user nguồn đủ điều kiện, chia 81 chọn cấu hình và 81 kiểm tra cuối theo user/nhóm nguồn trùng y hệt. Tập tổng hợp chọn cấu hình có 28.755 ca. |
| B3 · NB08 | So sáu phương án cleaning trên toàn dataset. Giữ vote20 vì đối chiếu số lượng, nguồn đóng góp và kết quả chưa cho thấy cần thay. |
| B4 · NB09 | 48 cấu hình tổng hợp và 40 cấu hình chạy GPS thật. Job GPS thật đủ 182 user, bảng chọn cấu hình dùng 81 user nguồn tương ứng. ST-DBSCAN có ca nối dọc hành trình, dài hơn 9 giờ và cách đầu–cuối gần 889 km. |
| B5 · NB10 | 17.472 dòng quyết định Home/Office, so 100/150 m, hai grouping, hai rule và sáu kịch bản trên 182 user. Baseline tái lập NB05. Với DBSCAN grouping và score, 150 m cho 39 Home và 22 Office, so với 37 và 18 ở 100 m. |
| B6 · báo cáo | [Bảng quyết định và giới hạn](reports/cp1/benchmark.md), [tóm tắt](reports/cp1/summary.md) và [deck 17 slide](exports/CP1_GeoLife_BaoCao_17slides.pptx). |

- B4 còn các ô không đạt hoặc chưa xác nhận, gồm kiểm tra phủ định bằng nhãn phương tiện và runtime
  chạy trộn tuần tự/song song. 150 m là lựa chọn thực nghiệm đã ghi trong báo cáo. Tập tổng hợp kiểm tra
  cuối chưa sinh/mở. B5 và EDA đã xem toàn dataset, nên đánh giá hiện có là khảo sát trong phạm vi GeoLife.
- F1 stay dựa trên stop tổng hợp có đáp án. B5 đo số dự đoán, unknown và độ đồng thuận, còn độ đúng
  Home/Office ngoài thực tế cần nhãn độc lập. Ledger sau B5 là 13,522/24 giờ theo cách tính trong báo cáo.
- Kết quả có thể đọc tại `artifacts/benchmark/b1/` đến `b5/`. Dùng audits và kết quả đã lưu khi bàn giao.
  Một số ô và mô tả tiến độ trong PLAN còn ở mốc cũ. Dùng báo cáo và audits để đọc trạng thái đã thực hiện.

**Bước đầu CP2 đã kiểm chứng ngày 2026-11-09.** API local kiểm tra input theo `openapi.yaml` rồi gọi
`run_pipeline`. HTTP 200 của user 101 (13.738 điểm GPS, 29 stays, 3 cụm, Home `predicted`, Office
`unknown`) khớp toàn bộ JSON CLI `dbscan-v1` đã lưu, gồm `inference_id`. Request thiếu `latitude`
trả HTTP 422 với đường dẫn `/points/0/latitude`. Tại mốc này có **181 test**, **8 kiểm tra biên API**
và **188 lượt kiểm tra schema OpenAPI** đều qua.

### Chạy lại API local

Mở PowerShell ở gốc repo, khởi động server và giữ cửa sổ này mở.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 -m geolife_inference.api
```

Endpoint `POST http://127.0.0.1:8000/v1/locations/infer` nhận `user_id` và mảng `points`.
Mỗi điểm có `trajectory_id`, `latitude`, `longitude`, `timestamp` UTC và có thể có `altitude_m`.
Có thể truyền `model_version` và chọn một trong hai trường `config_version` hoặc `config` ở cấp request.
`model_version` chọn `dbscan-v1` hoặc `heuristic-v1`, còn `pipeline_version` là phiên bản core `0.2.0`.

Mở PowerShell thứ hai ở gốc repo để kiểm lại hai request. Script đọc GPS gốc của user 101 và đối chiếu
với `artifacts/pipeline/dbscan-v1/101-dbscan-v1.json` đã lưu.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 scripts/check_local_api.py
```

Dừng server bằng `Ctrl+C` sau khi kiểm tra. Mã endpoint ở `src/geolife_inference/api.py`.

### Định danh cấu hình CP2 trước khi đóng gói

- `baseline-v1` là cấu hình mặc định 100 m/10 phút. `stay150-experiment-v1` là cấu hình thử nghiệm
  150 m/10 phút, chỉ đổi `distance_m`. Bán kính gom cụm `eps_m` vẫn là 100 m.
- API và CLI ghi `model_version`, `pipeline_version`, `config_version`, `config_sha256` và `config`
  đầy đủ. `config_version` được xác định theo bộ tham số thực chạy. Nếu khác cả hai preset thì kết quả
  ghi `custom`. Gửi lại `config` đã lưu để tái lập cấu hình `custom`.
- Để chuyển giữa hai preset, chọn `config_version` trong request hoặc `--config-version` ở CLI.
  Gửi đồng thời `config_version` và `config` trả 422. CLI vẫn đọc được file TOML qua `--config`.
- OpenAPI kiểm tra được 182 kết quả DBSCAN đã lưu và 6 ví dụ. Gọi trực tiếp WSGI với 13.738 điểm của
  user 101 và `baseline-v1` cho kết quả khớp toàn bộ trường JSON CLI đã lưu, gồm cả `inference_id`.
  Kết nối socket loopback trong môi trường kiểm tra bị chặn (`WinError 10013`).
- **182 test pass** khi dùng `pytest --basetemp` trỏ tới thư mục mới, đường dẫn ngắn dưới `tmp/` của repo.

### Docker local

- `Dockerfile` dùng Python 3.11, cài nhóm `api` từ `uv.lock`, chạy dưới user không phải root.
  `.dockerignore` giới hạn file đưa vào build context ở source package, lockfile và OpenAPI.
- Python API mặc định nghe ở `127.0.0.1`. Dockerfile dùng `--host 0.0.0.0` để nhận request trong container.
  Cổng trên Windows chỉ công bố ở `127.0.0.1:8001`. Lượt thử đặt giới hạn 2 CPU và 2 GiB RAM.
- Kiểm chứng ngày 2026-11-09: 182 test pass. Chạy script kiểm tra qua WSGI trực tiếp: user 101
  khớp JSON CLI, ca tổng hợp cho 0 lần dừng ở 100 m và 1 lần dừng ở 150 m, thiếu `latitude` trả 422.
  Docker CLI bị chặn ghi `buildx/.lock` và Docker Engine chưa kết nối được sau khi thử khởi động Desktop.
- **2026-11-10:** Build thành công image `geolife-api:0.2.0-cp2`. Container `geolife-api-local` chạy dưới UID
  `10001`, không mount dataset. `scripts/check_local_api.py --port 8001` qua HTTP cho bốn kết quả đúng:
  user 101 khớp JSON CLI, ca tổng hợp có 0 lần dừng ở 100 m và 1 ở 150 m, thiếu `latitude` trả 422
  tại `/points/0/latitude`. Container được để chạy trên máy local sau kiểm thử.
- Cùng ngày, build lại image sau khi thêm `/health` và `/version`. Smoke test qua cổng `8001` xác nhận cả
  hai trả `200` và metadata `/version` (`dbscan-v1`, `0.2.0`, `baseline-v1`, `config_sha256`) khớp với request
  suy luận mặc định. Các kiểm tra user 101, hai preset và lỗi 422 vẫn qua. Suite hiện tại có 116 test pass.

Lệnh build, chạy thử và dừng container từ gốc repo:

```powershell
docker build -t geolife-api:0.2.0-cp2 .
docker run -d --rm --name geolife-api-local --cpus 2 --memory 2g -p 127.0.0.1:8001:8000 geolife-api:0.2.0-cp2
.\.venv\Scripts\python.exe -X utf8 scripts/check_local_api.py --port 8001
docker stop geolife-api-local
```

### Bàn giao CP2 ngày 2026-11-17

- Người dùng chuyển demo CP2 sang Kubernetes local sau khi CloudFormation không tạo được Lambda
  do lỗi 403. Lần thử AWS đã push image lên ECR; endpoint AWS chưa chạy được.
  [Quy trình AWS đã thử](docs/cp2-sqlite-deploy.md)
- Kiến trúc hiện tại là client local → Kourier áp dụng Knative Route → Blue hoặc Green → SQLite chỉ đọc.
  Chính sách traffic là Blue 100% lúc đầu, Green có URL kiểm thử riêng, canary 90/10, promote
  100% Green hoặc rollback 100% Blue. Cả hai Revision cấu hình scale-to-zero.
- Image HTTP `dev.local/geolife-api:0.2.0-sqlite-demo` dùng snapshot `geolife-1.3-demo-v1` chứa
  120.508 điểm của user `101`, `117`, `125`, `145`. `POST /v2/locations/infer` nhận `user_id`
  và trả `model_version`, `pipeline_version`, `config_version`, `config_sha256` và `data_snapshot_id`.
  `baseline-v1` và các JSON CLI đã lưu là đối chứng.
- Đã chuẩn bị [manifest Knative](infra/knative/geolife-demo.yaml),
  [script rollout](scripts/knative_rollout.py) và [hướng dẫn chạy](docs/cp2-knative-deploy.md).
  Lượt kiểm tra gần nhất có 126 test pass. HTTP local với SQLite khớp JSON CLI user `101` cho
  cả hai model, các ca ID vắng và ID kiểu số đều qua. Đã mô phỏng trạng thái rollout và kiểm tra
  bộ đếm request qua HTTP local. Kết quả trên cluster được cập nhật ở các dòng tiếp theo.
- Người dùng đã tạo cluster Docker Desktop Kubernetes `v1.36.1`, cài Knative Serving và Kourier,
  deploy hai Revision. Blue và Green qua Kourier đều khớp JSON CLI user `101`, gồm các ca ID vắng
  và sai kiểu. Lượt canary 100 request có 88 Blue, 12 Green, 0 lỗi, p95 lần lượt 594 ms và
  5.219 ms. [Kết quả](reports/cp2/release.md#canary-knative-local-ngày-2026-11-17)
- Rollback sau canary đã được kiểm tra qua URL live, HTTP 200 và kết quả user `101` khớp CLI
  heuristic. Người dùng đo 11,5309006 giây cho chuỗi lệnh rollback và toàn bộ lượt kiểm thử API.
- Hai request `/version` Blue sau thời gian rảnh và ngay sau đó đều trả 200, mất 4,283861 giây
  và 0,010708 giây. Chưa nhận output xác nhận pod bằng 0 trong lượt này. `/version` trả metadata.
- Người dùng đo riêng từng URL tag sau một lượt warmup. Green có warmup 4.969 ms, 100/100 lượt
  thành công và p95 563 ms. Blue có warmup 5.000 ms, 100/100 lượt thành công và p95 594 ms.
  Số đo dùng user `101`, chạy lần lượt Green rồi Blue. Cả hai đạt mốc p95 đề xuất trên workload
  này sau warmup. Lượt đo dùng timeout client 60 giây; deadline 10 giây chưa được cấu hình.
- Sau promote, người dùng kiểm tra URL live và nhận HTTP 200, `model_version=dbscan-v1`,
  kết quả user `101` khớp CLI và các ca ID vắng, ID kiểu số đều qua.
- **Cập nhật registry ngày 2026-11-18:** MLflow 3.18.0 chạy từ `.venv-registry` tại
  `http://127.0.0.1:5001`. Đã kiểm tra trực tiếp registry `geolife-home-office` với version 1
  (alias `heuristic-v1`) và version 2 (alias `dbscan-v1`). Cả hai `READY`, run `FINISHED`,
  tag `cli_parity=passed`. `artifacts/cp2/mlflow/registration.json` ghi cả hai bản đã tải code
  từ bundle và khớp CLI cho toàn bộ snapshot demo, gồm 4 người dùng và 120.508 điểm GPS.
  Các ca ID sai hoặc vắng đều qua. Manifest ghi ID image local và tên Revision khai báo.
  Xem [hướng dẫn registry](docs/cp2-knative-deploy.md#chuẩn-bị-mlflow-model-registry-local).
- **Cold start ngày 2026-11-18:** kiểm tra từng Revision ở 0 pod, gọi hai request suy luận liên tiếp
  cho user `101` theo URL tag qua Kourier, rồi ghi nhận pod mới Ready. Blue 5.037 ms và 543 ms,
  Green 6.177 ms và 568 ms. Cả bốn HTTP 200 và khớp CLI. Bằng chứng ở
  `artifacts/cp2/knative-cold-start.json` và [báo cáo CP2](reports/cp2/release.md).
  Khi đánh giá hiệu năng rộng hơn, đo thêm các độ dài lịch sử trên Knative. Endpoint demo CP2 chạy local.

### Bàn giao CP02 ngày 2026-11-12 · Phương án AWS trước khi chuyển hướng

- Demo mô phỏng gợi ý điểm đến trong app đặt xe. Lịch sử GPS và ID đều lấy từ GeoLife. Client gửi
  `user_id`, backend đọc GPS từ PostgreSQL rồi trả Nhà, Nơi làm việc, Nơi thường đến và `model_version`.
- Đích AWS là API Gateway → alias `prod` → một Lambda suy luận với hai version đã publish → RDS
  PostgreSQL. Blue là `heuristic-v1`, Green là `dbscan-v1`. Hai bản dùng cùng snapshot và
  `baseline-v1`. Alias `prod` thử 10% traffic trên Green trước khi promote hoặc rollback.
  UI chọn hồ sơ, benchmark mở rộng và rollback tự động có thể làm sau.
- Tại mốc 12/11, PostgreSQL/RDS là hướng chính cho AWS và SQLite chỉ đọc là phương án demo rút gọn.
  [Quy trình SQLite trên AWS](docs/cp2-sqlite-deploy.md)
- Đã thêm schema PostgreSQL, `scripts/import_postgres.py` và `POST /v2/locations/infer`.
  Lượt thử với PostgreSQL 18.1 ở chế độ standalone xác nhận 13.738 điểm của user `101` khớp từng dòng với PLT.
  Gọi WSGI chỉ với `{"user_id":"101"}` và dùng dữ liệu truy vấn từ PostgreSQL trả 200.
  Cả 15 trường trong JSON CLI đã lưu đều khớp, gồm `inference_id`, 29 lần dừng và 3 cụm.
- Người dùng đã chạy `scripts/check_local_api.py --postgres` từ PowerShell và xác nhận luồng
  **HTTP → PostgreSQL → pipeline**. `/health` và `/version` trả 200. `POST /v2/locations/infer` với
  `{"user_id":"101"}` trả 200, khớp JSON CLI, Home `predicted`, Office `unknown`.
  Ca ID không tồn tại trả 404 và ca ID kiểu số trả 422. [Lệnh tái lập](README.md#thử-api-với-postgresql-local)
- Ngày 2026-11-12, người dùng chạy `scripts/check_local_api.py --postgres-edge-cases` trên PostgreSQL
  local. Import lặp user `101` giữ 13.738 bản ghi. ID `"001"` được giữ nguyên trong response HTTP 200.
  Lịch sử một điểm trả Home và Office `unknown`. Lịch sử 100.001 điểm trả HTTP 422
  `history_too_large`. Script đã dọn snapshot kiểm tra.
- Đã so ghép cặp 182 user từ hai bộ JSON CLI với `baseline-v1`. Cả hai có cùng 10.339 lần dừng.
  DBSCAN gợi ý thêm 9 Home và 10 Office. Mọi cặp mà cả hai cùng gợi ý đều cách nhau ≤200 m.
  Ba ca tổng hợp qua WSGI đều đạt cho mỗi model. Ngưỡng canary đã có bản đề xuất, chờ số đo AWS.
  [Báo cáo CP2 và tiêu chí release](reports/cp2/release.md)
- Đã thêm `lambda_handler.py` và `Dockerfile.lambda`. Handler nhận HTTP API payload format 2.0,
  chọn model từ `MODEL_VERSION`, ghim `baseline-v1` và đọc GPS theo `user_id` qua API v2.
  Gọi handler trực tiếp với lịch sử PLT của user `101` cho kết quả khớp toàn bộ JSON CLI của cả hai model.
  Người dùng đã build image và gọi cả hai model qua emulator với PostgreSQL local. Lượt đầu trả HTTP 200
  nhưng điểm bằng chứng lệch ở chữ số cuối do thay đổi phép cộng số thực của Python 3.12.
  Sau khi cố định thứ tự cộng theo bản CLI, người dùng đã build lại một image và xác nhận qua
  emulator trên cổng `19001` cho DBSCAN và `19002` cho heuristic. Cả hai khớp toàn bộ JSON CLI
  cho user `101` với 13.738 điểm và 29 lần dừng. DBSCAN có 3 cụm, Home `predicted` và Office
  `unknown`. Heuristic có 13 cụm, Home và Office đều `unknown`. Ca ID vắng và ID kiểu số đều qua.
  [Lệnh kiểm tra local](README.md#build-và-thử-lambda-local)
- Benchmark Docker và PostgreSQL local đã chạy đủ 30 lượt đo trên hai model, với user `117`
  (341 điểm), `145` (9.907 điểm) và `125` (96.522 điểm). Lịch sử dài có handler p50
  1,95–2,05 giây và peak RSS 251,7–253,5 MiB. Đọc DB chiếm 55,4–58,2% thời gian handler
  ở lịch sử điển hình và dài theo trung vị tỷ lệ của từng lượt.
  [Kết quả benchmark local](reports/cp2/release.md#benchmark-lambda-local)
- Thư mục PostgreSQL thử nghiệm `tmp/cp2-postgres-101` chứa user `101` trong snapshot `geolife-1.3`.
  Có thể khởi động lại cụm này từ PowerShell ở gốc repo bằng:

```powershell
& 'C:/Program Files/PostgreSQL/18/bin/pg_ctl.exe' -D (Resolve-Path tmp/cp2-postgres-101).Path -l tmp/cp2-postgres-101/server.log -o '-h 127.0.0.1 -p 55432' -w start
```

## 11. Nhật ký lập kế hoạch ngày 2026-11-04

<details>
<summary>Thiết kế ban đầu và kết quả tại mốc B1</summary>

Nội dung bên dưới ghi trạng thái lịch sử tại thời điểm lập kế hoạch, trước các lượt B1–B5 đã báo cáo.

- **Yêu cầu mới nhất:** có thể bắt đầu B1, kèm 5 góp ý cuối cần sửa. Đã sửa PLAN và bắt đầu inventory B1.
  Vòng góp ý tiếp theo gồm 4 điểm nhỏ: giờ annotation/ngày, speed bins unknown khi sampling thưa,
  compute xen kẽ annotation và dấu cách. Đã sửa PLAN/report/NB06, chưa chạy GeoLife scan.
  `PLAN.md`, mục **“Bổ sung CP1 — benchmark và lựa chọn có bằng chứng”** hiện là B1 khả thi/phụ thuộc;
  B2 protocol/reference; B3 benchmark cleaning; B4 hai detector/nhãn phương tiện; B5 role baseline
  rút gọn; B6 quyết định trước CP2. Có bảng nhận xét mentor → bước xử lý và bảng phần mở rộng.
- Quy mô thiết kế ban đầu: ≥45 user (30 dev/15 held-out), 6 cửa sổ lõi 2 giờ/user =270 cửa sổ,
  kèm context; tối thiểu 20/10 user có reference stops ≥20 phút và 80/40 events target ở dev/held-out. Nếu thiếu thì
  thêm theo quy tắc cố định tối đa 10 cửa sổ/user; không đủ thì pilot, không khẳng định benchmark xác nhận.
  Một người gán lại 20% sau ≥3 ngày; báo intra-rater consistency và tính không độc lập của GPS reference.
- Reference annotate stops ≥3 phút, báo nhóm [3,5)/[5,10)/[10,20)/≥20. Target chính ≥20 phút được
  định nghĩa trước tuning, không khẳng định 20 phút tối ưu. Match với mọi reference trước, prediction
  khớp stop ngắn không tự thành FP target dài; unmatched predictions vẫn là FP. Báo trade-off thời lượng.
- Cửa sổ hợp lệ: lõi 2 h có ≥90 phút observed union, ≥8/12 bins 10 phút có interval, gap không quan sát ≤15 phút.
  B1 đếm user có ≥6/≥10 cửa sổ; mỗi user 4 general + 2 challenge low-speed 3–<20 phút (độc lập detector),
  thiếu challenge bù general theo seed và báo riêng. Có selection bias do frame baseline cleaning.
- Metric cleaning/detector: event F1 macro target dài trên cohort reference-positive users cố định; một ứng viên
  cuối so baseline bằng paired user bootstrap 5.000 lần, CI 95%. Muốn thay bản service: Δ ≥0.03 tuyệt đối
  và cận dưới CI > 0 ở held-out. Guardrail false alarm trên observed-time ngoài mọi reference stops ≥3 phút
  và vùng uncertain, không còn yêu cầu negative-only windows: macro event/negative-hour không tăng > 0.1,
  cần ≥5 user mỗi người ≥30 phút và tổng ≥5 giờ negative exposure; báo cả false-stop minutes/negative-hour.
  Đây là mức thiết kế, không phải power analysis; dev chỉ chọn, held-out mở một lần sau khóa toàn pipeline.
- Cleaning grid: vote10/vote20/vote50/mean20/no-merge và một duplicate contrast, tối đa 6 cấu hình.
  Hai detector bắt buộc × 5 OAT configs, tối đa 10; ST-DBSCAN/lịch lễ/noise/Infostop là mở rộng.
  B1 phải dự toán compute/RAM từ full runs; budget đề xuất 12 h/config, tổng 24 h, RAM ≤min(8 GiB, 50% available).
  Không đủ budget thì thu hẹp công khai trước tuning, không chạy subset rồi gọi full-data. Tổng công
  chủ động dự kiến **83–156 h** cho 270 cửa sổ (29–48 h chuẩn bị/viewer/phân tích +54–108 h annotation),
  nếu 450 cửa sổ là 119–228 h, chưa rework. B1 và B3 đều 6–10 h sau bổ sung frame/overlap graph.
  Viewer local 6–10 h và hiệu chỉnh 12 cửa sổ dev để đo thời gian
  10–20 phút/lượt giả định trước tính lại; 324 lượt cho 270 cửa sổ gồm 54 gán lại. Chưa có runtime mới.
- Full-data heuristic CLI parity được đưa lên B1 trước khi dùng heuristic CLI làm đối chứng;
  saved NB04–05 vẫn dùng được với provenance notebook, không giả vờ đã chạy CLI.
  Role baseline/simple rules và dịch cửa sổ ±1 h bắt buộc; temporal comparison chỉ khi đủ 15 user/role
  với hai khối 28 ngày, mỗi khối ≥7 observed days và ≥60 role coverage minutes. Thiếu thì ghi chưa đánh giá.
- B3 thêm toàn-dataset stay-change/lost/new/split/merge/dwell delta theo provenance/overlap, không so
  local segment IDs; kỳ vọng F1 review có thể không đổi vì conflict ít, không suy vote20 tối ưu.
  B5 timezone ablation rerun coverage/features/inference mọi user có zone/offset khác Shanghai, giữ
  stays/grouping/rules; báo role transitions hoặc no-op sau inventory. Chưa thực hiện các thí nghiệm này.
- Đã đối chiếu mentor mapping với chính ghi chú user gửi trong chat (không có bản ghi độc lập).
  Lịch dự kiến nếu bắt đầu 05/11: B1 đến 09/11, checkpoint chọn full/pilot; full dự kiến đến 18/12, CP2 từ 21/12;
  pilot 8 user × 3 cửa sổ( + 5 gán lại), dự kiến đến 20/11, CP2 từ 23/11. Chưa đặt job/event. Không chen B3–B5
  vào quỹ annotation. **Đã thay ngưỡng 90 h cố định:** ghi giờ annotation bền vững/ngày và slots thực;
  Q_rem = quỹ annotation tương lai còn lại, R_rem = lượt chưa làm gồm gán lại. Chuyển pilot/đổi lịch
  trước tuning nếu 1,2 × R_rem × p75/60 > Q_rem; p75_limit = 60 × Q_rem/(1,2 × R_rem), và công chung + 20% vừa quỹ.
  Ví dụ trước lượt đầu 19 ngày × 4 h với 324 lượt → 11,73 phút. Không trừ công đã làm hai lần trong Q_rem.
  Jobs full-data có thể user chạy tuần tự qua đêm khi protocol/grid/input/code đã khóa, không mở
  metrics held-out; chọn bằng dev sau annotation. Cache phải tương thích cleaning, budget compute
  không đổi, không tự tạo automation/khởi job. Quỹ công chuẩn bị B3–B5 tách khỏi annotation.
- Đã bỏ tập conflict-enriched annotation chưa được định nghĩa; B3 dùng stay-diff toàn dataset và trace.
  B4/B6 ghi target dài/coverage liên tục có thể không phân biệt cấu hình, giữ baseline **không chứng minh
  100 m/10 phút tối ưu**. Gaps diagnostics báo unobserved-support hours/fraction, không gọi missing time là dwell.
  Frame loại gaps nên chưa đánh giá stops trong nhà mất GPS; baseline detector cũng không bù gaps > 5 phút.
- **B1 đã làm:** tạo `notebooks/06_cp1_benchmark.ipynb`, chỉ B1; đọc audits/CSV nhỏ đủ 182 users,
  inventory 69 label files. Top 5 raw share 25,7982%; user 153 raw 2.156.994 points (8,6706%).
  Xuất `artifacts/benchmark/b1/saved_output_user_inventory.csv`, `label_file_inventory.csv`,
  `inventory_manifest.json` (config/core hashes, input fingerprint/size/mtime, git HEAD).
  Báo cáo tiến độ thật tại `reports/cp1/benchmark.md`.
- NB06 có scanner đọc mọi cleaned points theo trajectory/user: exact coverage union, frame 2 giờ trên lưới UTC,
  speed midpoint bins/challenge, gap support trừ overlapping observations, baseline-Shanghai temporal
  eligibility. Mặc định **RUN_B1_SCAN = False**, chưa chạy GeoLife. User bật True rồi Run All khi sẵn sàng.
  Có audit running/failed/completed, đếm đủ input/user/trajectory, coverage parity, RAM/time checkpoint;
  không tự chọn sample/full/pilot. Memory checks là checkpoint, không phải hard OS cap.
- NB06 `scanner_revision=b1-frame-v2`: bin coverage ≥30 s nhưng thiếu midpoint = speed unknown;
  coverage < 30 s = insufficient coverage, cả hai ngắt low-speed run, không impute. CSV thêm known/unknown/
  insufficient bins trong frame hợp lệ, windows_with_unknown_speed, challenge_unresolved_sparse_windows,
  short_challenge_supply_with_unknown_speed (user đủ 6 windows, thiếu 2 challenge kèm unknown),
  `valid_speed_pairs_gt60s`/`valid_speed_pairs_gt120s`. Đây là observability flags, chưa biết challenge thật bị mất.
- NB06 đã validate nbformat/AST, chạy phần inventory nhỏ và 7 nhóm synthetic checks; scanner end-to-end
  synthetic kiểm tra counts/coverage và audit failed khi vượt budget. Không có pipeline/GeoLife scan mới.
  Sau sửa v2 đã kiểm tra thêm dense/sparse bins, coverage<30 giây, unknown ngắt challenge và counts/
  fractions pair gap>60/120 giây; chạy end-to-end synthetic và budget-failure regression, không chạy GeoLife.
  Heuristic CLI còn lệnh riêng trong notebook, chưa chạy; raw duplicate/altitude, label intervals,
  IANA timezone và runtime/RAM infer theo user vẫn pending. B1 chưa hoàn tất.
- Mentor nhấn mạnh cần benchmark để bảo vệ lựa chọn mốc/rules, deep dive người chiếm nhiều dữ liệu,
  timestamp conflicts, tránh leakage, thử giả định local time/ngày làm việc và độ ổn định theo thời gian.
  Người dùng gợi ý dùng transport labels tìm stay trong hành trình. Nhãn mode là weak evidence theo
  interval, không tự chứng minh từng giây đang chạy xe hoặc mọi overlap đều là stay giả.
- Findings đã đọc code: duplicate key hiện là user/trajectory/timestamp/lat/lon, **không xét altitude**;
  cần đo phạm vi khác biệt với “giống mọi trường” trước khi đổi. NB03 dùng GPS point đầu làm fixed anchor;
  baseline timezone vẫn Asia/Shanghai chung, chưa tra IANA zone từ tọa độ.
- Giữ baseline 0.2.0 và artifacts hiện tại để so sánh. Đã tạo một notebook `06_cp1_benchmark.ipynb`
  và inventory `artifacts/benchmark/b1/`; chưa có frame scan mới. Phân tích tự động full dataset,
  review thủ công có manifest/phạm vi riêng; user split/time split phục vụ mục tiêu khác nhau.
  GeoLife đã xem toàn dataset nên không gọi phân vùng mới là test hoàn toàn chưa từng được xem.
  Sensitivity counts/unknown rates không thay chất lượng; role accuracy/F1 vẫn chưa thể đo thiếu nhãn.
- Người dùng đang ôn lại 5 notebook để trình bày, vừa hỏi timestamp conflict tới giây và cách gom nhóm.
  Đã giải thích all-pairs ≤20 m, nhóm đông nhất, context votes và khác với fixed-anchor stay detector.
- Có câu hỏi tỷ lệ GPS ở nước ngoài. Scan full cleaned dataset đã hoàn tất trong nền, **không cần chạy lại**.
  Kết quả `artifacts/geography/distribution.json`, boundary GeoJSON Natural Earth, tỉ lệ 1:10 triệu cùng folder.
  Chưa trả lời kết quả số cuối cùng cho người dùng vì họ chuyển sang hỏi timestamp khi scan đang lâu.
  Map-unit counts: China 23.387.907; USA 279.194; Taiwan 69.472; Italy 59.878; France 50.267; các đơn vị khác xemJSON.
  HongKong 17.940, Macao 6.708; unassigned biển/bờ biển/biên giới 138.317. Đây là phân loại theo polygon bản đồ,
  không phải khẳng định ranh giới pháp lý; không gộp unassigned thành foreign hoặc đồng nhất map units với quốc gia.
  Shapely chỉ dùng qua `uv run --no-project --with ...` trong môi trường phân tích tạm, không thêm dependency dự án.
- Worksheet review định tính chưa được điền; tùy người dùng muốn bổ sung, không phải gate mentor approval.
- Notebook heuristic đã chạy toàn bộ; standalone CLI parity còn thiếu và được đưa vào B1 kế hoạch mới
  nếu dùng CLI heuristic làm đối chứng. Đây vẫn là việc chưa thực hiện, không tự chạy trong lượt lập plan.
- CP2 dự kiến: HTTP adapter/packaging/versioning rồi AWS/release strategy. CP3: serving/latency/monitoring/drift.
  Xem PLAN.md, nhưng chỉ bắt đầu khi người dùng yêu cầu. Cloud cần chốt tài nguyên/chi phí cụ thể trước khi tạo.
- Lượt mới nhất 2026-11-04 sửa PLAN/CHECKPOINT, tạo NB06/report và bắt đầu B1 từ saved outputs/label inventory.
  Chưa thay thuật toán, chạy lại dataset/CLI, gán nhãn hoặc commit/push thêm.

</details>

## 12. Bắt đầu chat tiếp theo

1. Đọc CHECKPOINT.md và yêu cầu mới nhất của người dùng.
2. Kiểm tra `git status`, rồi chỉ đọc source/artifact liên quan; không tái tạo toàn bộ dự án.
3. Dùng kết quả full-data hiện có; tiếp tục giải thích hoặc sửa đúng phần người dùng yêu cầu.
4. Cập nhật checkpoint khi có thay đổi đáng kể về rule, tiến độ, version hoặc quyết định.
5. Khi tiếp tục CP2, đọc [bàn giao ngày 17/11](#bàn-giao-cp2-ngày-2026-11-17) và
   [hướng dẫn Knative](docs/cp2-knative-deploy.md). Kiểm tra context `docker-desktop`, rồi chạy
   từ bước khởi tạo cluster và deploy Blue nếu chưa có kết quả in-cluster. Dùng lại snapshot
   SQLite và JSON CLI đã lưu khi kiểm tra bản đóng gói. [Kế hoạch CP2](docs/cp2-implementation-plan.md)
