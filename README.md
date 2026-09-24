# MicroVolunteer

[![CI](https://github.com/Jorik-creator/Micro-Volunteer-Diploma/actions/workflows/ci.yml/badge.svg)](https://github.com/Jorik-creator/Micro-Volunteer-Diploma/actions/workflows/ci.yml)

Платформа, що з'єднує людей, яким потрібна дрібна побутова допомога (купити ліки, донести покупки, провести до лікаря, розібратися з Дією), з волонтерами поблизу. Головна аудиторія отримувачів — літні люди, люди з інвалідністю, ВПО. Тому на першому місці довіра, приватність і доступність.

> **Демо:** на сторінці входу є кнопки «Я волонтер», «Мені потрібна допомога» і «Модератор». Вхід без пароля, дані оновлюються щодня.

*English summary: a Django 5 platform matching people who need small everyday help with nearby volunteers. It has trust levels with verification (no identity documents stored), an explicit request lifecycle, two-sided blind reviews, private chat with opt-in phone sharing and on-site moderation. It is tuned for elderly users and runs on a $0 hosting stack.*

## Можливості

**Для отримувача**
- Запит за три кроки: що потрібно → коли й де → перевірка. Формат допомоги: візит додому, під двері, зустріч у публічному місці, онлайн.
- Запит можна подати від імені іншої людини (родич, соцпрацівник).
- Отримувач обирає волонтера за рейтингом, відгуками й позначкою «Перевірений».
- Спілкування у вбудованій розмові. Номер телефону показується лише тоді, коли людина сама ним поділиться.
- Підтвердження виконання та двостороння оцінка.

**Для волонтера**
- Список і карта запитів. На карті місце зі зсувом ~150 м, точну адресу бачить лише прийнятий волонтер.
- Сповіщення про запити поблизу за категоріями й радіусом.
- Можна вийти із запиту з поясненням причини. Запит тоді знову відкривається для інших.

**Довіра й безпека**
- Рівні довіри: *зареєстрований → email підтверджено → перевірений*. Візити додому доступні лише перевіреним волонтерам.
- Перевірка без документів: анкета, яку розглядає модератор, або код партнерської організації.
- Перші запити нових отримувачів проходять премодерацію.
- Скарги на запити, людей, оцінки та повідомлення. Черга модерації на сайті.
- Оцінки приховані, доки обидві сторони не оцінили одна одну.
- EXIF, зокрема GPS, видаляється з фото. Користувач може сам видалити акаунт з анонімізацією даних.

**Доступність:** базовий текст 17 px, контраст WCAG AA, цілі для натискання від 44 px. Панель «Зручність» має режими великого тексту, високого контрасту та без анімацій. Сторінки працюють з клавіатури й зі скрінрідерами.

## Технології

| | |
|---|---|
| Backend | Python 3.12, Django 5.2 LTS, PostgreSQL (SQLite локально) |
| Frontend | Django Templates, Bootstrap 5, Leaflet (карта), без збирача фронтенду |
| Інфраструктура | Gunicorn, WhiteNoise, django-storages (S3), django-anymail (Brevo) |
| Якість | pytest (320+ тестів, покриття ≥ 90 %), ruff, GitHub Actions |
| Хостинг | Render + Neon + Supabase Storage + Brevo + cron-job.org — усе безкоштовно |

## Архітектура

- **Сервісний шар.** Усі переходи станів запиту живуть у [`apps/requests/services.py`](apps/requests/services.py): блокування рядка, перевірка прав і явні сповіщення. Сигналів у бізнес-логіці немає ([ADR 0003](docs/adr/0003-state-transitions-in-services.md)).
- **Періодичні задачі без воркера.** Зовнішній cron викликає `POST /tasks/run/`, а всі задачі ідемпотентні ([ADR 0004](docs/adr/0004-cron-endpoint-instead-of-worker.md)).
- **Документація рішень.** Словник домену — [CONTEXT.md](CONTEXT.md), рішення — [docs/adr](docs/adr/), план і діаграма станів — [docs/ROADMAP.md](docs/ROADMAP.md).

```
apps/
├── accounts/       користувачі, ролі, рівні довіри, профілі, видалення акаунта
├── requests/       запити, відгуки волонтерів, життєвий цикл (services.py)
├── reviews/        двосторонні приховані оцінки
├── conversations/  розмови отримувач ↔ волонтер
├── moderation/     перевірка, коди організацій, скарги, черга модерації
├── notifications/  сповіщення на сайті та email, налаштування
├── stats/          панель статистики для персоналу
└── core/           періодичні задачі, демо-дані, юридичні сторінки, обробка фото
```

## Локальний запуск

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Щоб з'явилися кнопки демо-входу, вкажіть у `.env` `DEMO_MODE=True`. Листи локально виводяться в консоль.

Для роботи з PostgreSQL через Docker:

```bash
docker compose up --build
```

## Тести

```bash
pytest
coverage run -m pytest && coverage report
ruff check . && ruff format --check .
```

## Деплой

Покрокова інструкція: [docs/DEPLOY.md](docs/DEPLOY.md). Конфігурація Render: [`render.yaml`](render.yaml).

## Ліцензія

Дипломний проєкт — усі права захищені.
