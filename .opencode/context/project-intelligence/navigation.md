<!-- Context: project-intelligence/navigation | Priority: high | Version: 1.3 | Updated: 2026-04-08 -->

# Project Intelligence

**Purpose**: Quick navigation to all project intelligence files.
**Last Updated**: 2026-04-08

## Files

| File | Description | Priority |
|------|-------------|----------|
| technical-domain.md | Tech stack, code patterns, naming, security | critical |

## Quick Routes
- **Tech stack?** → technical-domain.md § Primary Stack
- **How to write a view?** → technical-domain.md § Code Patterns
- **How to write a form?** → technical-domain.md § Code Patterns → Forms
- **Registration pattern?** → technical-domain.md § Code Patterns → Registration
- **Dual-form editing?** → technical-domain.md § Code Patterns → Dual-Form Editing
- **Auth views?** → technical-domain.md § Code Patterns → Auth Views
- **Naming rules?** → technical-domain.md § Naming Conventions
- **Security checklist?** → technical-domain.md § Security Requirements
- **What files exist?** → technical-domain.md § Codebase References
- **Project structure?** → technical-domain.md § Project Structure
- **Testing setup?** → technical-domain.md § Testing Architecture
- **Test factories?** → technical-domain.md § Testing Architecture → Factories
- **How to run tests?** → technical-domain.md § Testing Architecture → Running Tests

## Implementation Status
| Module | Models | Forms | Views | URLs | Templates | Admin | Tests | Migrations | Status |
|--------|--------|-------|-------|------|-----------|-------|-------|------------|--------|
| accounts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 26 | ✅ | **Done** |
| requests | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 63 | ✅ | **Phase 1 Done** |
| reviews | ✅ | — | — | — | — | ✅ | ✅ 6 | ✅ | Models + Admin + Tests |
| notifications | ✅ | — | — | — | — | ✅ | ✅ 6 | ✅ | Models + Admin + Tests |
| stats | — | — | — | — | — | — | — | ✅ | Placeholder |

**Total: 101 tests passing** (pytest + factory_boy, ~2s on SQLite in-memory)

## requests app — що реалізовано (Phase 1)
- `forms.py` — HelpRequestForm (валідація дати, фото), FilterForm, ResponseForm
- `views.py` — 12 views: List, Detail, Create, Update, MyRequests, MapView, map_data (JSON), respond, accept, reject, complete, cancel
- `urls.py` — 13 маршрутів, namespace `requests:`
- `management/commands/expire_requests.py` — `--dry-run`, атомарний UPDATE
- `templates/requests/` — request_list, request_detail, request_form, my_requests, map (Leaflet.js)
- `config/urls.py` — підключено `apps.requests.urls`
- `templates/base.html` — navbar: волонтер→Запити, отримувач→Мої запити, обидва→Карта

## Бізнес-правила requests (закодовані у views.py)
- Max 10 активних запитів на отримувача
- State machine: active→in_progress→completed / active→cancelled / active→expired
- `select_for_update()` + `transaction.atomic()` при accept (race condition)
- Автоматичне відхилення pending при заповненні квоти
- Координати офсетяться ~150м до підтвердження волонтера (utils.offset_coordinates)
- Тільки підтверджений волонтер може завершити запит (Q23)
