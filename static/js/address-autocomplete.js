/* Address suggestions (OpenStreetMap Nominatim) with an optional Leaflet mini map.
   Shared by the request form and the profile edit page. API (docs/DESIGN.md):

     <input data-address-autocomplete data-lat="#id_latitude" data-lon="#id_longitude"
            data-city="#id_city" data-map="#mini-map">

   data-city and data-map are optional. Picking a suggestion fills lat/lon (and the
   city when it is empty); typing by hand clears lat/lon. The map appears only when
   data-map is given and Leaflet (window.L) is loaded; its marker can be dragged. */
(function () {
  'use strict';

  const ENDPOINT = 'https://nominatim.openstreetmap.org/search';
  const MIN_CHARS = 3;
  const DEBOUNCE_MS = 400;
  // Keyless OSM tiles (CARTO now watermarks tiles without an API key), as in map.js
  const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  let uid = 0;

  // Component styles live with the component, so every page using it gets them
  function injectStyles() {
    if (document.getElementById('mv-ac-styles')) return;
    const style = document.createElement('style');
    style.id = 'mv-ac-styles';
    style.textContent = [
      '.mv-ac-host{position:relative}',
      '.mv-ac-list{position:absolute;left:0;right:0;z-index:1050;margin:0;padding:6px;list-style:none;background:#fff;',
      'border:1px solid var(--mv-line,#E3E8F0);border-radius:var(--mv-r-sm,10px);box-shadow:var(--mv-sh-3,0 14px 36px rgba(15,35,73,.14));',
      'max-height:320px;overflow-y:auto}',
      '.mv-ac-list[hidden]{display:none}',
      '.mv-ac-option{display:flex;gap:10px;align-items:flex-start;min-height:44px;padding:10px 12px;border-radius:8px;cursor:pointer;',
      'font-size:16px;line-height:1.4;color:var(--mv-navy-900,#0F2349)}',
      '.mv-ac-option i{color:var(--mv-blue-600,#2563EB);margin-top:2px}',
      '.mv-ac-option small{display:block;font-size:14px;color:var(--mv-muted,#4B5563)}',
      '.mv-ac-option:hover,.mv-ac-option.is-active{background:var(--mv-blue-50,#EFF6FF)}',
      '.mv-ac-option.is-active{box-shadow:inset 3px 0 0 var(--mv-blue-600,#2563EB)}',
      '.mv-ac-empty{padding:10px 12px;font-size:15px;color:var(--mv-muted,#4B5563)}',
      '.mv-ac-map{height:260px;border-radius:var(--mv-r-md,16px);border:1px solid var(--mv-line,#E3E8F0);overflow:hidden;z-index:0}',
      '.mv-ac-map[hidden]{display:none}'
    ].join('');
    document.head.appendChild(style);
  }

  function $(selector) {
    return selector ? document.querySelector(selector) : null;
  }

  function splitName(item) {
    // "вулиця Хрещатик, 22, Київ, 01001, Україна" -> main line + rest
    const parts = String(item.display_name || '').split(', ');
    const main = parts.slice(0, 2).join(', ');
    const rest = parts.slice(2).filter(function (p) { return p !== 'Україна' && !/^\d{5}$/.test(p); }).join(', ');
    return { main: main, rest: rest };
  }

  function cityOf(item) {
    const a = item.address || {};
    return a.city || a.town || a.village || a.hamlet || a.municipality || '';
  }

  function setup(input) {
    if (input.dataset.acReady) return;
    input.dataset.acReady = '1';
    injectStyles();

    const latInput = $(input.dataset.lat);
    const lonInput = $(input.dataset.lon);
    const cityInput = $(input.dataset.city);
    const mapEl = $(input.dataset.map);
    const id = 'mv-ac-' + (++uid);

    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', id + '-list');
    input.setAttribute('autocomplete', 'off');

    const host = input.parentElement;
    host.classList.add('mv-ac-host');
    const list = document.createElement('ul');
    list.id = id + '-list';
    list.className = 'mv-ac-list';
    list.setAttribute('role', 'listbox');
    list.setAttribute('aria-label', 'Підказки адрес');
    list.hidden = true;
    input.insertAdjacentElement('afterend', list);

    const live = document.createElement('span');
    live.className = 'visually-hidden';
    live.setAttribute('aria-live', 'polite');
    host.appendChild(live);

    let results = [];
    let active = -1;
    let timer = null;
    let controller = null;
    let map = null;
    let marker = null;

    function place() {
      list.style.top = (input.offsetTop + input.offsetHeight + 4) + 'px';
    }

    function close() {
      list.hidden = true;
      active = -1;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    }

    function highlight(index) {
      const options = list.querySelectorAll('[role="option"]');
      active = index;
      options.forEach(function (option, i) {
        const on = i === index;
        option.classList.toggle('is-active', on);
        option.setAttribute('aria-selected', on ? 'true' : 'false');
        if (on) option.scrollIntoView({ block: 'nearest' });
      });
      if (index >= 0 && options[index]) input.setAttribute('aria-activedescendant', options[index].id);
      else input.removeAttribute('aria-activedescendant');
    }

    function render(items) {
      results = items;
      list.replaceChildren();
      if (!items.length) {
        const empty = document.createElement('li');
        empty.className = 'mv-ac-empty';
        empty.textContent = 'Нічого не знайдено. Спробуйте додати місто або номер будинку.';
        list.appendChild(empty);
        live.textContent = 'Підказок не знайдено';
      } else {
        items.forEach(function (item, index) {
          const name = splitName(item);
          const option = document.createElement('li');
          option.id = id + '-opt-' + index;
          option.className = 'mv-ac-option';
          option.setAttribute('role', 'option');
          option.setAttribute('aria-selected', 'false');
          const icon = document.createElement('i');
          icon.className = 'bi bi-geo-alt';
          icon.setAttribute('aria-hidden', 'true');
          const text = document.createElement('span');
          text.textContent = name.main;
          if (name.rest) {
            const small = document.createElement('small');
            small.textContent = name.rest;
            text.appendChild(small);
          }
          option.append(icon, text);
          // mousedown keeps focus in the input
          option.addEventListener('mousedown', function (event) { event.preventDefault(); });
          option.addEventListener('click', function () { choose(index); });
          list.appendChild(option);
        });
        live.textContent = items.length === 1 ? 'Одна підказка' : 'Підказок: ' + items.length;
      }
      place();
      list.hidden = false;
      active = -1;
      input.setAttribute('aria-expanded', 'true');
      input.removeAttribute('aria-activedescendant');
    }

    async function search(query) {
      if (controller) controller.abort();
      controller = new AbortController();
      const params = new URLSearchParams({
        q: query, format: 'json', addressdetails: '1', limit: '6',
        countrycodes: 'ua', 'accept-language': 'uk'
      });
      try {
        const response = await fetch(ENDPOINT + '?' + params.toString(), {
          signal: controller.signal,
          headers: { Accept: 'application/json' }
        });
        if (!response.ok) return;
        const data = await response.json();
        if (document.activeElement !== input || input.value.trim() !== query) return;
        // Nominatim may return the same address twice (building + entrance)
        const seen = new Set();
        render((Array.isArray(data) ? data : []).filter(function (item) {
          const key = item.display_name;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        }));
      } catch (error) {
        if (error.name !== 'AbortError') close();
      }
    }

    function showMap(lat, lon) {
      if (!mapEl || !window.L) return;
      mapEl.classList.add('mv-ac-map');
      mapEl.hidden = false;
      if (!map) {
        map = window.L.map(mapEl, { scrollWheelZoom: false }).setView([lat, lon], 16);
        window.L.tileLayer(TILES, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map);
        marker = window.L.marker([lat, lon], { draggable: true, keyboard: true, title: 'Місце допомоги' }).addTo(map);
        marker.on('dragend', function () {
          const pos = marker.getLatLng();
          if (latInput) latInput.value = pos.lat.toFixed(6);
          if (lonInput) lonInput.value = pos.lng.toFixed(6);
        });
      } else {
        map.setView([lat, lon], 16);
        marker.setLatLng([lat, lon]);
      }
      window.setTimeout(function () { map.invalidateSize(); }, 60);
    }

    function hideMap() {
      if (mapEl) mapEl.hidden = true;
    }

    function choose(index) {
      const item = results[index];
      if (!item) return;
      const lat = parseFloat(item.lat);
      const lon = parseFloat(item.lon);
      input.value = item.display_name;
      if (latInput) latInput.value = lat.toFixed(6);
      if (lonInput) lonInput.value = lon.toFixed(6);
      const city = cityOf(item);
      if (cityInput && city && !cityInput.value.trim()) {
        cityInput.value = city;
        cityInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
      close();
      input.dispatchEvent(new CustomEvent('address:selected', { bubbles: true, detail: { lat: lat, lon: lon, city: city } }));
      showMap(lat, lon);
    }

    input.addEventListener('input', function () {
      // Typed by hand: the old coordinates no longer match
      if (latInput) latInput.value = '';
      if (lonInput) lonInput.value = '';
      hideMap();
      window.clearTimeout(timer);
      const query = input.value.trim();
      if (query.length < MIN_CHARS) {
        if (controller) controller.abort();
        close();
        return;
      }
      timer = window.setTimeout(function () { search(query); }, DEBOUNCE_MS);
    });

    input.addEventListener('keydown', function (event) {
      const open = !list.hidden && results.length > 0;
      if (event.key === 'ArrowDown' && open) {
        event.preventDefault();
        highlight(active < results.length - 1 ? active + 1 : 0);
      } else if (event.key === 'ArrowUp' && open) {
        event.preventDefault();
        highlight(active > 0 ? active - 1 : results.length - 1);
      } else if (event.key === 'Enter' && open && active >= 0) {
        event.preventDefault();
        choose(active);
      } else if (event.key === 'Escape' && !list.hidden) {
        event.preventDefault();
        close();
      }
    });

    input.addEventListener('blur', function () { window.setTimeout(close, 150); });
    window.addEventListener('resize', function () { if (!list.hidden) place(); });

    // Edit forms: coordinates already saved — show them on the map
    const lat0 = latInput && parseFloat(latInput.value);
    const lon0 = lonInput && parseFloat(lonInput.value);
    if (lat0 && lon0 && input.value.trim()) showMap(lat0, lon0);

    // Let other scripts redraw the map after it was inside a hidden block
    input.addEventListener('address:refresh-map', function () {
      if (map && mapEl && !mapEl.hidden) map.invalidateSize();
    });
  }

  function init() {
    document.querySelectorAll('input[data-address-autocomplete]').forEach(setup);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
