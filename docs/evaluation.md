# Evaluation procedure — no authoritative Home/Office labels

## Ba loại thông tin tách biệt

1. Ground truth: hiện **không có** nhãn Home/Office được xác thực.
2. Manual proxy label: nếu reviewer đọc lịch sử và suy đoán role, ghi lý do/uncertainty,
   reviewer và ngày review; không đổi tên proxy thành ground truth.
3. Algorithm prediction: JSON/CSV model output, không được copy làm reference label để tính accuracy.

## Reproduce

Sau setup trong README:

```powershell
py -X utf8 -m pytest -q
py -X utf8 scripts/run_experiments.py --dataset $dataset --scan-inventory
py -X utf8 scripts/validate_contract.py --results artifacts/evaluation
```

`$dataset` là đường dẫn ZIP ngoài repository. Kết quả mới ghi vào `artifacts/evaluation/`.
Inventory scan đếm nonblank record lines sau sáu header, không validate giá trị toàn bộ 24,9 triệu dòng.
Inference/EDA thực hiện trên users 000/001/002 và sparse user có ít trajectory nhất
(tie chọn ID nhỏ nhất: bản ZIP hiện tại là 049). Không chọn theo prediction quality.

Experiment grid, mỗi user một lần mỗi setting:

| Experiment | Changed assumption |
|---|---|
| baseline/dbscan-v1 | 100m stay radius, 10min stay, 5min max gap, DBSCAN 100m/3 |
| baseline/heuristic-v1 | Cùng pipeline, thay DBSCAN bằng radius matching |
| distance-50m / 200m | Chỉ đổi stay distance |
| stay-20min | Chỉ đổi minimum stay duration |
| gap-1min | Chỉ đổi maximum sampling gap |
| eps-200m | Chỉ đổi DBSCAN eps |
| min-samples-5 | Chỉ đổi DBSCAN min_samples |

Không dùng grid này để công bố chọn ngưỡng tối ưu; không có validation labels.
Không so cluster IDs giữa models như thể cùng định danh. Muốn so vị trí, dùng geographical distance
giữa centers và overlap observed events; đọc artifact riêng tư, không xuất tọa độ lên báo cáo công khai.

## Manual review

1. Xem EDA: số dates, sampled-time coverage, gaps, speeds và thời gian quan sát.
2. Xem `<user>-<model>.png`: toàn bộ observed extent và local 3km focus. Không có basemap/geocoding.
   Plot subsample tối đa khoảng 15–30k GPS fixes để dễ render; inference dùng toàn bộ points.
3. Xem `<user>-<model>-stays.csv`: kiểm tra một số intervals đầu/cuối, sampling gaps, noise labels.
4. Xem JSON: all location features, Home/Office candidate + alternatives, role overlap, days/weeks,
   dispersion và relative share. Travel regions có thể tạo candidates gây nhiễu.
5. Copy `manual-review-template.csv` thành `manual-review.csv` để ghi nhãn proxy/uncertainty.
   Script không ghi vào file có nhãn reviewer. Không điền nhãn bằng prediction rồi tính performance.
6. Reviewer nên đọc temporal evidence và trajectories trước khi quyết định proxy labels;
   nếu có thể, che prediction trong lần review đầu để giảm confirmation bias.
7. Giữ toàn bộ review files và maps trong `artifacts/`, không commit Git.

## Diagnostics báo cáo

Stays, clusters, noise/stays, radius max/p95, role prediction/unknown rates, POI count và coverage.
Unknown rate phải nêu role và mẫu số. Với zero stays, noise proportion convention=0 không có nghĩa model tốt.
Processing times là một lần chạy offline, bao gồm preprocessing/features; không gồm ZIP loading/plotting,
không phải API latency benchmark hay so sánh sync/async.

Actual results và các quan sát trực quan: `reports/cp1/results.md`.
Chưa có reviewer độc lập hoặc bộ proxy labels được adjudicate. Accuracy/F1/calibration không được đo.
