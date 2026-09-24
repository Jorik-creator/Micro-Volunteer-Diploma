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
  const UKRAINE = [48.6, 31.2];

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

  function metaList(item, inline) {
    const ul = el('ul', 'mv-meta' + (inline ? ' mv-meta--inline' : ''));
    ul.appendChild(urgencyItem(item));
    ul.appendChild(metaItem('bi-calendar-event', [item.needed_date, item.duration].filter(Boolean).join(' · ')));
    if (item.help_format_display) {
      ul.appendChild(metaItem(FORMAT_ICON[item.help_format] || 'bi-geo-alt', item.help_format_display));
    }
    if (item.city) ul.appendChild(metaItem('bi-geo-alt', item.city + ' · адреса — після прийняття', 'is-hidden-value'));
    return ul;
  }

  // ---- map ---------------------------------------------------------------
  let map = null;
  let layer = null;
  if (window.L) {
    map = L.map(mapEl, { zoomControl: false, scrollWheelZoom: true }).setView(UKRAINE, 6);
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
    box.appendChild(metaList(item, false));
    const link = el('a', 'mv-btn mv-btn--primary mv-btn--sm mv-btn--block', 'Детальніше');
    link.href = safeUrl(item.url);
    link.appendChild(icon('bi-arrow-right'));
    box.appendChild(link);
    return box;
  }

  // ---- list --------------------------------------------------------------
  function listRow(entry) {
    const item = entry.item;
    const li = el('li', 'mv-row bw-map-row');
    const body = el('div', 'mv-row__body');
    if (item.category) body.appendChild(el('p', 'mv-micro mv-mb-0', item.category));
    const title = el('h3', 'mv-row__title');
    const link = el('a', '', item.title || 'Запит допомоги');
    link.href = safeUrl(item.url);
    title.appendChild(link);
    body.appendChild(title);
    body.appendChild(metaList(item, true));
    if (entry.marker) {
      const show = el('button', 'mv-link-btn mv-link-btn--sm');
      show.type = 'button';
      show.appendChild(icon('bi-geo'));
      show.appendChild(document.createTextNode('Показати на карті'));
      show.addEventListener('click', function () {
        map.setView(entry.marker.getLatLng(), Math.max(map.getZoom(), 14));
        entry.marker.openPopup();
        // On phones the map sits above the list: bring it into view
        if (window.matchMedia('(max-width: 991.98px)').matches) {
          const rect = mapEl.getBoundingClientRect();
          if (rect.top < 0 || rect.bottom > window.innerHeight) mapEl.scrollIntoView({ block: 'center' });
        }
      });
      body.appendChild(show);
    }
    li.appendChild(body);
    return li;
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
    if (fit && map && layer.getLayers().length) {
      map.fitBounds(layer.getBounds(), { padding: [48, 48], maxZoom: 13 });
    }
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
        const entry = { item: item, marker: null, row: null };
        if (map && isFinite(item.lat) && isFinite(item.lon)) {
          entry.marker = L.marker([item.lat, item.lon], {
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
