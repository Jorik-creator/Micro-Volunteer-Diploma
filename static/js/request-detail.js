/* Request detail page: live status polling and the copy-address button.
   Loaded with data-status-url / data-status on the <script> tag. */
(function () {
  'use strict';

  const script = document.currentScript;

  // ---- Status polling: every 30 s while the tab is visible ----
  const statusUrl = script && script.dataset.statusUrl;
  const currentStatus = script && script.dataset.status;

  function showToast(text, strongText) {
    const old = document.getElementById('mv-toast');
    if (old) old.remove();
    const toast = document.createElement('div');
    toast.id = 'mv-toast';
    toast.className = 'mv-toast';
    toast.setAttribute('role', 'status');
    const icon = document.createElement('i');
    icon.className = 'bi bi-arrow-repeat';
    icon.setAttribute('aria-hidden', 'true');
    const body = document.createElement('span');
    body.append(text);
    const strong = document.createElement('strong');
    strong.textContent = strongText;
    body.append(strong, '. Оновлюємо сторінку…');
    toast.append(icon, body);
    document.body.appendChild(toast);
  }

  let reloading = false;
  async function poll() {
    if (document.hidden || reloading) return;
    try {
      const response = await fetch(statusUrl, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      if (!response.ok) return;
      const data = await response.json();
      if (data.status && data.status !== currentStatus) {
        reloading = true;
        showToast('Статус запиту змінився: ', data.status_display || data.status);
        window.setTimeout(function () { window.location.reload(); }, 2500);
      }
    } catch (_) { /* offline — the next tick retries */ }
  }

  if (statusUrl && currentStatus) window.setInterval(poll, 30000);

  // ---- Copy the exact address ----
  const copyButton = document.getElementById('copy-address-btn');
  const addressText = document.getElementById('address-text');
  if (!copyButton || !addressText) return;
  const label = copyButton.querySelector('[data-copy-label]');
  const icon = copyButton.querySelector('i');

  function fallbackCopy(text) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.className = 'visually-hidden';
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
    area.remove();
    return ok;
  }

  function flash(ok) {
    if (icon) icon.className = ok ? 'bi bi-check-lg' : 'bi bi-exclamation-circle';
    if (label) label.textContent = ok ? 'Скопійовано' : 'Не вдалося';
    copyButton.setAttribute('aria-label', ok ? 'Адресу скопійовано' : 'Не вдалося скопіювати адресу');
    window.setTimeout(function () {
      if (icon) icon.className = 'bi bi-clipboard';
      if (label) label.textContent = 'Копіювати';
      copyButton.setAttribute('aria-label', 'Скопіювати адресу');
    }, 2000);
  }

  copyButton.addEventListener('click', function () {
    const text = addressText.textContent.trim();
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        function () { flash(true); },
        function () { flash(fallbackCopy(text)); }
      );
    } else {
      flash(fallbackCopy(text));
    }
  });
})();
