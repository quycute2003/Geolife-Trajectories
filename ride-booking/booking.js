const byId = id => document.getElementById(id);
const sheet = byId('sheet');
const sheetHandle = byId('sheet-handle');
const sheetContent = byId('sheet-content');
const title = byId('sheet-title');
const search = byId('place-search');
const profilePage = byId('profile-page');
const bookingStage = byId('booking-stage');
const openProfiles = byId('open-profiles');
const profileSearch = byId('profile-search');
const releaseDetails = byId('release-details');
const servingDetails = byId('serving-details');
const registryDetails = byId('registry-details');
const mapElement = byId('map');
const confirm = byId('confirm');
const back = byId('back');
const phone = window.matchMedia('(max-width: 759px)');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const mapKeyLabel = byId('map-key-label');
const map = createMap(mapElement, sheet, byId('map-canvas'), byId('map-pickup'), byId('map-destination'), status => {
  const label = {
    loading: 'Đang tải bản đồ…', ready: 'Bản đồ',
    partial: 'Bản đồ chưa tải đủ', error: 'Không tải được bản đồ',
  }[status];
  if (mapKeyLabel.textContent !== label) mapKeyLabel.textContent = label;
});
const placesById = new Map(places.map(place => [place.id, place]));
const defaultPickup = placesById.get('station');
const placeTemplate = byId('place-template');
const live = location.protocol === 'http:' || location.protocol === 'https:';
const gpsOrigin = { latitude: 39.9, longitude: 116.4 };

let users = live ? [] : profiles;
let profile;
let trip;
let page;
let editor;
let browseAddresses = false;
let draft;
let selectionTimer;
let expanded = false;
let handleGesture;
let isDraggingMap = false;
let suggestions = [];
let suggestionLoad;
let suggestionStatus = '';

function writePlace(nameId, addressId, place) {
  byId(nameId).textContent = place.name;
  const address = byId(addressId);
  address.textContent = place.address ?? '';
  address.hidden = !place.address;
}

function makeCard({ name, address, icon, selected, choose }) {
  const row = placeTemplate.content.firstElementChild.cloneNode(true);
  const button = row.querySelector('button');
  row.querySelector('.place-icon use').setAttribute('href', `#i-${icon}`);
  row.querySelector('.place-name').textContent = name;
  row.querySelector('.address').textContent = address ?? '';
  row.querySelector('.address').hidden = !address;
  if (selected !== undefined) button.setAttribute('aria-pressed', String(selected));
  if (selected) row.querySelector('.trailing use').setAttribute('href', '#i-check');
  button.addEventListener('click', () => choose(button));
  return row;
}

function setExpanded(value) {
  expanded = value;
  sheet.classList.toggle('is-expanded', expanded);
  sheetHandle.setAttribute('aria-expanded', String(expanded));
  sheetHandle.setAttribute('aria-label', expanded ? 'Thu gọn bảng đặt xe' : 'Mở rộng bảng đặt xe');
}

function foldForMap() {
  setExpanded(false);
  sheetContent.scrollTop = 0;
}

function normalize(text) {
  return text.toLocaleLowerCase('vi').normalize('NFD').replace(/\p{M}/gu, '').replaceAll('đ', 'd');
}

function gpsPlace(name, latitude, longitude) {
  return { name, latitude, longitude, address: `GPS ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
    ...projectGps(latitude, longitude) };
}

function gpsPlaceFromPin(name, point) {
  const { latitude, longitude } = unprojectGps(point);
  return gpsPlace(name, latitude, longitude);
}

function inferenceSuggestions(result) {
  const cards = [];
  const usedClusters = new Set();
  function add(place, name, icon) {
    if (!Number.isFinite(place?.latitude) || !Number.isFinite(place?.longitude)) return;
    usedClusters.add(place.cluster_id);
    cards.push({ ...gpsPlace(name, place.latitude, place.longitude), id: `${icon}-${place.cluster_id}`, icon });
  }
  if (result.home.status === 'predicted') add(result.home.candidate, 'Nhà', 'home');
  if (result.office.status === 'predicted') add(result.office.candidate, 'Công ty', 'office');
  let poiCount = 0;
  for (const place of result.pois) {
    if (usedClusters.has(place.cluster_id)) continue;
    const count = cards.length;
    add(place, `Nơi hay đến ${poiCount + 1}`, 'poi');
    if (cards.length > count) poiCount += 1;
    if (poiCount === 2) break;
  }
  return cards;
}

async function getJson(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function showServing(result, source) {
  trip.inference = result;
  trip.serving = source;
  const track = { 'heuristic-v1': 'Blue', 'dbscan-v1': 'Green' }[result.model_version];
  const runtime = source === 'knative' ? ['Kourier / Knative', track].filter(Boolean).join(' · ') : 'API local';
  servingDetails.textContent = `${runtime} · ${result.model_version} · ${result.data_snapshot_id}`;
  releaseDetails.hidden = page === 'edit' || page === 'map';
}

releaseDetails.addEventListener('toggle', async () => {
  if (!releaseDetails.open || !trip?.inference || trip.registryRequested) return;
  const selectedTrip = trip;
  const inference = selectedTrip.inference;
  selectedTrip.registryRequested = true;
  registryDetails.textContent = 'Đang tra phiên bản trong MLflow…';
  try {
    const query = new URLSearchParams({ algorithm: inference.model_version });
    const registry = await getJson(`/booking/registry?${query}`);
    if (trip !== selectedTrip) return;
    const matched = registry.status === 'READY' && registry.algorithm === inference.model_version &&
      registry.snapshot === inference.data_snapshot_id && registry.pipeline_version === inference.pipeline_version &&
      registry.config_sha256 === inference.config_sha256;
    const version = `MLflow v${registry.version}`;
    registryDetails.textContent = matched ? `${version} · Khớp metadata suy luận.` :
      `${version} · Snapshot đăng ký ${registry.snapshot ?? 'chưa rõ'}. Metadata khác kết quả đang phục vụ.`;
  } catch {
    if (trip !== selectedTrip) return;
    selectedTrip.registryRequested = false;
    registryDetails.textContent = 'Chưa đọc được phiên bản từ MLflow.';
  }
});

function showMap() {
  const onMap = page === 'map';
  map.show({ pickup: trip.pickup, destination: trip.destination, draft: onMap ? draft : null,
    editing: onMap ? editor.field : null, gps: live,
    waitingForGps: live && !trip.gpsSettled && !onMap && !trip.pickupEdited && !trip.destination });
}

async function loadSuggestions() {
  const request = new AbortController();
  suggestionLoad = request;
  suggestionStatus = 'Đang tải gợi ý…';
  renderSearch();
  try {
    const response = await fetch('/v2/locations/infer', { method: 'POST', signal: request.signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: profile.id }) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (request !== suggestionLoad || trip.destination || page === 'map') return;
    suggestions = inferenceSuggestions(result);
    showServing(result, response.headers.get('X-GeoLife-Serving'));
    suggestionStatus = suggestions.length ? '' : 'Chưa có gợi ý cho người dùng này.';
    const anchor = suggestions[0] ?? result.locations[0];
    if (anchor && !trip.pickupEdited) {
      const point = gpsPlace('Điểm đón mô phỏng', anchor.latitude + 0.0022, anchor.longitude - 0.0028);
      trip.pickup = point;
    }
  } catch {
    if (request !== suggestionLoad || trip.destination || page === 'map') return;
    suggestionStatus = 'Chưa tải được gợi ý. Bạn vẫn có thể chọn trên bản đồ.';
  } finally {
    if (request === suggestionLoad) {
      if (suggestionStatus.startsWith('Đang')) suggestionStatus = '';
      suggestionLoad = null;
      trip.gpsSettled = true;
      if (page === 'choose' || page === 'edit') {
        renderSearch();
        showMap();
      }
    }
  }
}

function setPlace(field, place, fromSuggestion = false) {
  if (field === 'destination') {
    trip.destinationSource = fromSuggestion ? 'suggestion' : (trip.destination ? 'edited' : 'manual');
  } else {
    trip.pickupEdited = true;
  }
  trip[field] = place;
}

function choosePlace(place, fromSuggestion = false) {
  setPlace(page === 'edit' ? editor.field : 'destination', place, fromSuggestion);
  showPage(trip.destination ? 'review' : 'choose');
}

function chooseSuggestion(place, button) {
  clearTimeout(selectionTimer);
  for (const card of byId('suggestion-list').querySelectorAll('button')) {
    const selected = card === button;
    card.setAttribute('aria-pressed', String(selected));
    card.querySelector('.trailing use').setAttribute('href', selected ? '#i-check' : '#i-chevron');
    card.classList.toggle('is-selecting', selected);
  }
  if (reducedMotion.matches) choosePlace(place, true);
  else selectionTimer = setTimeout(() => choosePlace(place, true), 160);
}

function renderSearch() {
  const query = normalize(search.value.trim()).split(/\s+/).filter(Boolean);
  const pickingUp = page === 'edit' && editor.field === 'pickup';
  const showAddresses = !live && (pickingUp || browseAddresses || query.length > 0);
  const matches = place => {
    const text = normalize(`${place.name} ${place.address ?? ''}`);
    return query.every(word => text.includes(word));
  };
  const visible = !pickingUp && (live || query.length === 0) ? suggestions.filter(matches) : [];
  byId('suggestions').hidden = !visible.length;
  byId('search-results').hidden = !showAddresses;
  byId('search-view').classList.toggle('is-browsing', showAddresses);
  const status = byId('suggestion-status');
  status.textContent = suggestionStatus || (live && query.length && !visible.length ? 'Không tìm thấy gợi ý phù hợp.' : '');
  status.hidden = !status.textContent;

  byId('suggestion-list').replaceChildren(...visible.map(place => makeCard({ ...place,
    selected: trip.destinationSource === 'suggestion' && trip.destination?.id === place.id,
    choose: button => chooseSuggestion(place, button),
  })));

  if (showAddresses) {
    const filtered = places.filter(matches);
    byId('result-list').replaceChildren(...filtered.map(place => makeCard({ ...place, icon: 'pin', choose: () => choosePlace(place) })));
    byId('no-results').hidden = filtered.length > 0;
  }
}

function showPage(nextPage, focus = true) {
  clearTimeout(selectionTimer);
  page = nextPage;
  const choosing = page === 'choose';
  const editing = page === 'edit';
  const onMap = page === 'map';
  const reviewing = page === 'review';
  const confirmed = page === 'success';
  releaseDetails.hidden = !trip.inference || onMap || editing;
  const pickupEdit = (editing || onMap) && editor.field === 'pickup';
  const label = pickupEdit ? 'điểm đón' : 'điểm đến';

  byId('choose-view').hidden = !choosing;
  byId('search-view').hidden = !(choosing || editing);
  byId('review-view').hidden = !reviewing;
  byId('map-view').hidden = !onMap;
  byId('success-view').hidden = !confirmed;
  byId('sheet-footer').hidden = !(onMap || reviewing || confirmed);
  back.hidden = choosing || confirmed;
  if (choosing) title.textContent = 'Bạn muốn đi đâu?';
  if (editing) title.textContent = `Sửa ${label}`;
  if (onMap) title.textContent = `Đặt ghim ${label}`;
  if (reviewing) title.textContent = 'Xem lại chuyến đi';
  if (confirmed) title.textContent = 'Đã đặt chuyến mô phỏng';
  if (onMap) confirm.textContent = `Dùng ${label} này`;
  if (reviewing) confirm.textContent = 'Xác nhận chuyến mô phỏng';
  if (confirmed) confirm.textContent = 'Đặt chuyến mới';

  byId('current-pickup').textContent = trip.pickup.name;
  if (reviewing) {
    writePlace('review-pickup-name', 'review-pickup-address', trip.pickup);
    writePlace('review-destination-name', 'review-destination-address', trip.destination);
  }
  if (confirmed) byId('success-destination').textContent = trip.destination.name;

  search.value = '';
  browseAddresses = false;
  if (choosing || editing) renderSearch();
  foldForMap();
  sheet.classList.toggle('is-compact', onMap);
  sheetHandle.hidden = onMap;
  mapElement.classList.toggle('is-editing', onMap);
  if (onMap) {
    mapElement.tabIndex = 0;
    mapElement.setAttribute('aria-describedby', 'map-view');
  } else {
    mapElement.removeAttribute('tabindex');
    mapElement.removeAttribute('aria-describedby');
  }
  showMap();
  if (focus) (onMap ? mapElement : title).focus({ preventScroll: true });
}

function edit(field) {
  editor = { field, from: page };
  if (live && field === 'pickup') openMap(field);
  else showPage('edit');
}

function openMap(field = 'destination') {
  if (page !== 'edit') editor = { field, from: page };
  editor.mapFrom = page;
  const initial = trip[editor.field] ?? trip.pickup;
  draft = { x: initial.x, y: initial.y };
  if (!trip[editor.field]) draft = map.nudge(draft, 66, -42);
  showPage('map');
}

function moveDraft(point) {
  draft = point;
  map.moveDraft(draft);
}

function startTrip() {
  suggestionLoad?.abort();
  releaseDetails.hidden = true;
  releaseDetails.open = false;
  registryDetails.textContent = '';
  suggestionStatus = '';
  suggestions = live ? [] : profile.suggestions.map(({ placeId, name, icon }) => ({ ...placesById.get(placeId), name, icon }));
  trip = { is_fixture: !live, pickup: live ? gpsPlace('Điểm đón mô phỏng', gpsOrigin.latitude, gpsOrigin.longitude) : defaultPickup,
    destination: null, destinationSource: null };
  showPage('choose');
  if (live) void loadSuggestions();
}

function setProfileStatus(message, retry = false) {
  const status = byId('profile-status');
  status.textContent = message;
  status.hidden = !message;
  byId('reload-profiles').hidden = !retry;
}

function renderProfiles() {
  const query = profileSearch.value.trim();
  const options = users.filter(user => user.id.includes(query));
  byId('profile-list').replaceChildren(...options.map(option => makeCard({ ...option, icon: 'user',
    choose: () => {
      profile = option;
      showBooking();
      startTrip();
    },
  })));
  if (users.length) setProfileStatus(options.length ? '' : 'Không tìm thấy mã người dùng này.');
}

async function loadProfiles() {
  setProfileStatus('Đang tải danh sách người dùng…');
  try {
    const result = await getJson('/booking/users');
    users = result.user_ids.map(id => ({ id, name: `Người dùng ${id}` }));
    byId('profile-filter').hidden = !users.length;
    renderProfiles();
    if (!users.length) setProfileStatus('Chưa có người dùng để chọn.');
  } catch {
    setProfileStatus('Không tải được danh sách người dùng.', true);
  }
}

function showBooking() {
  profilePage.hidden = true;
  bookingStage.hidden = false;
  openProfiles.hidden = false;
  byId('active-profile').textContent = profile.name;
  openProfiles.setAttribute('aria-label', `${profile.name}. Đổi người dùng`);
}

openProfiles.addEventListener('click', () => {
  clearTimeout(selectionTimer);
  profileSearch.value = '';
  renderProfiles();
  bookingStage.hidden = true;
  profilePage.hidden = false;
  openProfiles.hidden = true;
  byId('return-booking').hidden = false;
  byId('profiles-title').focus();
});
byId('return-booking').addEventListener('click', () => {
  showBooking();
  map.resize();
  openProfiles.focus();
});
byId('reload-profiles').addEventListener('click', loadProfiles);
profileSearch.addEventListener('input', renderProfiles);
byId('edit-pickup').addEventListener('click', () => edit('pickup'));
byId('review-pickup').addEventListener('click', () => edit('pickup'));
byId('review-destination').addEventListener('click', () => edit('destination'));
byId('choose-map').addEventListener('click', () => openMap());
byId('zoom-in').addEventListener('click', () => map.zoom(1.25));
byId('zoom-out').addEventListener('click', () => map.zoom(.8));
byId('center-map').addEventListener('click', () => map.center());
search.addEventListener('focus', () => {
  clearTimeout(selectionTimer);
  browseAddresses = true;
  renderSearch();
});
search.addEventListener('input', renderSearch);
search.addEventListener('keydown', event => {
  const section = live ? 'suggestions' : 'search-results';
  if (event.key === 'Enter' && !byId(section).hidden) byId(section).querySelector('button')?.click();
});

back.addEventListener('click', () => {
  if (page === 'map') showPage(editor.mapFrom);
  else if (page === 'edit') showPage(editor.from);
  else showPage('choose');
});

confirm.addEventListener('click', () => {
  if (page === 'map') {
    const name = editor.field === 'pickup' ? 'Điểm đón mô phỏng' : 'Điểm đến đã ghim';
    const previous = trip[editor.field];
    const samePoint = previous && previous.x === draft.x && previous.y === draft.y;
    const place = live ? gpsPlaceFromPin(name, draft) : { ...draft, name };
    setPlace(editor.field, samePoint ? previous : place);
    showPage(trip.destination ? 'review' : 'choose');
  } else if (page === 'review') {
    showPage('success');
  } else {
    startTrip();
  }
});

sheetHandle.addEventListener('click', event => {
  if (event.detail === 0) setExpanded(!expanded);
});
sheetHandle.addEventListener('pointerdown', event => {
  if (!event.isPrimary || event.button !== 0) return;
  handleGesture = { id: event.pointerId, x: event.clientX, y: event.clientY };
  sheetHandle.setPointerCapture(event.pointerId);
});
sheetHandle.addEventListener('pointerup', event => {
  if (handleGesture?.id !== event.pointerId) return;
  const distance = event.clientY - handleGesture.y;
  if (Math.abs(distance) > 18) setExpanded(distance < 0);
  else if (Math.abs(event.clientX - handleGesture.x) < 18) setExpanded(!expanded);
});
sheetHandle.addEventListener('lostpointercapture', () => {
  handleGesture = null;
});
new ResizeObserver(() => {
  if (phone.matches) map.resize(true);
}).observe(sheet);

mapElement.addEventListener('pointerdown', event => {
  if (page !== 'map' || event.button !== 0) return;
  isDraggingMap = true;
  mapElement.setPointerCapture(event.pointerId);
  moveDraft(map.pointAt(event.clientX, event.clientY));
});
mapElement.addEventListener('pointermove', event => {
  if (isDraggingMap) moveDraft(map.pointAt(event.clientX, event.clientY));
});
mapElement.addEventListener('lostpointercapture', () => { isDraggingMap = false; });
mapElement.addEventListener('keydown', event => {
  const directions = { ArrowLeft: [-12, 0], ArrowRight: [12, 0], ArrowUp: [0, -12], ArrowDown: [0, 12] };
  const direction = directions[event.key];
  if (page !== 'map' || !direction) return;
  event.preventDefault();
  moveDraft(map.nudge(draft, ...direction));
});

if (live) {
  mapKeyLabel.textContent = 'Đang tải bản đồ…';
  byId('map-attribution').hidden = false;
  search.placeholder = 'Tìm trong gợi ý';
  search.setAttribute('aria-label', search.placeholder);
  void loadProfiles();
} else {
  byId('profiles-title').textContent = 'Chọn người dùng mẫu';
  renderProfiles();
}
