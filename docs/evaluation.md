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

`artifacts/evaluation/manual-review-sample.csv` là bảng review được tạo từ kết quả đã chạy trên
toàn bộ 182 users. Bảng có 32 dòng: 8 trường hợp được chọn có chủ đích để xem các tình huống khác
nhau (dự đoán, từ chối, hai model bất đồng, Home/Office trùng vị trí, dữ liệu thưa và ứng viên
phân tán). Đây là mẫu kiểm tra định tính, **không phải mẫu ngẫu nhiên để suy rộng tỷ lệ lỗi**.

Mỗi user có bốn dòng (Home/Office × DBSCAN/heuristic). `candidate_cluster_id` là cluster được chọn
nếu model dự đoán; nếu model trả `unknown`, đó là ứng viên xếp đầu để ta xem vì sao bị từ chối.
Cluster IDs chỉ có nghĩa trong đúng user và model. Mở `map_file`, chọn user ở danh sách, rồi đối
chiếu vị trí với cột thời gian/độ phân tán trong CSV. Cột `review_plausibility` có thể ghi
`plausible`, `implausible`, hoặc `unclear`; ghi mức không chắc và lý do vào các cột cuối.

Chỉ đánh giá **tính hợp lý của dấu vết thời gian/vị trí**. GPS không cho biết chắc một nơi là nhà
hay văn phòng; không dùng nhận xét này làm ground truth, accuracy/F1, hoặc bằng chứng hiệu năng.
Không sao chép nhãn dự đoán vào cột review. Bảng này chỉ là một mẫu review định tính và để trống
các cột nhận xét cho reviewer.

`manual-review.csv` và `manual-review-template.csv` là bảng cũ từ thí nghiệm subset ban đầu;
không dùng chúng làm mẫu review kết quả toàn dataset. Artifacts và bản đồ nằm trong `artifacts/`
đã được Git ignore.

## Diagnostics báo cáo

Stays, clusters, noise/stays, radius max/p95, role prediction/unknown rates, POI count và coverage.
Unknown rate phải nêu role và mẫu số. Với zero stays, noise proportion convention=0 không có nghĩa model tốt.
Processing times là một lần chạy offline, bao gồm preprocessing/features; không gồm ZIP loading/plotting,
không phải API latency benchmark hay so sánh sync/async.

Actual results và các quan sát trực quan: `reports/cp1/results.md`.
Chưa có reviewer độc lập hoặc bộ proxy labels được adjudicate. Accuracy/F1/calibration không được đo.
