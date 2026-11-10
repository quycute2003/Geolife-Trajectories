# CP1 B2 — Protocol tổng hợp v1

Chuẩn bị ngày 2026-11-05. Trạng thái: code và thiết kế đã chuẩn bị; chưa chạy preparation/generator
trên GeoLife, chưa khóa manifest nguồn hoặc xác nhận B2 hoàn tất. Các số dưới đây là quyết định thiết kế.

## Nguồn, phép chia và provenance

Lượt preparation đọc đủ 24M cleaned points một lần để đối chiếu mọi cửa sổ nguồn B1 với indices/
timestamps. Không chạy detector hoặc preprocessing. Chỉ trong generator, cách ly cửa sổ có pair speed
>100 m/s, tọa độ không hợp lệ, |latitude| ≥85°, gap >300 giây hoặc ranh giới observation segment;
giữ lý do trong source_audit.csv, không sửa dữ liệu gốc. Ngưỡng 100 m/s giới hạn nguồn cho mô phỏng
di chuyển mặt đất, không chứng minh các cửa sổ bị cách ly là lỗi (có thể là máy bay).

Mỗi user đủ điều kiện giữ tối đa 5 source windows theo thứ tự SHA256(seed 20261104, source ID).
Đủ 5 realization seed dù user chỉ có một nguồn; không gọi các seed là người độc lập. Toàn bộ nguồn
đủ điều kiện được fingerprint theo relative timestamps và tọa độ; các user có bản sao y hệt cùng
nhóm trước phép chia. Các nhóm được sắp theo hash rồi phân vào nửa ít user hơn. Hai phần gần 50/50;
không tách nhóm bản sao chỉ để cân bằng. Quota độc lập đếm theo nhóm nguồn sao chép; nếu có
nhóm chứa nhiều user, B4 phải bootstrap cả nhóm cùng nhau, không coi bản sao là quan sát độc lập. Cách này không bắt mọi bản sao gần giống/khác cadence.

Selection seed 100000–100004; final seed 200000–200004. Stream con được tạo bằng SHA256, bao gồm
user/cell/seed. B1 đã EDA toàn dataset: phép chia không xóa kiến thức đã có. Profile test chỉ dùng
cho mô phỏng của chính user test; mức stress chung chỉ tính từ selection.

Cohort báo đủ 182 users, nhóm không có nguồn, baseline ≥5 stays, mẫu số stay có nhãn hợp lệ và giao.
Mask nhãn lấy UTC/GMT, hợp nhất cùng mode, loại phần thời gian chồng mode mâu thuẫn. Nếu một nửa
có <15 users với ≥5 baseline stays, hoặc không có mẫu số phủ định, chốt chế độ mô tả: giữ baseline,
không chọn ứng viên và không sinh/chạy xác nhận cuối. Cohort radius chưa có per-user saved outputs
ghi unknown; đủ baseline chưa bảo đảm (c) sẽ đủ. Không đổi phép chia để vượt gate.

## Latent path và sampling

Source polyline lấy từ GPS thật đã cleaning, được coi là **đường đi latent do thiết kế**; nhiễu sẵn
trong polyline không biến mất. Loại các vertex tọa độ lặp liên tiếp khỏi mô tả latent, giữ tọa độ và
thời gian gốc trong source cache. Nội suy tuyến tính tạo tiến triển dương giữa vertex còn lại; đường
đi có thể quay đầu nhưng không có dwell không được khai báo. Đây không phải đáp án cho trace thật.

Stop được chèn tại nửa thời gian của nguồn: giữ vị trí cố định trong duration, dịch timestamps
phía sau đúng duration. Cadence lấy **cả chuỗi dt liên tiếp của cửa sổ nguồn của user**, dịch vòng
điểm bắt đầu và lặp theo block để kéo dài đồng hồ. Không rút dt độc lập hoặc ép fix tại endpoint truth.
Chu kỳ lặp là giới hạn của mô hình, không đại diện mọi thay đổi sampling của user. Gaps thực nghiệm
lấy thời lượng gap block >300 giây của chính user từ B1 (trọng số tần suất), đặt giữa stop.

Nhiễu được thêm lên mọi fix sampled của latent path, cả moving và stop. Observation segments được
đánh lại khi gap >300 giây. Mất toàn bộ observations của stop vẫn giữ event truth; nếu mất cả case,
case vẫn tồn tại trong manifest và phải tính FN khi chấm. Không dùng detector để lọc ca sinh.

## Ma trận và noise

Mọi user nguồn của phần đang xét có đủ 5 seed cho mỗi ô. 71 ô gồm:

| Nhóm | Thiết kế | Số ô |
|---|---|---:|
| Chính | 4 dwell groups × 5/15/30 m RMS × Gaussian/drift/outlier | 36 |
| Stress | 4 dwell groups × 1 mức stress × 3 họ nhiễu | 12 |
| Dropout | 4 dwell groups × empirical/25%/50%, 15 m drift | 12 |
| Không quan sát stop | 20–60 phút, mất toàn stop, 15 m drift | 1 |
| Hai stop | tâm cách 25/75/150 m × connector 2/10 phút, mỗi stop 20–60 phút, 15 m drift | 6 |
| Phủ định | moving thuần/đi chậm/creeping/đèn đỏ, 15 m drift | 4 |

Dwell giây theo 5 seed: [180,299,300,301,599]; [600,601,900,1199,600];
[1200,1201,2400,3600,1200]; [3601,5400,7200,10800,3601]. Nhóm tương ứng [3,10),
[10,20), [20,60], >60 phút. Dwell không phân bố đều: chủ ý khảo sát lân cận ngưỡng, không đại diện
tần suất stop thật. Số seed hữu hạn không bao phủ mọi thời lượng giữa các mốc.

RMS là căn kỳ vọng bình phương sai số khoảng cách hai chiều. Gaussian: sigma mỗi trục RMS/√2.
Drift dùng OU hai chiều có RMS stationary đã biết, tương quan exp(-dt/120 giây), khởi tạo stationary;
không gọi đây là random walk không giới hạn. Outlier: Gaussian scale mixture, xác suất lỗi 1% với
seed index 0/2/4 và 5% với 1/3, multiplier U[3,10]; scale chia theo kỳ vọng multiplier² để các họ
có cùng target RMS. Không normalize/cắt realized event. Báo empirical RMS/p95 trên toàn case.

5/15/30 m là dải thăm dò chứ không suy từ residual B1 thành GPS error truth. Stress = làm tròn lên
10 m của max(100 m, max p95 proxy noise của các user selection). Proxy có lẫn cong đường/gia tốc:
mức stress có thể rất cao, phải báo raw value, không coi là nhiễu GPS điển hình hoặc hạ để tăng F1.

Hai stop nối bằng chuyển động tuyến tính đã biết; hậu cảnh phía sau được tịnh tiến để giữ liên tục.
Đây là ca kiểm merge/split có kiểm soát, không tái hiện road network. Hard negatives dùng source
polyline trải thành 1 giờ; đi chậm scale tổng quãng đường xuống 1.800 m, creeping xuống 300 m,
vẫn tiến triển dương; đèn đỏ chèn physical hold 60/120/180 giây nhưng không có place-visit truth.
Stop detector chỉ dùng hình học không bảo đảm suy được ngữ nghĩa ghé/chờ. FP/giờ chính chỉ dùng
moving thuần; hold đèn đỏ không tính là latent moving. Báo từng nhóm riêng, không gộp F1.

## ST-DBSCAN và giao diện B4

ST-DBSCAN là đối chứng gom GPS thô thành stay event: eps spatial 100 m, eps time 300 giây,
MinPts =3 (gồm point đang xét), min dwell =600 giây. Đây là **cấu hình thăm dò của dự án**, không
phải mặc định paper hoặc optimum. Xử lý theo case/observation segment; haversine cho không gian,
absolute time cho thời gian, AND hai điều kiện neighborhood. Cluster → min/max timestamp, median
lat/lon (unwrap longitude); duration <600 giây bị loại. Không dùng bán kính envelope bổ sung hoặc
rule fixed-anchor để lọc cluster; chaining là hành vi cần đo. Đây là adaptation dùng hai chiều,
không tái lập toàn bộ xử lý thuộc tính non-spatial/adjacent-cluster của Birant & Kut (2007).

Không chọn winner ST-DBSCAN từ một cấu hình. Fixed-anchor/median-updated dùng grid và gate (a)–(d)
của PLAN.md; B4 chưa triển khai ở B2. Các case có timestamps nguồn chồng nhau: **chạy detector từng
case độc lập**. Không áp dụng loại overlap xuyên case của user gốc; macro-average theo source_user_id.
Detectors chỉ nhận file observations; không nhận latent coords, source IDs hay đáp án truth.

## Chấm và freeze

Matching one-to-one tối đa tổng temporal IoU, IoU ≥0,5 và haversine tâm ≤100 m, tie-break event ID.
Intervals [start,end). TP/FP/FN và NA/zero theo PLAN.md. Split/merge graph overlap >0, tâm ≤100 m.
Báo metrics từng cell/user: event precision/recall/F1, median/p95 start/end/center error trên matched
events kèm matched fraction; split/truth, merge/predictions; FP/latent moving hour trên pure_move,
kèm observed exposure khi B4 tính. Quota ≥10 users độc lập mỗi phần/cell; mỗi pure_move có 1 giờ
latent moving ×5 seed/user. Không lấy point count làm trọng số chất lượng.

protocol.json chứa mã nguồn/hash tài liệu/input profile/cache, bản chụp khối CP1 của PLAN (gồm
ngưỡng (a)–(d)), phép chia, seed, ST-DBSCAN params,
cohort và mode. Corpus ghi matrix và protocol hash. Preparation/generation không ghi đè namespace.
Audit còn ghi upper bound số fixes từ cadence nhỏ nhất của các nguồn đã cache; đây là trần quy
mô dữ liệu, không phải dự báo runtime. Corpus completed có SHA256 từng file và số ca qua invariants.
Code đổi sau preparation phải tạo namespace mới. Final corpus chỉ sinh khi tới lượt xác nhận;
không đọc final traces để sửa generator hoặc cấu hình. Sửa sau khi xem final làm mất tính xác nhận.

Runtime chưa đo; không hứa 71 ô × mọi user ×5 seeds nằm trong quỹ. Jobs dừng khi vượt RAM/12 giờ
hoặc quỹ compute tích lũy 24 giờ; failed/partial không coi là corpus completed, không âm thầm giảm
user/seed/cell. Lưu audit của mọi lượt, kể cả thất bại, để cộng compute cho lần sau.

## Nguồn và giới hạn

- [Detecting activity locations from raw GPS data (2013)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3637118/): dùng trace tổng hợp
  với stop biết trước, khảo sát nhiễu, thời lượng và hai stop gần nhau; không sao chép metric đếm stop.
- [Birant & Kut (2007)](https://doi.org/10.1016/j.datak.2006.01.013): nguồn ST-DBSCAN.
- [Kato et al. (2024)](https://doi.org/10.1016/j.procs.2024.06.095): độ nhạy theo log interval;
  kết quả dataset khác không tự chuyển sang GeoLife.
- [Kennedy et al. (2026), preprint](https://arxiv.org/abs/2607.19312): tổng hợp, noise/dropout,
  temporal/spatial metrics; đây là tài liệu tham khảo phương pháp, không phải chuẩn chung.

Tổng hợp sạch và có kiểm soát hơn thực tế; thiếu chuyển động trong tòa nhà, GNSS multipath thực,
ngữ nghĩa ghé địa điểm và độc lập với polyline nguồn. Không suy F1 tổng hợp thành accuracy GeoLife
hay Home/Office. B2 hoàn tất chỉ sau preparation/corpus/invariant audits thực tế, không tick khi mới viết code.
