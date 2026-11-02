# GeoLife Home / Office / POI Inference — CP1

Baseline Python chạy offline, từ GPS đến stay events và các địa điểm thường ghé.
Home/Office là **ứng viên theo hành vi**, có thể `unknown`; POI không phải business category.
Không có ground truth Home/Office, evidence score không phải xác suất.

Kế hoạch và trạng thái: [PLAN.md](PLAN.md). Kết quả thực nghiệm: [reports/cp1/results.md](reports/cp1/results.md).
**OpenAPI đang chờ mentor review. Repository không chứa HTTP server hoặc cloud infrastructure.**

## Bắt đầu học từ notebook

Hiện tại đi lại theo hướng hiểu dữ liệu trước. Bản pipeline phía dưới là bản thử tham khảo,
không thay thế việc đọc chart và thảo luận quyết định. Kế hoạch học đủ sáu tuần ở `PLAN.md`.

- Khám phá dữ liệu: [01_dataset_overview.ipynb](notebooks/01_dataset_overview.ipynb).
- Preprocessing toàn dataset và so trước–sau: [02_preprocessing.ipynb](notebooks/02_preprocessing.ipynb); đã sửa code, chờ người dùng chạy.
- NB02 scan phân phối timestamp conflict trước; đặt ngưỡng ở phần 5 rồi gộp mean nhóm gần, cách ly nhóm xa có truy vết. Không tự đoán ngưỡng.
- Mỗi bài chỉ có một notebook. Kết quả xuất vào `artifacts/overview/` và `artifacts/preprocessing/`.
- [Hướng dẫn mở notebook, đọc theo từng buổi và các câu hỏi cần hiểu](notebooks/README.md).
- Notebook 01 là EDA ban đầu có phần subset; notebook 02 xử lý mọi user/trajectory theo luồng. Từ yêu cầu mới nhất, các bước phân tích/xử lý mới mặc định toàn dataset. Chưa làm stays/inference trong các notebooks này.

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
py -X utf8 -m geolife_inference eda --dataset $dataset --users 000 001 002 --output artifacts/development
py -X utf8 -m geolife_inference infer --dataset $dataset --users 000 001 002 --model dbscan-v1 --config configs/baseline.toml --output artifacts/development --plot
py -X utf8 -m geolife_inference infer --dataset $dataset --users 000 001 002 --model heuristic-v1 --output artifacts/development
```

Output riêng tư nằm trong `artifacts/` (gitignored): JSON, stay-event CSV và bản đồ PNG offline.
Đọc `home.status`, `office.status`, `candidate`, `alternatives`, `coverage`, `diagnostics` và `warnings`.
`completed` chỉ có nghĩa pipeline hoàn thành; không đảm bảo có dự đoán.
CLI từ chối user không tồn tại, model/config không hỗ trợ và cấu trúc PLT sai.

Chạy lại EDA, so sánh hai model và sensitivity experiments:

```powershell
py -X utf8 scripts/run_experiments.py --dataset $dataset
py -X utf8 scripts/validate_contract.py --results artifacts/evaluation
```

Notebook 01 đếm toàn bộ record lines trong thư mục dataset. Lệnh experiment chỉ chạy inference
trên users 000/001/002 và một user có ít trajectory nhất. Với input là ZIP, có thể thêm
`--scan-inventory` để đếm record lines toàn ZIP. Ghi đè output trong thư mục đích; dùng `--output`
khác để giữ lần chạy trước. Thời gian thực nghiệm là offline processing time, không phải API latency.

## Kiến trúc

`data → preprocessing → stays → clustering → features → inference`, điều phối bởi `pipeline`.
CLI và evaluation tách khỏi core; không phụ thuộc FastAPI/AWS.
`heuristic-v1` dùng fixed-anchor radius grouping; `dbscan-v1` dùng DBSCAN Haversine.
Cả hai cùng preprocessing, stay detector, temporal features và output contract.

- [Architecture](docs/architecture.md), [assumptions](docs/assumptions.md), [data dictionary](docs/data_dictionary.md)
- [Research notes](docs/research_notes.md), [evaluation procedure](docs/evaluation.md)
- [OpenAPI](openapi.yaml), [mentor review checklist](docs/mentor_review.md)
- [Phase reports](reports/cp1/phase_log.md)

## Dữ liệu và giới hạn

Đọc điều khoản trong User Guide 1.3 trước khi sử dụng dataset; guide ghi non-commercial use
và có giới hạn phân phối. Không thêm ZIP, PLT, tọa độ suy luận hoặc bản đồ người dùng vào Git.
Notebook dùng một file duy nhất, có thể giữ cả code, bảng kết quả và biểu đồ để học.
Không tự động push GitHub. Không triển khai API trước khi người dùng xác nhận mentor phê duyệt OpenAPI.
Sampling thiếu, lịch làm việc khác giờ hành chính, du lịch, GPS jitter và đi bộ chậm đều có thể gây sai.
Các ngưỡng mặc định là giả thuyết, chưa tối ưu hoặc xác nhận bằng nhãn độc lập.
