/* Map of active requests (templates/requests/map.html).
   Markers and the accessible list come from the map-data JSON endpoint.
   All request data is written with textContent — never innerHTML. */
(function () {
  'use strict';

  const mapEl = document.getElementById('map');
  if (!mapEl) return;
  const listEl = document.getElementById('map-results');
  const statusEl = document.getElementById('map-status');
  const fallbackEl = document.getElementById('map-fallback');
  const categorySelect = document.getElementById('map-filter-category');
  const urgencySelect = document.getElementById('map-filter-urgency');
  const formatSelect = document.getElementById('map-filter-format');
  const formatWrap = document.getElementById('map-filter-format-wrap');

  const URGENCY_ICON = { low: 'bi-reception-1', medium: 'bi-reception-2', high: 'bi-reception-3', critical: 'bi-reception-4' };
  const FORMAT_ICON = { home_visit: 'bi-house-door', doorstep: 'bi-door-closed', public_place: 'bi-signpost-2', remote: 'bi-telephone' };
  const UKRAINE_BOUNDS = [[44.3, 22.1], [52.4, 40.2]];
  // map-data has only the category name; icons mirror the category fixture
  // (item.category_icon wins when the endpoint provides it)
  const CATEGORY_ICON = {
    'Продукти та харчування': 'bi-basket2', 'Медична допомога': 'bi-capsule',
    'Транспорт і пересування': 'bi-car-front', 'Прибирання та побут': 'bi-bucket',
    'Технічна допомога': 'bi-phone', 'Навчання та консультації': 'bi-mortarboard',
    'Тварини': 'paw', 'Інше': 'bi-three-dots'
  };
  const WEEKDAYS = ['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
  const MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня',
    'серпня', 'вересня', 'жовтня', 'листопада', 'грудня'];

  // ---- small DOM helpers -------------------------------------------------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function icon(name) {
    const i = el('i', 'bi ' + name);
    i.setAttribute('aria-hidden', 'true');
    return i;
  }
  function metaItem(iconName, text, className) {
    const li = el('li', className || '');
    li.appendChild(icon(iconName));
    li.appendChild(el('span', '', text));
    return li;
  }
  function urgencyItem(item) {
    const li = el('li');
    const span = el('span', 'mv-urg mv-urg--' + (URGENCY_ICON[item.urgency] ? item.urgency : 'medium'));
    span.appendChild(icon(URGENCY_ICON[item.urgency] || 'bi-reception-2'));
    span.appendChild(document.createTextNode('Терміновість: ' + String(item.urgency_display || '').toLowerCase()));
    li.appendChild(span);
    return li;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  // Same wording as the |when filter: 'Пт, 25 вересня, 19:57' (year only if not current)
  function when(value) {
    if (!value) return '';
    let d = null;
    const local = /^(\d{2})\.(\d{2})\.(\d{4})[ T](\d{2}):(\d{2})/.exec(value);
    if (local) d = new Date(+local[3], +local[2] - 1, +local[1], +local[4], +local[5]);
    else if (!isNaN(Date.parse(value))) d = new Date(value);
    if (!d) return String(value);
    const year = d.getFullYear() === new Date().getFullYear() ? '' : ' ' + d.getFullYear();
    return WEEKDAYS[d.getDay()] + ', ' + d.getDate() + ' ' + MONTHS[d.getMonth()] + year + ', ' +
      pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function pawSvg() {
    // Static shape (same as the category_icon tag), no request data inside
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    [[3.2, 6.3, 1.6, 2.1], [6.1, 3.4, 1.6, 2.2], [9.9, 3.4, 1.6, 2.2], [12.8, 6.3, 1.6, 2.1]].forEach(function (e) {
      const ellipse = document.createElementNS(ns, 'ellipse');
      ellipse.setAttribute('cx', e[0]); ellipse.setAttribute('cy', e[1]);
      ellipse.setAttribute('rx', e[2]); ellipse.setAttribute('ry', e[3]);
      svg.appendChild(ellipse);
    });
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', 'M8 7.2c-2.2 0-4.3 2.6-4.3 4.7 0 1.4 1 2.1 2.2 2.1.8 0 1.4-.4 2.1-.4s1.3.4 2.1.4c1.2 0 2.2-.7 2.2-2.1 0-2.1-2.1-4.7-4.3-4.7z');
    svg.appendChild(path);
    return svg;
  }
  function categoryTile(item) {
    const tile = el('span', 'mv-tile mv-tile--sm');
    tile.setAttribute('aria-hidden', 'true');
    let name = String(item.category_icon || CATEGORY_ICON[item.category] || 'bi-three-dots');
    if (name === 'paw') { tile.appendChild(pawSvg()); return tile; }
    if (!/^bi-[a-z0-9-]+$/.test(name)) name = /^[a-z0-9-]+$/.test(name) ? 'bi-' + name : 'bi-three-dots';
    tile.appendChild(icon(name));
    return tile;
  }
  function safeUrl(url) {
    return typeof url === 'string' && url.charAt(0) === '/' && url.charAt(1) !== '/' ? url : '#';
  }
  function setStatus(text) { if (statusEl) statusEl.textContent = text; }
  function plural(n, one, few, many) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (b === 1 && a !== 11) return one;
    if (b >= 2 && b <= 4 && (a < 12 || a > 14)) return few;
    return many;
  }

  // The same rows as the request card: when, format, city, urgency only if high
  function metaList(item) {
    const ul = el('ul', 'mv-meta');
    ul.appendChild(metaItem('bi-calendar-event', [when(item.needed_date), item.duration].filter(Boolean).join(' · ')));
    if (item.help_format_display) {
      ul.appendChild(metaItem(FORMAT_ICON[item.help_format] || 'bi-geo-alt', item.help_format_display));
    }
    if (item.help_format !== 'remote') {
      ul.appendChild(metaItem('bi-geo-alt', (item.city ? item.city + ' · ' : '') + 'адреса — після прийняття', 'is-hidden-value'));
    }
    if (item.urgency === 'high' || item.urgency === 'critical') ul.appendChild(urgencyItem(item));
    return ul;
  }

  // ---- map ---------------------------------------------------------------
  let map = null;
  let layer = null;
  if (window.L) {
    map = L.map(mapEl, { zoomControl: false, scrollWheelZoom: true });
    map.fitBounds(UKRAINE_BOUNDS);
    L.control.zoom({ position: 'topright', zoomInTitle: 'Наблизити', zoomOutTitle: 'Віддалити' }).addTo(map);
    // Tile source: data-tile-url / data-tile-attribution on #map override the default.
    // CARTO Voyager (https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png)
    // now watermarks tiles with "API key required", so the keyless default is OSM.
    const tileUrl = mapEl.getAttribute('data-tile-url') || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    L.tileLayer(tileUrl, {
      attribution: mapEl.getAttribute('data-tile-attribution') ||
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);
    layer = L.featureGroup().addTo(map);
  } else {
    mapEl.hidden = true;
    if (fallbackEl) fallbackEl.hidden = false;
  }

  const icons = {};
  function markerIcon(urgency) {
    const key = URGENCY_ICON[urgency] ? urgency : 'medium';
    if (!icons[key]) {
      // Static markup only: no request data goes into this HTML
      icons[key] = L.divIcon({
        className: 'bw-marker-wrap',
        html: '<span class="bw-marker bw-marker--' + key + '"><i class="bi ' + URGENCY_ICON[key] + '" aria-hidden="true"></i></span>',
        iconSize: [36, 44],
        iconAnchor: [18, 44],
        popupAnchor: [0, -40],
      });
    }
    return icons[key];
  }

  function popupContent(item) {
    const box = el('div', 'bw-popup');
    if (item.category) box.appendChild(el('p', 'bw-popup__cat', item.category));
    box.appendChild(el('p', 'bw-popup__title', item.title || 'Запит допомоги'));
    box.appendChild(metaList(item));
    const link = el('a', 'mv-btn mv-btn--primary mv-btn--sm mv-btn--block', 'Детальніше');
    link.href = safeUrl(item.url);
    link.appendChild(icon('bi-arrow-right'));
    box.appendChild(link);
    return box;
  }

  // ---- list --------------------------------------------------------------
  // A compact request card: category tile + title, then the meta rows
  function listRow(entry) {
    const item = entry.item;
    const li = el('li', 'mv-card mv-card--link bw-map-card');
    const head = el('div', 'bw-map-card__head');
    head.appendChild(categoryTile(item));
    const headText = el('div', 'bw-map-card__headtext');
    if (item.category) headText.appendChild(el('p', 'bw-map-card__cat', item.category));
    const title = el('h3', 'bw-map-card__title');
    const link = el('a', 'mv-stretched', item.title || 'Запит допомоги');
    link.href = safeUrl(item.url);
    title.appendChild(link);
    headText.appendChild(title);
    head.appendChild(headText);
    li.appendChild(head);
    li.appendChild(metaList(item));
    if (entry.marker) {
      const show = el('button', 'mv-link-btn mv-link-btn--sm bw-map-card__show');
      show.type = 'button';
      show.appendChild(icon('bi-geo'));
      show.appendChild(document.createTextNode('Показати на карті'));
      show.addEventListener('click', function () {
        map.setView(entry.base, Math.max(map.getZoom(), 14));
        entry.marker.openPopup();
        // On phones the map sits above the list: bring it into view
        if (window.matchMedia('(max-width: 991.98px)').matches) {
          const rect = mapEl.getBoundingClientRect();
          if (rect.top < 0 || rect.bottom > window.innerHeight) mapEl.scrollIntoView({ block: 'center' });
        }
      });
      li.appendChild(show);
    }
    return li;
  }

  // ---- markers on the same spot are fanned out around it ----------------
  // Deterministic (ordered by id) and recomputed on every zoom in screen
  // pixels, so pins that would overlap stay visible and clickable.
  const SPREAD_NEAR = 28; // px: closer than this counts as the same spot
  function spreadMarkers() {
    if (!map) return;
    const zoom = map.getZoom();
    const visible = entries.filter(function (e) { return e.marker && layer.hasLayer(e.marker); })
      .sort(function (a, b) { return (a.item.id || 0) - (b.item.id || 0); });
    const groups = [];
    visible.forEach(function (e) {
      const point = map.project(e.base, zoom);
      const group = groups.find(function (g) { return g.center.distanceTo(point) < SPREAD_NEAR; });
      if (group) group.members.push(e); else groups.push({ center: point, members: [e] });
    });
    groups.forEach(function (g) {
      const n = g.members.length;
      if (n === 1) { g.members[0].marker.setLatLng(g.members[0].base); return; }
      const radius = Math.max(24, (n * 36) / (2 * Math.PI));
      g.members.forEach(function (e, i) {
        const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
        const p = L.point(g.center.x + radius * Math.cos(angle), g.center.y + radius * Math.sin(angle));
        e.marker.setLatLng(map.unproject(p, zoom));
      });
    });
  }
  if (map) map.on('zoomend', spreadMarkers);

  // Zoom to the requests (with padding); the whole of Ukraine when there are none
  function fitToData() {
    if (!map) return;
    map.invalidateSize();
    const points = entries.filter(function (e) { return e.marker && layer.hasLayer(e.marker); })
      .map(function (e) { return e.base; });
    if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [56, 56], maxZoom: 13 });
    else map.fitBounds(UKRAINE_BOUNDS);
    spreadMarkers();
  }

  // ---- filters -----------------------------------------------------------
  let entries = [];
  function fillSelect(select, pairs) {
    pairs.forEach(function (pair) {
      const option = el('option', '', pair[1]);
      option.value = pair[0];
      select.appendChild(option);
    });
    select.disabled = false;
  }
  function uniquePairs(key, labelKey) {
    const seen = {};
    entries.forEach(function (e) {
      const value = e.item[key];
      if (value && !seen[value]) seen[value] = e.item[labelKey] || value;
    });
    return Object.keys(seen).map(function (k) { return [k, seen[k]]; })
      .sort(function (a, b) { return a[1].localeCompare(b[1], 'uk'); });
  }

  function applyFilters(fit) {
    const category = categorySelect ? categorySelect.value : '';
    const urgency = urgencySelect ? urgencySelect.value : '';
    const format = formatSelect ? formatSelect.value : '';
    let shown = 0;
    entries.forEach(function (e) {
      const visible = (!category || e.item.category === category) &&
        (!urgency || e.item.urgency === urgency) &&
        (!format || e.item.help_format === format);
      e.row.hidden = !visible;
      if (e.marker) {
        if (visible) layer.addLayer(e.marker); else layer.removeLayer(e.marker);
      }
      if (visible) shown += 1;
    });
    const total = entries.length;
    if (!total) setStatus('Зараз активних запитів на карті немає.');
    else if (shown === total) setStatus(total + ' ' + plural(total, 'запит', 'запити', 'запитів'));
    else setStatus('Показано ' + shown + ' з ' + total);
    if (fit) fitToData();
    else spreadMarkers();
  }

  [categorySelect, urgencySelect, formatSelect].forEach(function (select) {
    if (select) select.addEventListener('change', function () { applyFilters(true); });
  });

  // ---- load --------------------------------------------------------------
  fetch(mapEl.getAttribute('data-map-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(function (data) {
      entries = (Array.isArray(data) ? data : []).map(function (item) {
        const entry = { item: item, marker: null, row: null, base: null };
        if (map && item.lat !== null && item.lon !== null && isFinite(item.lat) && isFinite(item.lon)) {
          entry.base = L.latLng(Number(item.lat), Number(item.lon));
          entry.marker = L.marker(entry.base, {
            icon: markerIcon(item.urgency),
            title: item.title || '',
            alt: item.title || 'Запит допомоги',
            riseOnHover: true,
          }).bindPopup(popupContent(item), { maxWidth: 300, minWidth: 240 });
        }
        entry.row = listRow(entry);
        listEl.appendChild(entry.row);
        return entry;
      });
      if (categorySelect) fillSelect(categorySelect, uniquePairs('category', 'category'));
      if (urgencySelect) urgencySelect.disabled = false;
      if (formatSelect && formatWrap) {
        const formats = uniquePairs('help_format', 'help_format_display');
        if (formats.length) {
          fillSelect(formatSelect, formats);
          formatWrap.hidden = false;
        }
      }
      applyFilters(true);
    })
    .catch(function () {
      setStatus('Не вдалося завантажити запити. Оновіть сторінку або відкрийте список.');
    });
})();
