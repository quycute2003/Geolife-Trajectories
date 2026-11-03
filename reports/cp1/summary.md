# CP1 — Home / Office / POI inference

## Trạng thái

**Baseline offline đã hoàn tất và được kiểm chứng trên toàn dataset.** OpenAPI 3.1 draft đã
validate để người dùng trình bày trực tiếp. Chưa có HTTP server. Không có nhãn ground truth
Home/Office nên semantic accuracy chưa đo được.

## Bài toán và luồng xử lý

Đầu vào là lịch sử GPS thô của **một user**, gồm trajectory ID, tọa độ, thời điểm UTC và altitude
nếu có. Pipeline chuẩn hóa timestamp conflicts, tìm các lần dừng (stays), gom stays thành cluster,
tính bằng chứng theo thời gian/coverage, rồi trả Home, Office, POIs và lý do abstain. Thiếu bằng
chứng thì trả `unknown`; điểm số là heuristic evidence, không phải xác suất.

`data → preprocessing → stays → clustering → temporal features → role inference → JSON`

Các bước được khảo sát trên toàn bộ 182 users trong notebooks 01–05 trước khi đối chiếu với CLI.

## Bằng chứng toàn dataset

| Chỉ số | Kết quả |
|---|---:|
| Users / trajectory files | 182 / 18.670 |
| Raw → cleaned GPS points | 24.876.978 → 24.177.772 |
| Stays | 10.339 |
| DBSCAN locations / noise stays | 552 / 3.296 |
| DBSCAN Home predicted / unknown | 37 / 145 users |
| DBSCAN Office predicted / unknown | 18 / 164 users |
| DBSCAN POIs | 202 |

CLI DBSCAN 0.2.0 được so với saved outputs NB02–05 ở tất cả users. Không có sai khác ngoài
floating-point tolerance `rtol=1e-10`, `atol=1e-8`; sai lệch lớn nhất xấp xỉ `8.98e-9`.
Đối chiếu gồm per-user audit counters, stays, membership/noise labels, coverage/features,
candidate scores/reasons/alternatives, POIs và conflict/removal point traces. Record IDs không
so trực tiếp vì chúng được gán theo phạm vi của mỗi lượt chạy.

OpenAPI validation ngày 2026-11-03: **188/188** responses/examples đạt JSON Schema và format
checks (182 real-data DBSCAN responses + 6 contract examples). Test suite gần nhất: **115 passed**.

## Giới hạn cần giữ rõ

- Không có ground truth Home/Office; không tuyên bố accuracy, F1 hay score calibration.
- Stay/clustering thresholds và score weights là baseline/sensitivity assumptions, chưa được tối ưu
  bằng nhãn độc lập.
- Heuristic notebook đã chạy toàn dataset; standalone heuristic CLI 0.2.0 chưa chạy lại.
- `artifacts/evaluation/manual-review-sample.csv` có 8 users × 2 models × 2 roles để review định tính.
  Các cột reviewer đang để trống; không dùng sample có chủ đích này để ước lượng lỗi toàn dataset.
- OpenAPI là proposal. Chưa có HTTP routes, auth enforcement, resource guards, deployment hay load test.
  CP1 chỉ bàn giao bản thiết kế; implementation service nằm ngoài phạm vi hiện tại.

## Tài liệu kèm theo

- `reports/cp1/results.md` — số liệu chi tiết, sensitivity và lịch sử các phase.
- `docs/architecture.md`, `docs/assumptions.md`, `docs/data_dictionary.md` — cách hoạt động và rule.
- `docs/evaluation.md` — review procedure và giới hạn kết luận.
- `openapi.yaml` — API design draft để trình bày cùng báo cáo CP1.
- `PLAN.md` — tiến độ và các checkpoint tiếp theo.

Chi tiết đối chiếu máy đọc được trong local ignored artifact `artifacts/pipeline/dbscan-v1/notebook-comparison.json`.
