# Деплой за $0

Стек (див. [ADR 0005](adr/0005-free-hosting-stack.md)): **Render** (застосунок) + **Neon** (PostgreSQL) + **Supabase Storage** (фото) + **Brevo** (email) + **cron-job.org** (періодичні задачі). Усе безкоштовно, без прив'язки картки (станом на вересень 2026 — перевіряйте умови при реєстрації).

Порядок важливий: спершу сервіси з даними, потім Render.

## 1. Neon — база даних

1. Зареєструйтеся на neon.com → **Create project**, регіон **Frankfurt (eu-central-1)**.
2. На сторінці проєкту → **Connect** → скопіюйте рядок підключення (`postgresql://…?sslmode=require`).
3. Це значення `DATABASE_URL`.

> Neon засинає після 5 хв без запитів — перший запит після паузи займає ~1 с. Для демо це нормально.

## 2. Supabase — фото (необов'язково для першого запуску)

Без цього кроку сайт працює, але завантажені фото зникатимуть після кожного перезапуску Render.

1. supabase.com → **New project** (регіон Frankfurt).
2. **Storage → New bucket** `media`, увімкніть **Public bucket**.
3. **Project Settings → Storage → S3 Connection**: увімкніть, створіть **S3 access key**.
4. Змінні:
   - `AWS_STORAGE_BUCKET_NAME=media`
   - `AWS_S3_ENDPOINT_URL=https://<project-ref>.supabase.co/storage/v1/s3`
   - `AWS_S3_REGION_NAME=eu-central-1` (як показано на сторінці S3 Connection)
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — з кроку 3
   - `AWS_S3_CUSTOM_DOMAIN=<project-ref>.supabase.co/storage/v1/object/public/media`

> Безкоштовний проєкт Supabase ставиться на паузу після тижня без активності — його можна «розбудити» з панелі.

## 3. Brevo — email (необов'язково для першого запуску)

Без ключа листи просто пишуться в лог. Для справжніх листів:

1. brevo.com → реєстрація → **SMTP & API → API Keys → Generate**.
2. **Senders → Add a sender** — вкажіть свою пошту й підтвердьте її.
3. Змінні: `BREVO_API_KEY=…`, `DEFAULT_FROM_EMAIL=MicroVolunteer <ваша-підтверджена@пошта>`.

## 4. Render — застосунок

1. render.com → вхід через GitHub.
2. **New → Blueprint** → оберіть репозиторій `Micro-Volunteer-Diploma`. Render прочитає [`render.yaml`](../render.yaml).
3. Заповніть змінні з позначкою *sync: false*:
   - `DATABASE_URL` — з Neon (обов'язково);
   - Supabase і Brevo — якщо налаштували;
   - `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` — ваш адмін-акаунт (створюється під час першого запуску).
4. **Apply**. Перший деплой триває 3–5 хв. Під час старту застосунок сам:
   - застосує міграції;
   - створить адміна;
   - заповнить демо-дані (`DEMO_MODE=True`).
5. Відкрийте `https://<назва>.onrender.com` → **Увійти** → кнопки демо-входу.

> З `DEMO_MODE=True` сайт працює як публічне демо: реєстрацію вимкнено (демо-модератор доступний усім, а дані щодня перезаписуються), демо-акаунти не можна заблокувати чи видалити. Для «справжнього» запуску встановіть `DEMO_MODE=False`.

## 5. cron-job.org — періодичні задачі

Прострочення запитів, автопідтвердження, нагадування, публікація оцінок і щоденне оновлення демо запускаються запитом `POST /tasks/run/`. Він же не дає сервісу на Render заснути.

1. У Render → сервіс → **Environment** скопіюйте згенерований `CRON_SECRET`.
2. cron-job.org → **Create cronjob**:
   - URL: `https://<назва>.onrender.com/tasks/run/`
   - Schedule: кожні **10 хвилин**
   - **Advanced → Request method:** `POST`
   - **Headers:** `Authorization: Bearer <CRON_SECRET>`
3. **Test run** → відповідь `200` з JSON на кшталт `{"expire_overdue": 0, …}`.

## Перевірка після деплою

- [ ] Головна відкривається по HTTPS, стилі на місці.
- [ ] Демо-вхід працює для всіх трьох ролей.
- [ ] Модератор бачить черги модерації.
- [ ] Реєстрація нового акаунта надсилає лист (якщо налаштовано Brevo).
- [ ] `https://<назва>.onrender.com/admin/` — вхід адміністратором.
- [ ] cron-job.org показує успішні виклики.
