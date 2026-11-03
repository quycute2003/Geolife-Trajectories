# GeoLife Home / Office / POI Inference — CP1

Baseline Python chạy offline, từ GPS đến stay events và các địa điểm thường ghé.
Home/Office là **ứng viên theo hành vi**, có thể `unknown`; POI không phải business category.
Không có ground truth Home/Office, evidence score không phải xác suất.

Kế hoạch và trạng thái: [PLAN.md](PLAN.md). Kết quả thực nghiệm: [reports/cp1/results.md](reports/cp1/results.md).
**OpenAPI là bản thiết kế trong CP1 để người dùng trình bày trực tiếp. Repository không chứa HTTP server hoặc cloud infrastructure.**

## Bắt đầu học từ notebook

Hiện tại đi lại theo hướng hiểu dữ liệu trước. Bản pipeline phía dưới là bản thử tham khảo,
không thay thế việc đọc chart và thảo luận quyết định. Kế hoạch học đủ sáu tuần ở `PLAN.md`.

- Khám phá dữ liệu: [01_dataset_overview.ipynb](notebooks/01_dataset_overview.ipynb).
- Preprocessing toàn dataset và so trước–sau: [02_preprocessing.ipynb](notebooks/02_preprocessing.ipynb); đã chạy đủ 182 users / 18.670 trajectories.
- Tìm lần dừng trên cleaned dataset: [03_stay_detection.ipynb](notebooks/03_stay_detection.ipynb); đã chạy đủ input, baseline 10.339 stays của 151/182 users, có sensitivity toàn dataset.
- Gom các lần dừng thành địa điểm: [04_location_grouping.ipynb](notebooks/04_location_grouping.ipynb); đã chạy toàn stays. Phần 7b có map tương tác hai phương pháp, chọn mọi user, zoom và popup; mở riêng `artifacts/locations/03_location_map.html` nếu cần.
- Suy luận Home/Office/POI: [05_role_inference.ipynb](notebooks/05_role_inference.ipynb); người dùng đã chạy toàn dataset và sensitivity, có giải thích score/unknown, chart và map nhãn.
- NB02 scan phân phối timestamp conflict trước; đặt ngưỡng ở phần 5 rồi gộp mean nhóm gần, cách ly nhóm xa có truy vết. Không tự đoán ngưỡng.
- Mỗi bài chỉ có một notebook. Kết quả xuất vào thư mục tương ứng trong `artifacts/`.
- [Hướng dẫn mở notebook, đọc theo từng buổi và các câu hỏi cần hiểu](notebooks/README.md).
- Notebook 01 là EDA ban đầu có phần subset. Từ notebook 02, mọi xử lý mới mặc định toàn dataset; NB03–05 lần lượt tìm stays, gom địa điểm và suy luận vai trò.

## Setup trên Windows / PowerShell

Yêu cầu: Python 3.11–3.13 qua `py`, Git, và `uv` (đã có trong môi trường phát triển).
Các lệnh dưới đây chạy từ thư mục gốc repository:

```powershell
uv sync --frozen --group notebook --python (py -c "import sys; print(sys.executable)")
# Chọn môi trường riêng cho py, không cần thay đổi PowerShell execution policy.
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 -c "import sys; print(sys.executable)"
py -X utf8 -m pytest -q
```

`py` phải trỏ tới `.venv\Scripts\python.exe` sau khi đặt `VIRTUAL_ENV`.
`uv.lock` khóa cả phụ thuộc trực tiếp và gián tiếp. Không dùng môi trường Python chung cho dự án.

## Dataset và chạy thử

Dataset đã giải nén tại `data/Geolife Trajectories 1.3/`. Mở notebook trực tiếp không cần biến môi trường.
Core CLI vẫn có thể dùng GeoLife ZIP hoặc thư mục qua `--dataset`;
không có đường dẫn máy cá nhân hardcode trong mã nguồn. Loader cũng nhận thư mục
chứa cấu trúc `<user_id>/Trajectory/*.plt`, hoặc thư mục cha của cấu trúc đó.
Dataset local được giải nén từ ZIP do người dùng cung cấp, không tải lại từ mạng.

```powershell
$dataset = Join-Path (Get-Location) 'data\Geolife Trajectories 1.3'
py -X utf8 -m geolife_inference inventory --dataset $dataset
py -X utf8 -m geolife_inference eda --dataset $dataset --output artifacts/eda-full
py -X utf8 -m geolife_inference infer --dataset $dataset --model dbscan-v1 --config configs/baseline.toml --output artifacts/pipeline/dbscan-v1 --audit-points
py -X utf8 -m geolife_inference infer --dataset $dataset --model heuristic-v1 --config configs/baseline.toml --output artifacts/pipeline/heuristic-v1 --audit-points
```

Hai lệnh infer trên là hai lựa chọn model, mỗi lệnh mặc định xử lý **mọi user**, không phải chỉ ba users.
Không cần chạy notebook trước: loader → preprocessing voting → stays → grouping → temporal evidence → JSON.
Core 0.2.0 đã dùng cùng policy `spatial_vote_context_v2` với NB02, ngưỡng gộp 20 m trong config,
giữ observation segments khi conflict không giải quyết được. `--users` chỉ giới hạn khi bạn chủ động truyền vào.
CLI đọc một user trong RAM mỗi lần; không khẳng định streaming trong một user rất lớn.

Mỗi user có `<user>-<model>.json` và `-stays.csv`. Cờ `--audit-points` thêm `-removed.csv`
(invalid/exact duplicates) và `-conflicts.csv` (mọi distinct conflict fixes, mean contributors và điểm tách riêng).
Không xuất bản cleaned GPS thứ hai mặc định. `run-audit.json` trong thư mục output ghi phạm vi,
users/files dự kiến và đã xử lý, counts và running/failed/completed; không coi lượt thất bại là full completed.
Chọn thư mục output riêng cho mỗi model/lượt chạy để không lẫn kết quả cũ.

Python cũng có một hàm duy nhất để gọi toàn bộ pipeline:

```python
from geolife_inference.config import Config
from geolife_inference.pipeline import run_pipeline

run = run_pipeline(points, user_id="003", config=Config(), model_version="dbscan-v1")
result = run.result
```

`points` là DataFrame GPS thô của đúng user đó, gồm user_id/trajectory_id/latitude/longitude/altitude_m/timestamp.
Timestamp phải UTC có timezone; altitude missing dùng NaN. `run.points`, `run.stays`,
`run.removed_points`, `run.conflict_points` giúp kiểm tra các bước. Không truyền CSV đã làm sạch
vào raw entry point để áp dụng cleaning lần nữa. NB02 dùng helper riêng cho rows đã resolve.

Output riêng tư nằm trong `artifacts/` (gitignored): JSON, stay-event CSV và bản đồ PNG offline.
Đọc `home.status`, `office.status`, `candidate`, `alternatives`, `coverage`, `diagnostics` và `warnings`.
`completed` chỉ có nghĩa pipeline hoàn thành; không đảm bảo có dự đoán.
CLI từ chối user không tồn tại, model/config không hỗ trợ và cấu trúc PLT sai.

Chạy lại EDA, so sánh hai model và sensitivity experiments:

```powershell
py -X utf8 scripts/run_experiments.py --dataset $dataset
py -X utf8 scripts/validate_contract.py --results artifacts/evaluation
```

Notebook 01 đếm toàn bộ record lines trong thư mục dataset. Lệnh experiment mặc định chạy mọi users;
chỉ dùng subset nếu người dùng chủ động truyền `--users`. Với input là ZIP, có thể thêm
`--scan-inventory` để đếm record lines toàn ZIP. Ghi đè output trong thư mục đích; dùng `--output`
khác để giữ lần chạy trước. Thời gian thực nghiệm là offline processing time, không phải API latency.

Người dùng đã chạy CLI DBSCAN 0.2.0 trên toàn dataset; đã đối chiếu mọi saved outputs với NB02–05:
counters, stays, memberships, coverage/features, predictions và point traces đều khớp trong float tolerance.
Report ở `artifacts/pipeline/dbscan-v1/notebook-comparison.json`; các artifact notebook được giữ nguyên.
CLI heuristic 0.2.0 chưa chạy lại, còn các tests synthetic đã kiểm tra cả hai models.
Bộ review định tính 8 users hiện tại nằm ở `artifacts/evaluation/manual-review-sample.csv`; chưa có nhãn reviewer.

## Kiến trúc

`data → preprocessing → stays → clustering → features → inference`, điều phối bởi `pipeline`.
CLI và evaluation tách khỏi core; không phụ thuộc FastAPI/AWS.
`heuristic-v1` dùng fixed-anchor radius grouping; `dbscan-v1` dùng DBSCAN Haversine.
Cả hai cùng preprocessing, stay detector, temporal features và output contract.

- [Architecture](docs/architecture.md), [assumptions](docs/assumptions.md), [data dictionary](docs/data_dictionary.md)
- [Research notes](docs/research_notes.md), [evaluation procedure](docs/evaluation.md)
- [OpenAPI](openapi.yaml), [CP1 summary](reports/cp1/summary.md)
- [Phase reports](reports/cp1/phase_log.md)

## Dữ liệu và giới hạn

Đọc điều khoản trong User Guide 1.3 trước khi sử dụng dataset; guide ghi non-commercial use
và có giới hạn phân phối. Không thêm ZIP, PLT, tọa độ suy luận hoặc bản đồ người dùng vào Git.
Notebook dùng một file duy nhất, có thể giữ cả code, bảng kết quả và biểu đồ để học.
Không tự động push GitHub. CP1 dừng ở pipeline offline và OpenAPI draft; không có endpoint đang chạy.
Sampling thiếu, lịch làm việc khác giờ hành chính, du lịch, GPS jitter và đi bộ chậm đều có thể gây sai.
Các ngưỡng mặc định là giả thuyết, chưa tối ưu hoặc xác nhận bằng nhãn độc lập.
