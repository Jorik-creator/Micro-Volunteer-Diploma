/* Request form wizard (create / edit): three steps, a summary built with
   textContent, format- and "on behalf"-dependent fields.
   Without JavaScript every step stays visible and the form submits as usual. */
(function () {
  'use strict';

  const form = document.getElementById('request-form');
  if (!form) return;
  const steps = Array.from(form.querySelectorAll('.mv-rq-step'));
  const stepper = document.getElementById('wizard-stepper');
  const markers = stepper ? Array.from(stepper.querySelectorAll('[data-step-marker]')) : [];
  const progress = document.getElementById('wizard-progress');
  const summary = document.getElementById('wizard-summary');
  const placeFields = document.getElementById('place-fields');
  const beneficiary = document.getElementById('beneficiary-fields');
  const onBehalf = form.elements.on_behalf;
  const address = form.elements.address;
  const city = form.elements.city;
  const neededDate = form.elements.needed_date;
  const titles = steps.map(function (step) { return step.querySelector('.mv-rq-step__title').textContent.trim(); });
  let current = 0;

  // ---------- Dependent fields ----------
  function chosenFormat() {
    const radio = form.querySelector('input[name="help_format"]:checked');
    return radio ? radio.value : '';
  }
  function syncFormat() {
    const remote = chosenFormat() === 'remote';
    if (placeFields) placeFields.hidden = remote;
  }
  function syncBehalf() {
    if (onBehalf && beneficiary) beneficiary.hidden = !onBehalf.checked;
  }
  form.querySelectorAll('input[name="help_format"]').forEach(function (radio) {
    radio.addEventListener('change', syncFormat);
  });
  if (onBehalf) onBehalf.addEventListener('change', syncBehalf);
  syncFormat();
  syncBehalf();

  // No past dates in the picker (the server checks as well)
  if (neededDate) {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    const min = now.toISOString().slice(0, 16);
    if (!neededDate.value || neededDate.value >= min) neededDate.min = min;
  }

  // ---------- Validation ----------
  function isShown(el) {
    return !el.closest('[hidden]:not(.mv-rq-step)');
  }
  function requireIf(el, condition, message) {
    if (!el) return;
    el.setCustomValidity(condition && !el.value.trim() ? message : '');
  }
  function applyCustomRules() {
    const remote = chosenFormat() === 'remote';
    requireIf(city, !remote, 'Вкажіть місто — його бачитимуть волонтери у списку.');
    requireIf(address, !remote, 'Вкажіть адресу — її побачить лише прийнятий волонтер.');
    const behalf = onBehalf && onBehalf.checked;
    requireIf(form.elements.beneficiary_name, behalf, 'Вкажіть, кому потрібна допомога.');
    requireIf(form.elements.beneficiary_phone, behalf, 'Потрібен телефон — волонтер зателефонує перед візитом.');
  }
  function firstInvalid(step) {
    applyCustomRules();
    const fields = Array.from(step.querySelectorAll('input, select, textarea'))
      .filter(function (el) { return el.type !== 'hidden' && isShown(el); });
    return fields.find(function (el) { return !el.checkValidity(); }) || null;
  }
  [city, address, form.elements.beneficiary_name, form.elements.beneficiary_phone].forEach(function (el) {
    if (el) el.addEventListener('input', function () { el.setCustomValidity(''); });
  });

  // ---------- Summary ----------
  function text(el) {
    return el ? el.textContent.replace(/\s+/g, ' ').replace('*', '').trim() : '';
  }
  function selectText(select) {
    if (!select || !select.value) return '';
    const option = select.options[select.selectedIndex];
    return option ? option.text : '';
  }
  // Same wording as the |when filter: 'Пт, 25 вересня, 19:57' (year only if not current)
  const WEEKDAYS = ['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
  const MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня',
    'серпня', 'вересня', 'жовтня', 'листопада', 'грудня'];
  function formatDate(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(value || '');
    if (!m) return value || '';
    const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    const year = date.getFullYear() === new Date().getFullYear() ? '' : ' ' + date.getFullYear();
    return WEEKDAYS[date.getDay()] + ', ' + date.getDate() + ' ' + MONTHS[date.getMonth()] + year + ', ' + m[4];
  }
  function shorten(value, limit) {
    const clean = (value || '').replace(/\s+/g, ' ').trim();
    return clean.length > limit ? clean.slice(0, limit - 1) + '…' : clean;
  }

  function placeText() {
    const where = address ? address.value.trim() : '';
    const town = city ? city.value.trim() : '';
    if (!where) return town;
    return town && where.indexOf(town) < 0 ? town + ', ' + where : where;
  }

  function groups() {
    const format = form.querySelector('input[name="help_format"]:checked');
    const formatLabel = format ? text(format.closest('label').querySelector('.mv-choice__title')) : '';
    const formatIcon = format ? format.closest('label').querySelector('.mv-tile i').className : 'bi bi-geo-alt';
    const photo = form.elements.photo;
    const remote = chosenFormat() === 'remote';
    const behalf = onBehalf && onBehalf.checked;
    const els = form.elements;
    return [
      { step: 0, title: titles[0], rows: [
        ['bi bi-card-heading', 'Заголовок', els.title && els.title.value.trim()],
        ['bi bi-text-paragraph', 'Опис', shorten(els.description && els.description.value, 180)],
        ['bi bi-grid', 'Категорія', selectText(els.category)],
        [formatIcon, 'Формат', formatLabel],
        ['bi bi-reception-3', 'Терміновість', selectText(els.urgency)],
        ['bi bi-image', 'Фото', photo && photo.files && photo.files[0] ? photo.files[0].name : '']
      ] },
      { step: 1, title: titles[1], rows: [
        ['bi bi-calendar-event', 'Коли', formatDate(neededDate && neededDate.value)],
        ['bi bi-stopwatch', 'Тривалість', selectText(els.duration)],
        ['bi bi-people', 'Волонтерів', els.volunteers_needed && els.volunteers_needed.value],
        ['bi bi-person-heart', 'Для кого', behalf ? [els.beneficiary_name.value.trim(), els.beneficiary_phone.value.trim()].filter(Boolean).join(' · ') : ''],
        ['bi bi-geo-alt', 'Місце', remote ? 'Онлайн / телефоном' : placeText()]
      ] }
    ];
  }

  function buildSummary() {
    if (!summary) return;
    summary.replaceChildren();
    groups().forEach(function (group) {
      const box = document.createElement('div');
      box.className = 'mv-rq-review__group';
      const head = document.createElement('div');
      head.className = 'mv-rq-review__head';
      const h3 = document.createElement('h3');
      h3.textContent = group.title;
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'mv-link-btn mv-link-btn--sm';
      edit.dataset.goto = String(group.step);
      edit.setAttribute('aria-label', 'Змінити: ' + group.title);
      const pencil = document.createElement('i');
      pencil.className = 'bi bi-pencil';
      pencil.setAttribute('aria-hidden', 'true');
      edit.append(pencil, 'Змінити');
      head.append(h3, edit);
      const dl = document.createElement('dl');
      dl.className = 'mv-summary';
      group.rows.forEach(function (row) {
        if (!row[2]) return;
        const dt = document.createElement('dt');
        const icon = document.createElement('i');
        icon.className = row[0];
        icon.setAttribute('aria-hidden', 'true');
        dt.append(icon, row[1]);
        const dd = document.createElement('dd');
        dd.textContent = row[2];
        dl.append(dt, dd);
      });
      box.append(head, dl);
      summary.appendChild(box);
    });
  }

  // ---------- Steps ----------
  function show(index, focus) {
    current = Math.max(0, Math.min(index, steps.length - 1));
    steps.forEach(function (step, i) { step.hidden = i !== current; });
    markers.forEach(function (li, i) {
      li.classList.toggle('is-done', i < current);
      li.classList.toggle('is-current', i === current);
      if (i === current) li.setAttribute('aria-current', 'step');
      else li.removeAttribute('aria-current');
      const dot = li.querySelector('.mv-step__dot');
      if (dot) {
        dot.replaceChildren();
        if (i < current) {
          const check = document.createElement('i');
          check.className = 'bi bi-check-lg';
          dot.appendChild(check);
        } else {
          dot.textContent = String(i + 1);
        }
      }
    });
    if (progress) progress.textContent = 'Крок ' + (current + 1) + ' з ' + steps.length + ': ' + titles[current];
    if (current === steps.length - 1) buildSummary();
    if (current === 1 && address) address.dispatchEvent(new CustomEvent('address:refresh-map'));
    if (focus) {
      const heading = steps[current].querySelector('.mv-rq-step__title');
      (stepper || heading).scrollIntoView({ block: 'start' });
      heading.focus({ preventScroll: true });
    }
  }

  function goNext() {
    const invalid = firstInvalid(steps[current]);
    if (invalid) { invalid.reportValidity(); return; }
    show(current + 1, true);
  }

  form.addEventListener('click', function (event) {
    if (event.target.closest('[data-next]')) goNext();
    else if (event.target.closest('[data-back]')) show(current - 1, true);
    else {
      const jump = event.target.closest('[data-goto]');
      if (jump) show(Number(jump.dataset.goto), true);
    }
  });

  // Enter in a one-line field moves forward instead of submitting half a form
  form.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' || event.defaultPrevented) return;
    const el = event.target;
    if (el.tagName !== 'INPUT' || ['submit', 'button', 'checkbox', 'radio', 'file'].indexOf(el.type) >= 0) return;
    if (current < steps.length - 1) { event.preventDefault(); goNext(); }
  });

  form.addEventListener('submit', function (event) {
    for (let i = 0; i < steps.length; i++) {
      const invalid = firstInvalid(steps[i]);
      if (invalid) {
        event.preventDefault();
        show(i, false);
        invalid.reportValidity();
        return;
      }
    }
  });

  // Links in the error summary open the step that holds the field
  const errors = document.getElementById('form-errors');
  if (errors) {
    errors.addEventListener('click', function (event) {
      const link = event.target.closest('a[href^="#"]');
      if (!link || link.getAttribute('href').length < 2) return;
      const target = document.getElementById(link.getAttribute('href').slice(1));
      const step = target && steps.findIndex(function (s) { return s.contains(target); });
      if (step >= 0) {
        event.preventDefault();
        show(step, false);
        target.focus();
      }
    });
  }

  // Turn on the wizard UI
  form.querySelectorAll('[data-js-only]').forEach(function (el) { el.hidden = false; });
  if (stepper) stepper.hidden = false;
  form.classList.add('is-wizard');

  // After a failed submit, open the step with the first server-side error
  const firstError = form.querySelector('.is-invalid, .invalid-feedback, [aria-invalid="true"]');
  const errorStep = firstError ? steps.findIndex(function (s) { return s.contains(firstError); }) : -1;
  show(errorStep >= 0 ? errorStep : 0, false);
})();
