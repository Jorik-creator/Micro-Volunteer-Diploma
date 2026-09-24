/* Site-wide behaviour: confirmations, dismissible notes, accessibility
   preferences and the unread-notification counter. */
(function () {
  'use strict';

  // Buttons with data-confirm-submit ask before submitting their form
  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-confirm-submit]');
    if (button && !window.confirm(button.getAttribute('data-confirm-submit'))) event.preventDefault();
    const close = event.target.closest('[data-dismiss-note]');
    if (close) close.closest('.mv-note').remove();
  });

  // Collapse the mobile menu after a link is chosen
  const nav = document.getElementById('mainNav');
  if (nav) {
    nav.addEventListener('click', function (event) {
      if (!event.target.closest('a') || !nav.classList.contains('show')) return;
      bootstrap.Collapse.getOrCreateInstance(nav, { toggle: false }).hide();
    });
  }

  // Accessibility preferences (html classes, stored on this device)
  const root = document.documentElement;
  const storageKey = 'microvolunteer:a11y';
  const classMap = {
    highContrast: 'a11y-high-contrast',
    monochrome: 'a11y-monochrome',
    largeText: 'a11y-large-text',
    calmMode: 'a11y-calm-mode'
  };
  function readState() {
    try { return JSON.parse(localStorage.getItem(storageKey)) || {}; } catch (_) { return {}; }
  }
  function writeState(state) {
    try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* private mode */ }
  }
  function applyState(state) {
    Object.keys(classMap).forEach(function (key) {
      root.classList.toggle(classMap[key], Boolean(state[key]));
      document.querySelectorAll('[data-a11y-toggle="' + key + '"]').forEach(function (option) {
        option.setAttribute('aria-pressed', state[key] ? 'true' : 'false');
      });
    });
  }
  let state = readState();
  applyState(state);
  document.addEventListener('click', function (event) {
    const option = event.target.closest('[data-a11y-toggle]');
    if (option) {
      const key = option.getAttribute('data-a11y-toggle');
      state[key] = !state[key];
      writeState(state);
      applyState(state);
    }
    if (event.target.closest('#a11y-reset')) {
      state = {};
      writeState(state);
      applyState(state);
    }
  });

  // Unread notifications counter (polls only while the tab is visible)
  const script = document.currentScript;
  const countUrl = script && script.dataset.countUrl;
  const badge = document.getElementById('notification-badge');
  if (!countUrl || !badge) return;
  let previous = parseInt(badge.textContent, 10) || 0;
  let timer = null;

  function showToast(count) {
    const old = document.getElementById('mv-toast');
    if (old) old.remove();
    const toast = document.createElement('div');
    toast.id = 'mv-toast';
    toast.className = 'mv-toast';
    toast.setAttribute('role', 'status');
    const icon = document.createElement('i');
    icon.className = 'bi bi-bell-fill';
    icon.setAttribute('aria-hidden', 'true');
    const link = document.createElement('a');
    link.href = badge.closest('a').getAttribute('href');
    link.textContent = count === 1 ? 'Нове сповіщення' : 'Нові сповіщення: ' + count;
    toast.append(icon, link);
    document.body.appendChild(toast);
    window.setTimeout(function () { toast.remove(); }, 6000);
  }

  async function poll() {
    window.clearTimeout(timer);
    if (document.hidden) return;
    try {
      const response = await fetch(countUrl, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (response.ok) {
        const count = Number((await response.json()).count) || 0;
        if (count > previous) showToast(count);
        previous = count;
        badge.textContent = count;
        badge.classList.toggle('d-none', count === 0);
      }
    } catch (_) { /* offline — next poll retries */ }
    timer = window.setTimeout(poll, 20000);
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
  timer = window.setTimeout(poll, 20000);
})();
