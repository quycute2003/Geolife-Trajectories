# Notebook 01 — raw dataset overview

Ngày: 2026-10-31. Trạng thái: **đã chạy kỹ thuật; chờ cùng người dùng đọc kết quả**.

**Cập nhật 2026-11-02:** người dùng yêu cầu bỏ ảnh 03–06. Đã xóa ảnh và cell code/giải thích
tương ứng ở source và bản làm việc. Hiện còn **28 cells (13 code), hai charts**: user volume và sampling/gaps.
Các số liệu sáu charts bên dưới ghi lại lần chạy ban đầu, không phải cấu trúc notebook hiện tại.

**Cấu trúc mới nhất:** chỉ giữ `notebooks/01_dataset_overview.ipynb`, gồm cả code, outputs và ghi chú.
Ảnh/cache ở `artifacts/overview/`. Không còn folder `artifacts/notebooks/` hoặc hai bản source/executed;
các mô tả tách bản phía dưới là lịch sử của lần triển khai ban đầu.

**Dataset local:** đã giải nén tại `data/Geolife Trajectories 1.3/`. Notebook tự đọc thư mục này,
không yêu cầu biến môi trường khi mở trực tiếp. Cache hiện dùng metadata fingerprint (tên, size, mtime),
các mô tả cache ZIP SHA256 bên dưới thuộc lần chạy ban đầu.

**Dọn code phụ:** đã bỏ `open_notebook.ps1`, `run_notebook.py` và generator tạm `build_overview.py`.
Mở/chạy notebook trực tiếp bằng VS Code hoặc Jupyter; các script liệt kê trong lịch sử bên dưới không còn dùng.

## Completed

Notebook 39 cells (19 code/20 Markdown), sáu charts: user volume, sampling/gaps,
daily coverage, UTC/local recording hours, distance/speed và spatial overview.
Không gọi cleaning, stay detector, clustering hay inference. Có câu hỏi tự kiểm tra và chỗ ghi nhận xét.

## Files Changed

`notebooks/01_dataset_overview.ipynb`, `notebooks/README.md`, `scripts/run_notebook.py`,
`scripts/open_notebook.ps1`, `PLAN.md`, `README.md`, `.gitignore`, `pyproject.toml`, `uv.lock`.
Bản đã chạy/PNG/summary ở `artifacts/notebooks/` (private, gitignored).

## Technical Decisions

Đếm file/record lines toàn ZIP theo luồng; cache kiểm tra SHA256/file list. Giữ raw tokens riêng,
parse trên bản sao, không xóa records. Users 000/001/002 là development subset, không đại diện ngẫu nhiên.
Consecutive diagnostics tính trong từng trajectory; timezone Asia/Shanghai được khai báo là giả định.
Source notebook không chứa outputs; runner không ghi đè bản đã chạy có thể có notes của người dùng.

## Validation

Notebook đã chạy từ kernel mới: 19 code cells hoàn thành, 0 cell errors, 6 charts được render và xem.
Toàn ZIP: 182 users, 18.670 trajectories, 24.876.978 record lines.
Subset: **530.694 raw = 530.694 parsed rows, 0 rows removed**.
Audit thấy một missing altitude, sáu distinct positions trong các timestamp-conflict groups của user 002;
đây chưa phải sáu points nên xóa. Median sampling của users 000/001/002 lần lượt 5/4/5 giây;
vẫn có 653/206/566 positive intervals >5 phút. Không dùng observations này để chốt cleaning rules.
Existing suite sau cài notebook dependencies: **48 tests passed**; `uv lock --check` thành công.

## Limitations

Không validate mọi GPS value trên toàn ZIP. Chưa kết luận outlier nào phải xóa.
Day/hour point counts không phải dwell/time coverage; quỹ đạo không có basemap.
User review, câu trả lời tự kiểm tra và cleaning decisions chưa hoàn tất.

## Next Steps

Cùng đọc **phần 1–3**: file mẫu, đơn vị point/trajectory/user và phân phối dung lượng.
Sau đó mới đọc quality/sampling. Chưa tạo notebook 02 hoặc mở rộng API/cloud.
