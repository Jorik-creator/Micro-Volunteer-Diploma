/* Request list filters: leave empty fields out of the URL so that
   "?category=&urgency=" does not count as an applied filter. */
(function () {
  'use strict';
  const form = document.querySelector('[data-clean-query]');
  if (!form) return;
  form.addEventListener('submit', function () {
    Array.prototype.forEach.call(form.elements, function (el) {
      if (el.name && !el.disabled && el.type !== 'checkbox' && el.value === '') el.disabled = true;
    });
    // Re-enable after navigation starts, so going "back" shows a usable form
    setTimeout(function () {
      Array.prototype.forEach.call(form.elements, function (el) { el.disabled = false; });
    }, 0);
  });
})();
