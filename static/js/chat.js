/* Conversation page: fetches new messages every 5 s while the tab is visible.
   Message bodies are only ever set with textContent — never parsed as HTML,
   and links are never made clickable (ADR 0007). */
(function () {
  'use strict';

  const log = document.getElementById('chat-log');
  if (!log) return;

  const url = log.dataset.url;
  const reportUrl = log.dataset.reportUrl || ''; // absent for moderators
  const next = encodeURIComponent(window.location.pathname);
  let lastId = parseInt(log.dataset.lastId, 10) || 0;
  let busy = false;

  // The log grows with its content (personal.css caps it); scroll only once it overflows
  function scrollToEnd() {
    if (log.scrollHeight > log.clientHeight) log.scrollTop = log.scrollHeight;
  }
  scrollToEnd();

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function icon(name, extra) {
    const node = el('i', 'bi ' + name + (extra ? ' ' + extra : ''));
    node.setAttribute('aria-hidden', 'true');
    return node;
  }

  function render(m) {
    const empty = document.getElementById('chat-empty');
    if (empty) empty.remove();

    if (m.kind === 'system') {
      const note = el('p', 'mv-chat__system');
      note.append(icon('bi-info-circle'), el('span', '', m.body));
      log.appendChild(note);
      return;
    }

    const bubble = el('div', 'mv-bubble' + (m.mine ? ' mv-bubble--mine' : '') + (m.kind === 'phone' ? ' mv-bubble--phone' : ''));
    const text = el('span', 'mv-bubble__text');
    if (m.kind === 'phone') text.appendChild(icon('bi-telephone', 'mv-bubble__icon'));
    text.appendChild(document.createTextNode(m.body));

    const meta = el('span', 'mv-bubble__meta');
    if (!m.mine) {
      meta.appendChild(el('span', '', m.sender));
      const dot = el('span', '', '·');
      dot.setAttribute('aria-hidden', 'true');
      meta.appendChild(dot);
    }
    meta.appendChild(el('time', '', m.time));
    if (!m.mine && reportUrl) {
      const report = el('a', 'mv-link-btn mv-link-btn--sm mv-bubble__report');
      report.href = reportUrl.replace(/\/0\/$/, '/' + Number(m.id) + '/') + '?next=' + next;
      report.append(icon('bi-flag'), 'Поскаржитися');
      meta.appendChild(report);
    }

    bubble.append(text, meta);
    log.appendChild(bubble);
  }

  function closeComposer() {
    ['chat-form', 'chat-tools'].forEach(function (id) {
      const node = document.getElementById(id);
      if (node) node.remove();
    });
    const closed = document.getElementById('chat-closed');
    if (closed) closed.hidden = false;
  }

  async function poll() {
    if (document.hidden || busy) return;
    busy = true;
    try {
      const response = await fetch(url + '?after=' + lastId, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      if (!response.ok) return;
      const data = await response.json();
      if (data.messages.length) {
        const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
        data.messages.forEach(function (m) {
          if (m.id <= lastId) return;
          render(m);
          lastId = m.id;
        });
        if (nearBottom) scrollToEnd();
      }
      if (!data.writable) closeComposer();
    } catch (_) {
      /* offline — the next poll retries */
    } finally {
      busy = false;
    }
  }

  window.setInterval(poll, 5000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });

  // Composer: Ctrl/Cmd+Enter sends; the button is disabled while the form submits
  const form = document.getElementById('chat-form');
  if (form) {
    const body = form.querySelector('textarea');
    body.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
    form.addEventListener('submit', function () {
      const button = form.querySelector('button[type="submit"]');
      if (button) window.setTimeout(function () { button.disabled = true; }, 0);
    });
  }
})();
