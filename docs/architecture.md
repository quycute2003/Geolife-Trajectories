# Architecture — Checkpoint 1

## Data flow và trách nhiệm

1. `data.py`: inventory, đọc từng PLT từ ZIP/thư mục; timezone UTC, altitude meters.
2. `preprocessing.py`, `geo.py`: validate, audit invalid/duplicate/conflicting rows, distances và speeds.
3. `stays.py`: scan theo user/trajectory; chặn gaps; loại stay overlaps giữa các file.
4. `clustering.py`: cùng input stay events; hai phương pháp nhóm per user.
5. `features.py`: union intervals, temporal overlap, observation coverage, cluster extent.
6. `inference.py`: chọn role, evidence components, abstention và recurring POIs.
7. `pipeline.py`: orchestration một user, deterministic inference ID, structured result.
8. `evaluation.py`, `cli.py`: EDA, offline PNG và JSON/CSV; không có serving dependency.

`PipelineRun` trả result JSON và hai DataFrame points/stays để phục vụ kiểm tra riêng tư.
Mỗi user được load vào bộ nhớ một lần; CLI xử lý tuần tự từng user. ZIP không được giải nén toàn bộ.
Không hứa streaming cho user rất lớn. DBSCAN có thể tốn bộ nhớ khi neighborhoods dày;
thêm resource limits ở HTTP boundary sau khi contract được duyệt và load testing.

## Tính tái lập

- `uv.lock`, Python version và config có trong tài liệu; model và pipeline versions có trong result.
- Stable timestamp/trajectory sorting, deterministic conflict resolution, n_jobs=1, không random sampling trong inference.
- UUID5 dựa trên hash DataFrame sạch + user/model/config. Không dùng ID làm bằng chứng quyền truy cập.
- UUID không phải artifact hash của raw input: nhiều input sau khi làm sạch có thể cùng ID nhưng audit khác nhau.
- Mỗi baseline có cùng input/output để so sánh ở checkpoint sau. Chưa có registry.

## Data boundaries

PLT loader chịu lỗi giá trị: invalid coordinate/time được audit rồi loại trước inference.
Malformed cấu trúc dòng gây lỗi, không silently skip. Thứ tự dòng được chuẩn hóa theo timestamp.
API đề xuất validate chặt và từ chối request có giá trị invalid; chưa có adapter/endpoints.
Tests validate core JSON theo schema response để tránh contract drift.

Log mặc định chỉ ghi counts, không ghi GPS coordinates, user ID hay lịch sử di chuyển.
Artifacts riêng tư nằm trong `artifacts/`; báo cáo trong Git chỉ có diagnostics tổng hợp.

## Ranh giới CP1

OpenAPI 3.1 là tài liệu proposal. Không có HTTP runtime, AWS, Docker deployment,
monitoring hay async infrastructure. Khi mentor duyệt, HTTP adapter có thể gọi `run_pipeline`
sau validation/auth/resource guards mà không thay đổi thuật toán core.
