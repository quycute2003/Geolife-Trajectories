const places = [
  { id: 'station', name: 'Ga Vườn Xanh', address: '12 đường Gió Mát', x: 453, y: 459 },
  { id: 'home', name: 'Nhà', address: '18 ngõ Ngọc Lan', x: 501, y: 360 },
  { id: 'office', name: 'Công ty', address: 'Tòa nhà Ánh Dương, số 128 đường Hướng Dương, khu đô thị Ven Sông, khu thương mại trung tâm Bờ Đông', x: 753, y: 429 },
  { id: 'garden', name: 'Công viên Vườn Xanh', address: 'Cổng phía nam, đường Gió Mát', x: 394, y: 310 },
  { id: 'square', name: 'Quảng trường Nắng', address: '6 đường Nắng Sớm', x: 347, y: 571 },
  { id: 'library', name: 'Thư viện Bờ Đông', address: '26 đường Hướng Dương', x: 813, y: 397 },
  { id: 'riverside', name: 'Công viên Ven Sông', x: 795, y: 336 },
];

const profiles = [
  { id: 'full', name: 'Người dùng mẫu 01', address: 'Nhà, Công ty và một nơi hay đến', suggestions: [
    { placeId: 'home', name: 'Nhà', icon: 'home' },
    { placeId: 'office', name: 'Công ty', icon: 'office' },
    { placeId: 'garden', name: 'Nơi hay đến 1', icon: 'poi' },
  ] },
  { id: 'partial', name: 'Người dùng mẫu 02', address: 'Có Nhà và một nơi hay đến', suggestions: [
    { placeId: 'home', name: 'Nhà', icon: 'home' },
    { placeId: 'riverside', name: 'Nơi hay đến 1', icon: 'poi' },
  ] },
  { id: 'empty', name: 'Người dùng mẫu 03', address: 'Tự tìm địa điểm hoặc chọn trên bản đồ', suggestions: [] },
];
