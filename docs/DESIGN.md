# Дизайн-система «Solid Blue» (v4)

Розвиток оригінального дизайну MicroVolunteer: Inter, темно-синя/синя палітра, карта України, м'які картки — але **солідно**: без наліпок, з іконками.

Стилі: [`static/css/mv.css`](../static/css/mv.css). Теги: `{% load mv_ui %}` ([`apps/core/templatetags/mv_ui.py`](../apps/core/templatetags/mv_ui.py)). Партіали: `templates/partials/`.

## Правила

1. **Жодних наліпок.** Категорія, статус, терміновість, формат, «перевірений» — завжди **іконка + текст** (`.mv-meta`, `{% request_status %}`, `{% urgency %}`). Pill-форма дозволена лише для: числових лічильників (`.mv-count`) і вибору-перемикача у формах (`.mv-chip-check`).
2. **Одна головна дія на екран** (`.mv-btn--primary`). Решта — `--secondary` / `--ghost` / `.mv-link-btn`.
3. **Нічого дрібніше 14px**, без uppercase-підписів. Контраст AA: для вторинного тексту — `.mv-muted` (#4B5563).
4. **Цілі для натискання ≥ 44px.** Кнопки мають іконку `bi-*` з `aria-hidden="true"`.
5. **Заголовки по порядку:** одна `h1` на сторінку, секції — `h2`, картки — `h3`.
6. **Порожній стан** — `partials/_empty.html` з однією дією. **Помилки форм** — `partials/_form_errors.html` зверху форми.
7. Без inline-стилів і без Bootstrap-кольорових компонентів (`btn-primary`, `alert-*`, `badge`, `text-bg-*`). Bootstrap — лише сітка (`row`, `col-*`), утиліти відступів/флексу, `dropdown`, `collapse`, `form-check`.
8. Сторінкові стилі — у `static/css/pages/<область>.css`, підключати через `{% block extra_css %}`. Спершу шукайте готовий клас у `mv.css`.
9. Сигнатура — **«нитка допомоги»** `.mv-thread` (пунктир з двома крапками): під заголовками секцій, у порожніх станах, у степері.

## Каркас сторінок

```django
{% extends "base.html" %}{% load mv_ui %}
{% block title %}Назва — MicroVolunteer{% endblock %}
{% block content %}
<section class="mv-page-head"><div class="container">
  <a class="mv-back" href="…"><i class="bi bi-arrow-left" aria-hidden="true"></i>Назад до …</a>
  <div class="mv-page-head__row">
    <div><h1>Заголовок</h1><p class="mv-lead">Пояснення одним реченням.</p></div>
    <a class="mv-btn mv-btn--primary" href="…"><i class="bi bi-plus-lg" aria-hidden="true"></i>Дія</a>
  </div>
</div></section>
<div class="container mv-page">…</div>
{% endblock %}
```

## Каталог компонентів

| Клас | Призначення |
|---|---|
| `.mv-section`, `--tight`, `--canvas` | секція 96/48px, світлий фон |
| `.mv-page-head`, `__row`, `.mv-back` | шапка сторінки, «назад» |
| `.mv-page`, `.mv-narrow`, `.mv-form-col` | контейнер вмісту, вузька колонка 760/720 |
| `.mv-grid --cards --2`, `.mv-layout-aside`, `.mv-sticky` | сітки; основна колонка + сайдбар 360px |
| `.mv-stack`, `--lg`, `.mv-cluster`, `.mv-spread` | вертикальний/горизонтальний ритм |
| `.mv-section-head` (`--center`) + `.mv-eyebrow` + `.mv-thread` | заголовок секції |
| `.mv-btn --primary --secondary --ghost --danger --danger-solid --white --outline-white --sm --lg --block` | кнопки |
| `.mv-link-btn --muted --danger --sm` | кнопка-посилання (форма з POST) |
| `.mv-card --flat --canvas --link`, `__title`, `__foot`, `.mv-stretched` | картка, клікабельна картка |
| `.mv-tile --lg --sm --success --warning --danger --muted --navy` | іконка в плитці 44px |
| `.mv-meta` (`--inline`), `li.is-hidden-value`, `li.is-negative` | рядки «іконка + текст» замість чипів |
| `.mv-summary` (dl) | ключ–значення з іконками (факти запиту, підсумок форми) |
| `.mv-status --success --warning --danger --muted --blue --navy` | статус: іконка + кольоровий текст |
| `.mv-urg --low --medium --high --critical` | терміновість: іконка-«антена» |
| `.mv-avatar --56 --96 --128`, `__badge`, `.mv-avatar-stack` | аватари (через `{% avatar user 56 %}`) |
| `.mv-count --blue` | числовий лічильник |
| `.mv-rating`, `.mv-stars` | рейтинг |
| `.mv-tabs`, `.mv-tab.is-active` | вкладки-підкреслення (посилання або кнопки) |
| `.mv-disclosure --danger`, `__body` | `<details>` для другорядних дій («Не можу допомогти») |
| `.form-control`, `.form-select`, `.form-label`, `.form-text`, `.mv-fieldset` | поля (crispy рендерить їх сам) |
| `.mv-choices` + `label.mv-choice` (input + `.mv-tile` + `__text/__title/__hint`) | вибір-картки (роль, формат, радіус) |
| `.mv-chip-check` (input + span) | перемикач-тег (теги оцінки, швидкі фільтри) |
| `.mv-form-errors` | зведення помилок (партіал) |
| `.mv-note --success --warning --danger --muted`, `__body/__title` | повідомлення з лівою смугою |
| `.mv-empty` | порожній стан (партіал) |
| `.mv-stepper` (`--rail`), `li.is-done/.is-current`, `.mv-step__dot` | степер (горизонтальний / вертикальний) |
| `.mv-stats` (`--compact`), `.mv-stat`, `__num`, `__label` | цифри з розділювачами |
| `.mv-rows` (`--joined`), `.mv-row.is-unread`, `__body __title __text __side __actions` | рядки списків (відгуки, сповіщення, розмови, модерація) |
| `.mv-group-title` | підзаголовок групи («Сьогодні») |
| `.mv-req` … (партіал `_request_card.html`) | картка запиту |
| `.mv-hero`, `__grid`, `__art`, `.mv-float --tr --bl`, `.mv-pin --hot`, `__trust` | головний банер з картою |
| `.mv-howto`, `.mv-cats`/`.mv-cat`, `.mv-cta` | «як це працює», категорії, CTA-смуга |
| `.mv-profile-band`, `.mv-profile-card` | шапка профілю |
| `.mv-chat`, `__head __log __system __compose __send`, `.mv-bubble --mine --phone`, `__meta` | розмова |
| `.mv-auth`, `__panel`, `__form`, `__card`, `.mv-divider` | сторінки входу/реєстрації |
| `.mv-prose` | юридичні тексти |
| `.mv-map-page`, `__side`, `__map` | сторінка карти |
| `.mv-photo` | фото запиту |

## Теги `mv_ui`

| Тег / фільтр | Результат |
|---|---|
| `{% request_status hr %}` | `.mv-status` з іконкою для кожного з 9 статусів запиту |
| `{% response_status resp %}` | те саме для відгуку волонтера |
| `{% urgency hr %}` / `{% urgency_icon hr %}` | терміновість з підписом / лише іконка |
| `{% category_icon cat %}` | `<i>` або SVG-лапка для «Тварини» (всередині `.mv-tile`) |
| `{% format_icon hr %}` | іконка формату допомоги |
| `{% avatar user 56 %}` | аватар (фото або ініціали) + галочка для перевірених |
| `{% notification_tile n %}` | плитка з іконкою типу сповіщення |
| `{% nav_class 'app:name' exact=True %}` | клас активного пункту меню |
| `{{ user\|short_name }}` | «Анна К.» |
| `{{ n\|uk_plural:"оцінка,оцінки,оцінок" }}` | українські форми множини |
| `{% demo_mode as x %}` | чи увімкнено демо-режим |

## Партіали

- `_request_card.html` — картка запиту. Параметри: `hr`, `show_status`, `card_note`, `card_note_value`, `card_action`.
- `_pagination.html` — пагінація; `extra_query` без `page`.
- `_form_errors.html` — зведення помилок (`form`).
- `_empty.html` — `icon`, `title`, `text`, `action_url`, `action_label`.
- `_rating_summary.html` (`rating`), `_review.html` (`review`, огортати в `<ul class="mv-rows">`), `_stars.html` (`value`).
- `_ukraine_map.svg` — вбудована карта для банера.

## Іконки

| Що | Іконки |
|---|---|
| Формати | візит додому `bi-house-door` · під двері `bi-door-closed` · публічне місце `bi-signpost-2` · онлайн `bi-telephone` |
| Факти | коли `bi-calendar-event` · тривалість `bi-stopwatch` · місце `bi-geo-alt` · прихована адреса `bi-lock` · волонтери `bi-people` · категорія `{% category_icon %}` |
| Довіра | перевірений `bi-patch-check-fill` · email `bi-envelope-check` · рейтинг `bi-star-fill` · виконано `bi-check2-all` |
| Дії | створити `bi-plus-lg` · відгукнутися `bi-hand-thumbs-up` · написати `bi-chat-dots` · прийняти `bi-check-lg` · відхилити `bi-x-lg` · виконано `bi-check2-circle` · редагувати `bi-pencil` · видалити `bi-trash3` · поскаржитися `bi-flag` · копіювати `bi-clipboard` · фільтри `bi-sliders` · карта `bi-map` · список `bi-list-ul` · назад `bi-arrow-left` |

## Спільний JS

- `static/js/base.js` — підтвердження (`data-confirm-submit="Питання?"` на кнопці), закриття `.mv-note`, панель зручності, лічильник сповіщень.
- `static/js/address-autocomplete.js` — підказки адрес Nominatim + міні-карта. API: `<input data-address-autocomplete data-lat="#id_latitude" data-lon="#id_longitude" data-city="#id_city" data-map="#mini-map">` (атрибути `data-city`/`data-map` необов'язкові). Використовують форма запиту й редагування профілю.

## Макети сторінок

- **Головна:** банер (h1, lead, дві кнопки ролей, рядок довіри з реальними цифрами | карта України в картці з пінами й двома «плаваючими» картками з *реальних* даних) → смуга цифр → категорії-посилання → «Як це працює» (дві колонки, кроки на нитці) → нові запити (3 картки) → безпека (3 рядки з іконками) → CTA для гостей.
- **Список запитів:** шапка + фільтри (картка зліва 300px на ≥992, над списком на мобільних) → рядок «N запитів · перемикач Список/Карта» → сітка карток → пагінація.
- **Карта:** бокова панель (фільтр, легенда іконками, список карток-рядків) + карта; попап — назва, мета-рядки, «Детальніше».
- **Запит:** «назад» → рядок статусу + категорія → h1 → двоколонково: основна картка (факти `.mv-summary`, фото, опис, для власника — відгуки волонтерів `.mv-rows` з кнопками) | сайдбар `.mv-sticky` (степер-рейка, блок дії з однією головною кнопкою, міні-профіль, примітка безпеки, «Поскаржитися»).
- **Форма запиту:** 720px, степер кроків зверху, одна картка на крок, «Назад»/«Далі» внизу, крок перевірки з `.mv-summary`.
- **Мої запити / Мої відгуки:** вкладки «Потребують дії / Активні / Завершені» → картки з `show_status` і `card_note`.
- **Профіль:** `.mv-profile-band` + `.mv-profile-card` (аватар 128, h1, рядки довіри, дії) → цифри `--compact` → картки (рівень довіри-степер, «залиште оцінку», особисті дані, волонтерський профіль, оцінки).
- **Сповіщення:** групи за днями, `.mv-rows--joined`, `{% notification_tile %}`, непрочитані `.is-unread`.
- **Розмови:** рядки з аватаром; чат `.mv-chat` з бульбашками.
- **Модерація:** вкладки з лічильниками → картки з `.mv-summary` доказів і панеллю дій.
- **Вхід/реєстрація:** `.mv-auth` — ліворуч темна панель з картою й трьома рядками довіри, праворуч форма; реєстрація починається з вибору ролі (`.mv-choice`).
