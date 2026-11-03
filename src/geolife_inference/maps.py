"""One HTML map for all stay assignments; no grouping or point sampling here."""
import json
from pathlib import Path
from collections.abc import Iterable

import pandas as pd

from .config import Config


def write_location_map(assignments: pd.DataFrame, locations: pd.DataFrame,
                       user_ids: Iterable[str], output: str | Path, config: Config,
                       *, role_labels: pd.DataFrame | None = None) -> Path:
    """Export two Leaflet maps with shared user/layer controls.

    Every input stay/location is embedded in one file. Leaflet and OpenStreetMap
    tiles load over the internet when opened; no Python map dependency is needed.
    """
    users = list(map(str, user_ids))
    if len(users) != len(set(users)):
        raise ValueError("Map user IDs must be unique")
    if not assignments["stay_id"].is_unique:
        raise ValueError("Map stay IDs must be unique")
    for frame in (assignments, locations):
        if not set(frame["user_id"].astype(str)).issubset(users):
            raise ValueError("Map contains a user outside the supplied full user list")
    columns = ["user_id", "stay_id", "latitude", "longitude", "duration_minutes",
               "start_time", "end_time", "heuristic-v1_cluster_id", "dbscan-v1_cluster_id"]
    points = assignments[columns].copy()
    points["user_id"] = points["user_id"].astype(str)
    points["stay_id"] = points["stay_id"].astype(str)
    for column in ("start_time", "end_time"):
        points[column] = pd.to_datetime(points[column], utc=True).map(lambda t: t.isoformat())
    place_columns = ["method", "user_id", "cluster_id", "latitude", "longitude",
                     "stay_event_count", "visit_count", "unique_visit_days",
                     "total_dwell_minutes", "radius_max_m"]
    places = locations[place_columns].copy()
    places["user_id"] = places["user_id"].astype(str)
    labels = []
    if role_labels is not None:
        valid_keys = set(zip(places.method, places.user_id, places.cluster_id))
        for row in role_labels.to_dict("records"):
            key = (row["method"], str(row["user_id"]), int(row["cluster_id"]))
            if row["role"] not in ("home", "office", "poi") or key not in valid_keys:
                raise ValueError("Role labels must reference an existing non-noise location and valid role")
            labels.append(dict(method=key[0], user_id=key[1], cluster_id=key[2], role=row["role"]))
    payload = dict(users=users, stays=points.to_dict("records"), locations=places.to_dict("records"),
                   eps_m=config.eps_m, min_samples=config.min_samples, timezone=config.timezone,
                   has_roles=role_labels is not None, role_labels=labels)
    # Prevent user-controlled strings from closing the JSON script element.
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    data = data.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.write_text(_HTML.replace("__MAP_DATA__", data), encoding="utf-8")
    partial.replace(target)
    return target


_HTML = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GeoLife — So sánh địa điểm</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
*{box-sizing:border-box}body{margin:0;background:#eef2f7;color:#17243a;font:14px/1.5 system-ui,sans-serif}
header{padding:18px 22px 12px;background:white;border-bottom:1px solid #dce3ed}
h1{font-size:22px;margin:0 0 4px}p{margin:4px 0;color:#53637a}
.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:13px}
select,button{font:inherit;padding:7px 10px;border:1px solid #bdc9d9;border-radius:7px;background:white;color:#17243a}
select{min-width:230px}button{cursor:pointer}label{display:inline-flex;align-items:center;gap:5px}
.maps{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px}
.card{background:white;border:1px solid #dce3ed;border-radius:10px;overflow:hidden;min-width:0}
.heading{padding:10px 14px;min-height:82px}.heading h2{font-size:16px;margin:0}.stats{color:#53637a;font-size:13px}
.map{height:530px}.legend{padding:0 18px 12px;display:flex;gap:15px;flex-wrap:wrap;color:#53637a}
.dot{display:inline-block;width:9px;height:9px;background:#4f46e5;border-radius:50%;margin-right:4px}
.ring{background:white;border:2px solid #4f46e5;width:13px;height:13px;vertical-align:middle}.gray{background:#7b8797}
#notice{font-size:13px;margin-top:8px}.leaflet-popup-content{min-width:190px;line-height:1.7}
.popup-title{font-weight:700;margin-bottom:3px}.foot{padding:0 18px 14px;color:#53637a;font-size:12px}
.role-marker{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;color:white;
 font-weight:750;font-size:12px;border:2px solid white;box-shadow:0 1px 5px #17243a80;background:#2563eb}
.role-home{background:#16a34a}.role-office{background:#e85b17}.role-both{background:#9333ea}
@media(max-width:850px){.maps{grid-template-columns:1fr}.map{height:420px}}
</style></head><body>
<header><h1>Từ lần dừng đến địa điểm</h1>
<p id="scope"></p>
<div class="controls">
<label>User <select id="user" aria-label="Chọn user"></select></label>
<label><input type="checkbox" id="stays" checked>Stays đã gom</label>
<label><input type="checkbox" id="noise" checked>Noise</label>
<label><input type="checkbox" id="extent">Độ rộng cluster</label>
<label><input type="checkbox" id="sync" checked>Đồng bộ zoom</label>
<button id="fit" type="button">Xem hết vùng đã chọn</button>
<button id="focus" type="button" title="Ưu tiên địa điểm DBSCAN có nhiều ngày ghé nhất; nếu chưa có thì dùng heuristic">Zoom nơi thường ghé</button>
</div><p id="notice">Đang tải bản đồ…</p></header>
<main class="maps">
<section class="card"><div class="heading"><h2>Ghép theo bán kính</h2><div id="stats0" class="stats"></div></div><div id="map0" class="map" aria-label="Bản đồ heuristic"></div></section>
<section class="card"><div class="heading"><h2>DBSCAN</h2><div id="stats1" class="stats"></div></div><div id="map1" class="map" aria-label="Bản đồ DBSCAN"></div></section>
</main><div class="legend">
<span><i class="dot"></i>Chấm màu: vị trí một stay</span>
<span><i class="dot gray"></i>Chấm xám: noise</span>
<span><i class="dot ring"></i>Vòng đậm: vị trí đại diện cluster, bấm để xem chi tiết</span>
<span id="role-legend" hidden>H: Home · O: Office · H+O: cả hai · P: POI (nhãn suy luận)</span>
</div><div class="foot">Màu chỉ phân biệt cluster trong từng bản đồ, không ghép nhãn giữa hai phương pháp.
Vòng độ rộng dùng khoảng cách lớn nhất từ vị trí stay tới median cluster, không phải ranh giới thực tế hay vòng eps.
Không vẽ đường nối giữa stays vì chưa biết quãng đường đi. Thời gian hiển thị theo <span id="timezone"></span>.</div>
<script type="application/json" id="map-data">__MAP_DATA__</script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('map-data').textContent);
  const el = id => document.getElementById(id);
  const fmt = n => Number(n).toLocaleString('vi-VN', {maximumFractionDigits: 1});
  const escape = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  el('scope').textContent = `${fmt(data.stays.length)} stays · ${fmt(data.locations.length)} địa điểm cộng hai phương pháp · ${data.users.length} users. Chọn user để xem rõ; dữ liệu không lấy mẫu.`;
  el('timezone').textContent = data.timezone;
  el('role-legend').hidden = !data.has_roles;
  const labelsByLocation = new Map();
  for (const row of data.role_labels) {
    const key = JSON.stringify([row.method, row.user_id, row.cluster_id]);
    if (!labelsByLocation.has(key)) labelsByLocation.set(key, []);
    labelsByLocation.get(key).push(row.role);
  }
  if (typeof L === 'undefined') {
    el('notice').textContent = 'Chưa tải được thư viện bản đồ. Kiểm tra kết nối internet rồi mở lại file HTML.';
    return;
  }
  const counts = new Map(data.users.map(u => [u, 0]));
  data.stays.forEach(s => counts.set(s.user_id, counts.get(s.user_id) + 1));
  const all = document.createElement('option'); all.value = ''; all.textContent = 'Toàn bộ users'; el('user').append(all);
  data.users.forEach(u => {
    const option = document.createElement('option'); option.value = u;
    option.textContent = `${u} — ${fmt(counts.get(u))} stays`;
    el('user').append(option);
  });
  // Start with the first user with stays for a readable local view; every user remains selectable.
  el('user').value = data.users.find(u => counts.get(u) > 0) || '';
  const methods = ['heuristic-v1', 'dbscan-v1'];
  const maps = methods.map((_, i) => {
    const map = L.map(`map${i}`, {preferCanvas: true, maxZoom: 19}).setView([20, 0], 2);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).on('tileerror', () => {el('notice').textContent = 'Một số ô nền chưa tải được; các stays và clusters vẫn có thể xem. Kiểm tra internet nếu nền trống.';}).addTo(map);
    L.control.scale({imperial: false}).addTo(map);
    return map;
  });
  const layers = maps.map(map => L.layerGroup().addTo(map));
  let syncing = false;
  maps.forEach((map, i) => map.on('moveend', () => {
    if (syncing || !el('sync').checked) return;
    syncing = true;
    maps[1 - i].setView(map.getCenter(), map.getZoom(), {animate: false});
    syncing = false;
  }));
  function color(user, cluster) {
    if (cluster === -1) return '#7b8797';
    let hash = 0;
    for (const c of `${user}:${cluster}`) hash = (Math.imul(hash, 31) + c.charCodeAt(0)) | 0;
    return `hsl(${(hash >>> 0) * 137.508 % 360}, 72%, 43%)`;
  }
  function selection() {
    const user = el('user').value;
    return {stays: data.stays.filter(s => !user || s.user_id === user),
            places: data.locations.filter(p => !user || p.user_id === user)};
  }
  function fit() {
    const selected = selection().stays;
    const bounds = L.latLngBounds(selected.map(s => [s.latitude, s.longitude]));
    syncing = true;
    maps.forEach(map => bounds.isValid() ? map.fitBounds(bounds, {padding: [28, 28], maxZoom: 16, animate: false}) : map.setView([20, 0], 2));
    syncing = false;
  }
  function draw() {
    const selected = selection();
    layers.forEach(layer => layer.clearLayers());
    methods.forEach((method, i) => {
      const places = selected.places.filter(p => p.method === method);
      const clusterKey = `${method}_cluster_id`;
      const noiseCount = selected.stays.filter(s => s[clusterKey] === -1).length;
      const settings = method === 'dbscan-v1' ? `eps ${fmt(data.eps_m)} m · min_samples ${data.min_samples}` : `Mốc cố định · bán kính ${fmt(data.eps_m)} m`;
      el(`stats${i}`).textContent = `${settings} | ${fmt(selected.stays.length)} stays · ${fmt(places.length)} địa điểm · ${fmt(noiseCount)} noise`;
      if (data.has_roles) {
        const labels = data.role_labels.filter(r => r.method === method && (!el('user').value || r.user_id === el('user').value));
        const count = role => labels.filter(r => r.role === role).length;
        el(`stats${i}`).textContent += el('user').value ?
          ` | Home: ${count('home') ? 'H' : 'unknown'} · Office: ${count('office') ? 'O' : 'unknown'} · ${count('poi')} POI` :
          ` | ${count('home')} Home · ${count('office')} Office · ${count('poi')} POI`;
      }
      if (el('extent').checked) places.forEach(p => {
        L.circle([p.latitude, p.longitude], {radius: p.radius_max_m, color: color(p.user_id, p.cluster_id),
          weight: 1, opacity: .5, fillOpacity: .04, interactive: false}).addTo(layers[i]);
      });
      selected.stays.forEach(s => {
        const cluster = s[clusterKey], noise = cluster === -1;
        if (noise ? !el('noise').checked : !el('stays').checked) return;
        const time = value => new Date(value).toLocaleString('vi-VN', {timeZone: data.timezone});
        L.circleMarker([s.latitude, s.longitude], {radius: noise ? 3 : 4, weight: .7,
          color: color(s.user_id, cluster), fillColor: color(s.user_id, cluster), fillOpacity: .7})
          .bindTooltip(`User ${escape(s.user_id)} · ${escape(s.stay_id)} · ${noise ? 'noise' : `cluster ${cluster}`}`)
          .bindPopup(`<div class="popup-title">Stay ${escape(s.stay_id)}</div>User ${escape(s.user_id)} · ${noise ? 'Noise' : `Cluster ${cluster}`}<br>${escape(time(s.start_time))}<br>→ ${escape(time(s.end_time))}<br>Thời lượng: ${fmt(s.duration_minutes)} phút`)
          .addTo(layers[i]);
      });
      places.forEach(p => {
        const roles = labelsByLocation.get(JSON.stringify([method, p.user_id, p.cluster_id])) || [];
        let marker;
        if (roles.length) {
          const both = roles.includes('home') && roles.includes('office');
          const role = both ? 'both' : roles[0];
          const text = both ? 'H+O' : {home:'H',office:'O',poi:'P'}[role];
          marker = L.marker([p.latitude, p.longitude], {icon:L.divIcon({
            className:'', html:`<div class="role-marker role-${role}">${text}</div>`,
            iconSize:[30,30],iconAnchor:[15,15]})});
        } else {
          marker = L.circleMarker([p.latitude, p.longitude], {radius: 8, weight: 3,
            color: color(p.user_id, p.cluster_id), fillColor: '#fff', fillOpacity: .9});
        }
        marker
          .bindTooltip(`User ${escape(p.user_id)} · cluster ${p.cluster_id} · ${fmt(p.unique_visit_days)} ngày`)
          .bindPopup(`<div class="popup-title">User ${escape(p.user_id)} · Cluster ${p.cluster_id}</div>${escape(method)}${roles.length ? '<br>Nhãn suy luận: '+roles.map(escape).join(' + ') : ''}<br>${fmt(p.stay_event_count)} stays · ${fmt(p.visit_count)} đợt ghé<br>${fmt(p.unique_visit_days)} ngày có quan sát<br>Tổng dừng: ${fmt(p.total_dwell_minutes / 60)} giờ<br>Xa median nhất: ${fmt(p.radius_max_m)} m`)
          .addTo(layers[i]);
      });
    });
    el('notice').textContent = selected.stays.length ? 'Cuộn để zoom, kéo để di chuyển, bấm chấm/vòng để xem chi tiết. Hai bản đồ dùng cùng vùng nhìn.' : 'User này không có stay đạt rule ở NB03; cả hai bản đồ không có điểm.';
  }
  el('user').addEventListener('change', () => {draw(); fit();});
  ['stays', 'noise', 'extent'].forEach(id => el(id).addEventListener('change', draw));
  el('fit').addEventListener('click', fit);
  el('focus').addEventListener('click', () => {
    const places = selection().places;
    const dbscan = places.filter(p => p.method === 'dbscan-v1');
    const candidates = (dbscan.length ? dbscan : places).slice().sort((a, b) =>
      b.unique_visit_days - a.unique_visit_days || b.total_dwell_minutes - a.total_dwell_minutes);
    if (!candidates.length) {fit(); return;}
    syncing = true;
    maps.forEach(map => map.setView([candidates[0].latitude, candidates[0].longitude], 16, {animate: false}));
    syncing = false;
  });
  el('sync').addEventListener('change', () => {
    if (el('sync').checked) maps[1].setView(maps[0].getCenter(), maps[0].getZoom(), {animate: false});
  });
  draw(); fit();
})();
</script></body></html>'''
