# Notebooks CP1

| Notebook | Nội dung |
|---|---|
| `01_dataset_overview.ipynb` | Cấu trúc/quy mô dataset, quality audit, sampling/gaps trước cleaning |
| `02_preprocessing.ipynb` | Scan conflict spread toàn dataset → chọn ngưỡng → spatial/context vote → gộp cụm được ưu tiên → audit trước–sau |
| `03_stay_detection.ipynb` | Cleaned GPS toàn dataset → anchor 100 m / 10 phút → stays, overlap audit, phân phối duration và mọi users; sensitivity tùy chọn |
| `04_location_grouping.ipynb` | Toàn bộ stays → so heuristic/DBSCAN → locations, noise, số ngày ghé và độ phân tán; sensitivity tùy chọn |
| `05_role_inference.ipynb` | Toàn bộ users/clusters → coverage GPS + khung giờ → điểm bằng chứng → Home/Office/POI hoặc unknown; charts, map và sensitivity |

Notebook 02 chạy toàn bộ dataset: lấy mọi user từ thư mục, xử lý từng trajectory và tổng hợp đầy đủ.
Không giới hạn ba users và không lấy mẫu points để tính audit hoặc ECDF.
Notebook 01 là bản khảo sát cũ có phần subset; từ yêu cầu mới nhất, các bước xử lý mới mặc định dùng toàn dataset.
NB02 đã được người dùng chạy đủ 182 users/18.670 trajectories, policy `spatial_vote_context_v2`, ngưỡng 20m.
Code trên ổ đĩa được đồng bộ với lần chạy trước khi commit; nhãn hiện tại `NB02-VOTE-V3`.
Chỉ giữ các bước xử lý, kết quả và giải thích cần thiết; không có phần tự kiểm tra/trả lời câu hỏi.

## Mở trong VS Code

1. Mở notebook cần dùng tại `notebooks/`.
2. Chọn kernel `.venv` / **Python (GeoLife)**.
3. Chạy từng cell bằng Shift+Enter, hoặc Restart Kernel and Run All Cells.

Dataset tự đọc từ `data/Geolife Trajectories 1.3/`, không bắt buộc biến môi trường.
Nếu tab vẫn có code cũ, nạp lại file từ ổ đĩa sau khi giữ các ghi chú chưa lưu.

## Mở bằng JupyterLab

Từ thư mục gốc dự án, PowerShell:

```powershell
uv sync --frozen --group notebook --python (py -c "import sys; print(sys.executable)")
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 -m jupyterlab notebooks/02_preprocessing.ipynb
```

Không cần script tạo/mở/chạy notebook riêng.

## Kết quả xuất ra

- `artifacts/overview/`: hai ảnh và cache/tổng hợp của notebook 01.
- `artifacts/preprocessing/01_record_counts.png`: tổng points trước–sau trên toàn dataset và số bị loại theo rule.
- `artifacts/preprocessing/02_sampling_before_after.png`: ECDF chính xác từ mọi positive pair của tất cả users, cùng trục trước–sau.
- `artifacts/preprocessing/conflict_groups.csv`, `conflict_scan.json`: độ lệch từng nhóm conflict và trạng thái scan toàn dataset.
- `artifacts/preprocessing/03_conflict_spread.png`: phân phối độ lệch để quyết định ngưỡng gộp.
- `artifacts/preprocessing/conflict_points.csv`: các points conflict sau dedup, kèm group ID, spread, decision và ID output; nhóm xa được giữ ở đây để review.
- `artifacts/preprocessing/audit.json`: trạng thái cleaning, policy mean/quarantine, ngưỡng, phạm vi thực tế, audit từng user và pair frequencies.
- `artifacts/preprocessing/cleaned_points.csv.gz`: points sau cleaning/gộp mean, source_point_count, flags và observation segment.
- `artifacts/preprocessing/removed_points.csv`: chỉ invalid và exact duplicates; points đóng góp mean không bị gọi là deleted.

Không thay đổi các PLT gốc, không tạo bản notebook thứ hai cho cùng một bài.
Notebook 02 giữ missing altitude và các points ở high-speed pairs/long gaps.
Độ lệch conflict là khoảng cách Haversine lớn nhất giữa mọi pair trong nhóm, không chỉ khoảng cách tới điểm đầu.
Nhóm trong ngưỡng gộp mean. Nhóm vượt ngưỡng chọn cụm đông nhất; nếu hòa, dùng context vote trong cùng trajectory.
Các điểm ngoài cụm thắng được giữ riêng. Chỉ timestamp hoàn toàn chưa giải quyết mới làm ngắt observation segment.
Core/CLI 0.2.0 đã đồng bộ voting với NB02. Notebook giữ phần vote hiển thị để đọc;
import `diagnose_resolved_points as preprocess` chỉ tính diagnostics trên rows đã resolve,
giữ mean provenance và tránh vote hai lần. Khi vừa cập nhật core, Restart Kernel trước khi chạy notebook.
Notebook 03 làm stay detection; notebook 04 gom địa điểm; notebook 05 suy luận Home/Office/POI theo thời gian ghé.

## Cách chạy notebook 02 hiện tại

1. Chạy phần 1–4 để scan mọi conflict và xem phân phối spread trên toàn dataset.
2. Ở phần 5, đặt `CONFLICT_MERGE_THRESHOLD_M` dựa trên số liệu vừa xem; mặc định `None`, không tự đặt 100m hay percentile.
3. Chạy lại từ phần 5 trở đi để áp dụng spatial/context voting và xuất toàn bộ cleaned dataset.

Run All khi ngưỡng còn `None` chỉ làm bước scan và bỏ qua cleaning, không báo preprocessing completed.
Sau khi đổi ngưỡng, scan có thể dùng cache đã khớp metadata thay vì đọc lại toàn bộ GPS.
Cell xử lý toàn dataset ghi tiến độ theo user.
CSV được ghi theo luồng vào `.partial`, chỉ thay file kết quả chính khi mọi users/files xử lý thành công.
Các artifact còn từ lần subset trước chưa phải kết quả full; kiểm tra `scope: full_dataset`, `status: completed`
và đủ expected/completed users, trajectories trong `audit.json` sau khi chạy;
policy phải là `spatial_vote_context_v2` và đúng ngưỡng đã chọn.

## Chạy notebook 03

Mở `03_stay_detection.ipynb`, chọn **Python (GeoLife)** và chạy từ trên xuống.
NB03 dùng `artifacts/preprocessing/cleaned_points.csv.gz` và kiểm tra audit NB02 đã hoàn tất toàn dataset.
Đọc file theo khối, ghép tiếp trajectory vắt qua hai khối; không giới hạn users hoặc points.
Không nối qua user/trajectory/observation_segment, gaps > 5 phút hoặc timestamp không tăng.

Kết quả nằm trong `artifacts/stays/`: `stays.csv`, `overlapping_stays.csv`, `per_user.csv`, `audit.json`
và hai PNG tổng hợp (duration, số stays/tổng giờ theo từng user). Các stays overlap được tách riêng
theo rule giữ lần bắt đầu trước, không xóa GPS input và không khẳng định file nào đúng hơn.
Chỉ dùng output khi audit `completed` và counts từng user khớp NB02.

Phần 8 mặc định `RUN_SENSITIVITY = False`; bật để chạy thêm bốn cấu hình trên toàn input.
Chỉ thay radius hoặc min duration từng lần, giữ gap 5 phút; kết quả so sánh ở `sensitivity.csv`.
Không nối lại các segments mà NB02 đã cắt. Khi đổi CONFIG baseline, chạy lại từ phần 4.
Người dùng đã chạy NB03 và sensitivity toàn dataset: baseline 10.339 stays của 151/182 users,
không có overlap; 3.592,999 giờ trong stays. Ngưỡng vẫn là baseline, chưa tối ưu bằng nhãn độc lập.

## Chạy notebook 04

Mở `04_location_grouping.ipynb`, chọn **Python (GeoLife)** và chạy từ trên xuống.
Input là toàn bộ `artifacts/stays/stays.csv` của NB03; không đọc lại GPS để clustering.
Kiểm tra audit/CSV đúng lượt chạy và đủ phạm vi, so heuristic-v1 với dbscan-v1 riêng từng user.
Baseline eps 100 m / min_samples 3; mỗi input là một stay, không phải một GPS point.

`artifacts/locations/` chứa `stay_assignments.csv` (giữ cả noise), `locations.csv`,
`comparison.csv`, `per_user.csv`, `audit.json`, hai chart tổng hợp và `03_location_map.html`.
Per-user table chứa mọi user, cả người không có stay/location. Cluster IDs chỉ có ý nghĩa trong từng method/user.
Đếm ngày theo Asia/Shanghai, union các khoảng chạm/chồng trong cùng địa điểm nhưng không lấp gap dương.
Ứng viên thường ghé >= 3 ngày chưa phải nhãn Home/Office.

Phần 9 có sensitivity DBSCAN tùy chọn, mặc định tắt; bật để thử eps 50/200 m, min_samples 2/5,
mọi cấu hình vẫn dùng toàn stays. Không ghi đè baseline; lưu `sensitivity.csv` và `sensitivity_audit.json` riêng.
Người dùng đã chạy NB04 baseline đủ 10.339 stays / 182 users. Baseline hiện có 3.577 địa điểm heuristic,
552 địa điểm DBSCAN và 3.296 noise stays của DBSCAN; đây chưa phải nhãn đúng/sai.

Phần **7b** thêm bản đồ đường phố tương tác: hai phương pháp cạnh nhau, chọn mọi user hoặc toàn dataset,
zoom đồng bộ, popup chi tiết stay/cluster, bật/tắt noise và vòng độ rộng. Nút **Zoom nơi thường ghé**
ưu tiên nơi có nhiều ngày ghé nhất. Map dùng mọi stays/locations, chỉ lọc góc nhìn để dễ xem.
Chỉ xuất một HTML, không tạo file riêng cho từng user. Có thể mở HTML trực tiếp bằng trình duyệt;
nếu iframe trong VS Code không hiện, dùng file HTML. Cần internet để tải Leaflet và nền OpenStreetMap.
Renderer nằm trong `src/geolife_inference/maps.py`; không thêm package hoặc script khởi động mới.
Map đã được xuất từ CSV có sẵn và kiểm tra trình duyệt, không chạy lại grouping.

## Chạy notebook 05

Mở `05_role_inference.ipynb`, chọn **Python (GeoLife)**, **Restart Kernel rồi Run All** để nạp core mới.
NB05 giữ nguyên toàn bộ assignments/clusters của NB04, chạy cả heuristic-v1 và dbscan-v1,
thống kê đủ mọi user (kể cả không có stay/cluster). Không chạy lại clustering, không dùng subset.

Phần 3 đọc toàn bộ cleaned GPS theo từng trajectory để tính coverage/observed days đúng mẫu số,
không dùng riêng stay points. Tôn trọng user/trajectory/observation_segment và gap 5 phút;
nén các khoảng nối tiếp rồi union để tránh đếm trùng các file chồng nhau. Lần sau có cache kiểm tra
fingerprints/config/counts; đổi khung giờ làm cache mất hiệu lực, đổi ngưỡng score không cần đọc GPS lại.

Phase 5 dùng Asia/Shanghai: Home 22h–6h, Office 9h–18h Mon–Fri; tính phần giao thực tế,
không gán cả stay theo giờ bắt đầu. Có bảng giải thích từng thành phần score, eligibility và alternatives.
Score chưa hiệu chuẩn, weights chưa train; relative share loại noise khỏi mẫu số nên hiển thị thêm
share gồm noise để đối chiếu. Home/Office có thể cùng nơi; POI không phải business category.

`artifacts/inference/` chứa coverage/cache audit, `location_features.csv`, `candidate_scores.csv`,
`decisions.csv`, `pois.csv`, `user_diagnostics.csv`, `summary.csv`, `predictions.json`, `audit.json`,
hai chart và `03_role_map.html`. Map thêm H/O/H+O/P lên clusters cũ, giữ noise và mọi users;
unknown không tạo tọa độ giả. Mở HTML bằng trình duyệt nếu nền không hiện trong notebook.

Phần 8 lọc bảng theo user chỉ để xem, sau khi mọi user đã được tính. Phần 11 sensitivity tùy chọn,
mặc định tắt: thay min days/dwell/score/share từng yếu tố trên toàn users, không đổi clustering/khung giờ,
không ghi đè baseline. Chỉ dùng output khi audit completed và input/config vẫn khớp.
Người dùng đã chạy NB05 baseline và sensitivity đủ 182 users; DBSCAN có 37 Home / 18 Office theo rule.
Các nhãn vẫn là suy luận, chưa có ground truth. Người dùng đã chạy CLI DBSCAN 0.2.0 toàn GeoLife;
đã đối chiếu mọi saved outputs với notebooks và khớp trong float tolerance.

## Pipeline một lượt sau khi review notebooks

Core 0.2.0 có `run_pipeline(points, user_id, config, model_version)` và CLI chạy từ GeoLife tới JSON
không cần notebooks/artifact trung gian. CLI mặc định mọi users, hai model dùng cùng preprocessing.
Xem lệnh full-data và cờ `--audit-points` trong README gốc. Core đã được đối chiếu với reference NB02
và các bước notebook bằng synthetic fixtures. Sau đó đã đối chiếu CLI DBSCAN full-data người dùng chạy:
mọi counters/stays/memberships/coverage/features/predictions/traces khớp. CLI heuristic mới chưa chạy lại.
Các outputs/ghi chú/sensitivity settings hiện có trong notebooks được giữ nguyên.
