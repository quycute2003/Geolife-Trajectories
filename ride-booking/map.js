const WORLD = { width: 1120, height: 880 };
const westRoads = [30, 88, 141, 201, 263, 323, 386, 448, 511];
const eastRoads = [659, 711, 763, 822, 882, 947, 1005, 1067];
const crossRoads = [30, 87, 152, 212, 267, 329, 386, 442, 502, 560, 628, 696, 759, 825];
const river = new Path2D('M 739 -30 C 699 63 691 129 650 200 C 612 263 583 291 589 366 C 597 453 628 497 602 569 C 586 621 527 655 516 721 C 505 782 537 837 562 910 L 697 910 C 646 814 616 780 621 734 C 628 678 686 632 704 575 C 734 485 688 437 689 360 C 682 306 708 277 747 218 C 784 151 797 61 857 -30 Z');
const parks = [
  { area: [318, 199, 525, 351], path: 'M333 206 Q413 208 465 199 L507 244 524 312 483 345 354 349 319 305Z', type: 'park' },
  { area: [255, 507, 413, 621], path: 'M290 509 L407 527 412 586 357 621 254 601 260 549Z', type: 'park' },
  { area: [724, 277, 873, 380], path: 'M755 281 L846 277 873 317 852 376 755 383 724 346Z', type: 'park' },
  { area: [792, 513, 904, 613], path: 'M807 513 L880 522 905 570 876 614 793 604 792 559Z', type: 'field' },
  { area: [427, 633, 509, 745], path: 'M460 633 L506 654 497 724 455 745 426 706Z', type: 'park' },
  { area: [108, 339, 198, 418], path: 'M115 341 L185 348 198 400 181 418 108 409Z', type: 'field' },
  { area: [933, 105, 1040, 195], path: 'M938 108 L1016 105 1041 152 1014 195 930 183Z', type: 'park' },
];

function roadX(x, y, east) {
  return x + (east ? -.13 : .12) * (y - 390) + 8 * Math.sin((y + x * .24) / 99);
}

function roadY(y, x, east) {
  return y + (east ? .11 : -.09) * (x - (east ? 810 : 330)) + 7 * Math.sin(x / 90 + y / 113);
}

function drawBaseMap() {
  const base = document.createElement('canvas');
  base.width = WORLD.width * 2;
  base.height = WORLD.height * 2;
  const ctx = base.getContext('2d');
  ctx.scale(2, 2);
  ctx.fillStyle = '#e9eeeb';
  ctx.fillRect(0, 0, WORLD.width, WORLD.height);

  let seed = 119;
  const random = () => {
    seed = (Math.imul(1664525, seed) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const buildings = ['#dce5e0', '#dfe7e2', '#e2e9e5', '#d7e2dd'];
  for (let y = 12; y < WORLD.height; y += 21) {
    for (let x = 9; x < WORLD.width; x += 19) {
      if (random() > .76) continue;
      ctx.save();
      ctx.translate(x + random() * 6, y + random() * 7);
      ctx.rotate(x < 600 ? -.13 : .14);
      ctx.fillStyle = buildings[Math.floor(random() * buildings.length)];
      ctx.fillRect(0, 0, 7 + random() * 10, 6 + random() * 12);
      ctx.restore();
    }
  }

  for (const { area, path, type } of parks) {
    const [left, top, right, bottom] = area;
    const shape = new Path2D(path);
    ctx.fillStyle = type === 'field' ? '#dbe7d1' : '#d5e7d9';
    ctx.fill(shape);
    ctx.save();
    ctx.clip(shape);
    ctx.beginPath();
    ctx.moveTo(left, bottom - 15);
    ctx.quadraticCurveTo((left + right) / 2 + 22, top + 25, right, top + 23);
    ctx.strokeStyle = '#eaf1e6';
    ctx.lineWidth = 4;
    ctx.stroke();
    ctx.fillStyle = '#bbd5c2';
    for (let y = top + 8; y < bottom; y += 15) {
      for (let x = left + 8; x < right; x += 16) {
        if (random() > .47) continue;
        ctx.beginPath();
        ctx.arc(x + random() * 6, y + random() * 7, 1.4 + random() * 2.1, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawRoad(path, width, fill = '#fafcfb') {
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#d4e0d9';
    ctx.lineWidth = width + 2;
    ctx.stroke(path);
    ctx.strokeStyle = fill;
    ctx.lineWidth = width;
    ctx.stroke(path);
  }

  for (const east of [false, true]) {
    const columns = east ? eastRoads : westRoads;
    for (const x of columns) {
      const path = new Path2D();
      path.moveTo(roadX(x, -20, east), -20);
      for (let y = 0; y <= 900; y += 35) path.lineTo(roadX(x, y, east), y);
      drawRoad(path, [201, 448, 763, 947].includes(x) ? 11 : 6);
    }
    for (const y of crossRoads) {
      const firstX = east ? 617 : -35;
      const endX = east ? 1160 : 660;
      const path = new Path2D();
      path.moveTo(firstX, roadY(y, firstX, east));
      for (let x = firstX; x <= endX; x += 20) path.lineTo(x, roadY(y, x, east));
      drawRoad(path, [152, 442, 696].includes(y) ? 11 : 6);
    }
  }

  const avenues = [
    'M -20 592 Q 156 516 258 449 T 520 358 Q 566 362 609 378',
    'M -10 750 Q 197 652 355 701 T 616 741',
    'M 691 337 Q 809 466 1117 419',
    'M 615 691 Q 808 666 1130 565',
  ];
  for (const path of avenues) drawRoad(new Path2D(path), 15, '#fffdf4');

  ctx.fillStyle = '#c0dee0';
  ctx.fill(river);
  ctx.save();
  ctx.clip(river);
  ctx.strokeStyle = '#d0e9e9';
  ctx.lineWidth = 2;
  for (let y = 8; y < WORLD.height; y += 27) {
    const x = 510 + random() * 300;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.quadraticCurveTo(x + 13, y - 3, x + 29, y);
    ctx.stroke();
  }
  ctx.restore();
  ctx.strokeStyle = '#afcfd1';
  ctx.lineWidth = 2;
  ctx.stroke(river);

  for (const path of [
    'M 549 181 Q 638 176 787 157',
    'M 547 364 Q 626 367 701 404 T 787 435',
    'M 490 687 Q 590 669 705 678 T 810 650',
  ]) drawRoad(new Path2D(path), 12, '#fffdf4');

  return base;
}

const labels = [
  { text: 'KHU VƯỜN XANH', x: 428, y: 290, district: true },
  { text: 'KHU BỜ TÂY', x: 230, y: 380, district: true },
  { text: 'KHU BỜ ĐÔNG', x: 840, y: 490, district: true },
  { text: 'Đường Gió Mát', x: 343, y: 433, angle: -.12 },
  { text: 'Đại lộ Ngọc Lan', x: 456, y: 369, angle: -.18 },
  { text: 'Cầu Ánh Dương', x: 633, y: 371, angle: .25 },
  { text: 'Sông Ngọc', x: 643, y: 489, angle: 1.24, river: true },
  { text: 'Quảng trường Nắng', x: 338, y: 574 },
  { text: 'Công viên Ven Sông', x: 802, y: 331 },
  { text: 'Đường Hướng Dương', x: 945, y: 406, angle: -.07 },
  { text: 'Cầu Sóng Xanh', x: 563, y: 659, angle: -.09 },
  { text: 'Đường Phượng Vĩ', x: 268, y: 157, angle: -.09 },
  { text: 'KHU BÌNH MINH', x: 492, y: 773, district: true },
];

const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
const interpolate = (start, end, progress) => start + (end - start) * progress;
const EARTH_RADIUS = 6378137;
const MERCATOR_WIDTH = 2 * Math.PI * EARTH_RADIUS;
const MAX_MERCATOR_LATITUDE = Math.atan(Math.sinh(Math.PI)) * 180 / Math.PI;
const TILE_SIZE = 256;
const TILE_CACHE_LIMIT = 128;

function projectGps(latitude, longitude) {
  const radians = clamp(latitude, -MAX_MERCATOR_LATITUDE, MAX_MERCATOR_LATITUDE) * Math.PI / 180;
  return {
    x: (longitude + 180) / 360 * MERCATOR_WIDTH,
    y: MERCATOR_WIDTH / 2 - EARTH_RADIUS * Math.asinh(Math.tan(radians)),
  };
}

function unprojectGps({ x, y }) {
  const boundedY = clamp(y, 0, MERCATOR_WIDTH);
  return {
    latitude: Math.atan(Math.sinh((MERCATOR_WIDTH / 2 - boundedY) / EARTH_RADIUS)) * 180 / Math.PI,
    longitude: ((x / MERCATOR_WIDTH % 1) + 1) % 1 * 360 - 180,
  };
}

function createMap(element, sheet, canvas, pickupMarker, destinationMarker, onTileStatus) {
  const ctx = canvas.getContext('2d');
  const base = drawBaseMap();
  const desktop = window.matchMedia('(min-width: 760px)');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let size;
  let camera;
  let zoom = 1;
  let frame = 0;
  let tileRefresh = 0;
  let points = {};
  let activeTiles = [];
  const tileCache = new Map();

  function visibleArea() {
    const bounds = element.getBoundingClientRect();
    const panel = sheet.getBoundingClientRect();
    return desktop.matches
      ? { left: panel.right - bounds.left + 18, right: bounds.width - 24, top: 54, bottom: bounds.height - 38 }
      : { left: 32, right: bounds.width - 40, top: 61, bottom: Math.max(79, panel.top - bounds.top - 22) };
  }

  function fit() {
    const area = visibleArea();
    const width = Math.max(80, area.right - area.left);
    const height = Math.max(24, area.bottom - area.top);
    const locations = [points.pickup, points.destination, points.draft].filter(Boolean);
    const minX = Math.min(...locations.map(point => point.x));
    const maxX = Math.max(...locations.map(point => point.x));
    const minY = Math.min(...locations.map(point => point.y));
    const maxY = Math.max(...locations.map(point => point.y));
    const isSingle = minX === maxX && minY === maxY;
    const scale = Math.max(points.gps ? .00001 : .23,
      Math.min(desktop.matches ? 1.65 : 1.15, width / (maxX - minX + 125), height / (maxY - minY + 135)) * zoom);
    return {
      scale,
      x: (area.left + area.right) / 2 - ((minX + maxX) / 2 + (isSingle ? 54 : 0)) * scale,
      y: (area.top + area.bottom) / 2 - ((minY + maxY) / 2 - 29) * scale,
    };
  }

  function project(point) {
    return { x: point.x * camera.scale + camera.x, y: point.y * camera.scale + camera.y };
  }

  function positionMarker(marker, point) {
    marker.hidden = !point;
    if (!point) return;
    const position = project(point);
    marker.style.left = `${position.x}px`;
    marker.style.top = `${position.y}px`;
  }

  function paintMapTiles(width, height) {
    const tileWidth = WORLD.width * camera.scale;
    const tileHeight = WORLD.height * camera.scale;
    const firstRow = Math.floor(-camera.y / tileHeight);
    const firstColumn = Math.floor(-camera.x / tileWidth);
    for (let row = firstRow; camera.y + row * tileHeight < height; row += 1) {
      for (let column = firstColumn; camera.x + column * tileWidth < width; column += 1) {
        const flipX = column % 2 !== 0;
        const flipY = row % 2 !== 0;
        ctx.save();
        ctx.translate(camera.x + (column + Number(flipX)) * tileWidth,
          camera.y + (row + Number(flipY)) * tileHeight);
        ctx.scale(flipX ? -1 : 1, flipY ? -1 : 1);
        ctx.drawImage(base, 0, 0, tileWidth, tileHeight);
        ctx.restore();
      }
    }
  }

  function paintIllustration(width, height) {
    paintMapTiles(width, height);
    for (const label of labels) {
      const point = project(label);
      const fontSize = label.district ? 11 : 10;
      ctx.save();
      ctx.translate(point.x, point.y);
      ctx.rotate(label.angle || 0);
      ctx.font = `600 ${fontSize}px 'Be Vietnam Pro', system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.letterSpacing = label.district ? '1.1px' : '0px';
      ctx.lineWidth = 3;
      ctx.lineJoin = 'round';
      ctx.strokeStyle = '#f2f8f3';
      ctx.fillStyle = label.river ? '#376e73' : '#506b60';
      ctx.strokeText(label.text, 0, 0);
      ctx.fillText(label.text, 0, 0);
      ctx.restore();
    }
  }

  function groundScale() {
    const center = unprojectGps({ x: 0, y: (size.height / 2 - camera.y) / camera.scale });
    return camera.scale / Math.cos(center.latitude * Math.PI / 180);
  }

  function paintGpsGrid(width, height, step) {
    ctx.beginPath();
    for (let x = camera.x % step; x < width; x += step) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
    }
    for (let y = camera.y % step; y < height; y += step) {
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
    }
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#d3e2da';
    ctx.stroke();
  }

  function paintGpsTiles() {
    for (const { tile, x, y, extent } of activeTiles) {
      if (tile.status !== 'ready') continue;
      const at = project({ x, y });
      const pixels = extent * camera.scale;
      const left = Math.round(at.x);
      const top = Math.round(at.y);
      ctx.drawImage(tile.image, left, top, Math.round(at.x + pixels) - left, Math.round(at.y + pixels) - top);
    }
  }

  function reportTiles() {
    if (points.waitingForGps) return;
    if (activeTiles.some(({ tile }) => tile.status === 'loading')) onTileStatus('loading');
    else if (activeTiles.every(({ tile }) => tile.status === 'ready') && activeTiles.length) onTileStatus('ready');
    else if (activeTiles.some(({ tile }) => tile.status === 'ready')) onTileStatus('partial');
    else onTileStatus('error');
  }

  function getTile(z, column, row) {
    const key = `${z}/${column}/${row}`;
    const cached = tileCache.get(key);
    if (cached) {
      tileCache.delete(key);
      tileCache.set(key, cached);
      return cached;
    }
    const image = new Image();
    const tile = { image, status: 'loading' };
    function finish(status) {
      clearTimeout(timeout);
      tile.status = status;
      if (activeTiles.some(entry => entry.tile === tile)) {
        reportTiles();
        paint();
      }
    }
    image.addEventListener('load', () => finish('ready'), { once: true });
    image.addEventListener('error', () => finish('error'), { once: true });
    const timeout = setTimeout(() => finish('error'), 8000);
    image.src = `https://tile.openstreetmap.org/${key}.png`;
    tileCache.set(key, tile);
    if (tileCache.size > TILE_CACHE_LIMIT) tileCache.delete(tileCache.keys().next().value);
    return tile;
  }

  function refreshGpsTiles() {
    if (!points.gps || points.waitingForGps || !element.clientWidth) return;
    const z = clamp(Math.round(Math.log2(camera.scale * MERCATOR_WIDTH / TILE_SIZE)), 0, 19);
    const count = 2 ** z;
    const extent = MERCATOR_WIDTH / count;
    const pixels = extent * camera.scale;
    const firstColumn = Math.floor(-camera.x / pixels);
    const lastColumn = Math.ceil((size.width - camera.x) / pixels);
    const firstRow = Math.max(0, Math.floor(-camera.y / pixels));
    const lastRow = Math.min(count, Math.ceil((size.height - camera.y) / pixels));
    const visible = [];
    for (let row = firstRow; row < lastRow; row += 1) {
      for (let column = firstColumn; column < lastColumn; column += 1) {
        const tile = getTile(z, ((column % count) + count) % count, row);
        visible.push({ tile, x: column * extent, y: row * extent, extent });
      }
    }
    activeTiles = visible;
    reportTiles();
    paint();
  }

  function scheduleTiles() {
    clearTimeout(tileRefresh);
    if (points.gps && !points.waitingForGps) tileRefresh = setTimeout(refreshGpsTiles, 100);
  }

  function paintScale(width, stepMeters, step) {
    const region = visibleArea();
    const x = region.left + 8;
    const y = region.bottom;
    if (y < 106 || x + step > width - 18) return;
    const label = stepMeters >= 1000 ? `${stepMeters / 1000} km` : `${stepMeters} m`;
    ctx.font = '600 11px system-ui, sans-serif';
    ctx.fillStyle = '#fffffff2';
    ctx.fillRect(x - 6, y - 22, Math.max(step, 68) + 12, 28);
    ctx.fillStyle = '#46615b';
    ctx.fillText(`≈ ${label}`, x, y - 7);
    ctx.fillRect(x, y, step, 2);
  }

  function paint() {
    if (!size) return;
    const { width, height, ratio } = size;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = points.gps ? '#edf5f0' : '#e9eeeb';
    ctx.fillRect(0, 0, width, height);
    if (points.gps) {
      const meterScale = groundScale();
      const stepMeters = 25 * 2 ** Math.ceil(Math.log2(60 / (25 * meterScale)));
      const step = stepMeters * meterScale;
      paintGpsGrid(width, height, step);
      if (!points.waitingForGps) paintGpsTiles();
      paintScale(width, stepMeters, step);
    } else paintIllustration(width, height);
    const pickup = points.editing === 'pickup' ? points.draft : points.pickup;
    const destination = points.editing === 'destination' ? points.draft : points.destination;
    if (pickup && destination) {
      const start = project(pickup);
      const end = project(destination);
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(end.x, end.y);
      ctx.lineCap = 'round';
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 6;
      ctx.stroke();
      ctx.strokeStyle = '#0f766e';
      ctx.lineWidth = 3;
      ctx.setLineDash([3, 7]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    positionMarker(pickupMarker, pickup);
    positionMarker(destinationMarker, destination);
  }

  function reframe(animate = false) {
    cancelAnimationFrame(frame);
    clearTimeout(tileRefresh);
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (!width || !height || !points.pickup) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    if (!size || size.width !== width || size.height !== height || size.ratio !== ratio) {
      size = { width, height, ratio };
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      animate = false;
    }
    const target = fit();
    if (!camera || !animate || reducedMotion.matches) {
      camera = target;
      paint();
      scheduleTiles();
      return;
    }
    const start = camera;
    const startedAt = performance.now();
    function move(now) {
      const time = Math.min((now - startedAt) / 280, 1);
      const progress = 1 - (1 - time) ** 3;
      camera = {
        x: interpolate(start.x, target.x, progress),
        y: interpolate(start.y, target.y, progress),
        scale: interpolate(start.scale, target.scale, progress),
      };
      paint();
      if (time < 1) frame = requestAnimationFrame(move);
      else scheduleTiles();
    }
    frame = requestAnimationFrame(move);
  }

  new ResizeObserver(() => {
    const boundsChanged = size?.width !== element.clientWidth || size?.height !== element.clientHeight;
    reframe(!boundsChanged);
  }).observe(element);

  return {
    show(nextPoints) {
      const previousDestination = points.destination;
      points = nextPoints;
      if (points.waitingForGps) onTileStatus('loading');
      zoom = 1;
      reframe(true);
      if (points.destination && points.destination !== previousDestination) {
        destinationMarker.classList.remove('is-dropping');
        void destinationMarker.offsetWidth;
        destinationMarker.classList.add('is-dropping');
      }
    },
    resize: reframe,
    zoom(factor) {
      zoom = clamp(zoom * factor, .55, 2.5);
      reframe(true);
    },
    center() {
      for (const [key, tile] of tileCache) {
        if (tile.status === 'error') tileCache.delete(key);
      }
      zoom = 1;
      reframe(true);
    },
    moveDraft(point) {
      points.draft = point;
      paint();
    },
    pointAt(clientX, clientY) {
      const bounds = element.getBoundingClientRect();
      return {
        x: (clientX - bounds.left - camera.x) / camera.scale,
        y: (clientY - bounds.top - camera.y) / camera.scale,
      };
    },
    nudge(origin, x, y) {
      return {
        x: origin.x + x / camera.scale,
        y: origin.y + y / camera.scale,
      };
    },
  };
}
