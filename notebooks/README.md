# Notebooks CP1

| Notebook | Nội dung |
|---|---|
| `01_dataset_overview.ipynb` | Cấu trúc/quy mô dataset, quality audit, sampling/gaps trước cleaning |
| `02_preprocessing.ipynb` | Scan conflict spread toàn dataset → chọn ngưỡng → spatial/context vote → gộp cụm được ưu tiên → audit trước–sau |

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
NB02 không còn để core chọn fix theo lat/lon nhỏ nhất. Core/CLI raw vẫn giữ baseline cũ cho tới khi đồng bộ policy sau.
Hai notebook chưa làm stay detection, clustering hoặc Home/Office inference.

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
