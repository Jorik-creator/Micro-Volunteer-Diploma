# Безкоштовний стек: Render + Neon + Supabase Storage + Brevo

Проєкт — портфоліо без бюджету, тож потрібен $0 без прив'язки картки та без терміну дії. Render free web service (gunicorn) не має постійного диска й блокує SMTP-порти, а його безкоштовна БД видаляється через 30 днів. Тому: БД — Neon Postgres, медіа — Supabase Storage через S3-API (`django-storages`), зображення стискаються при завантаженні, email — Brevo HTTP API через `django-anymail`, статика — WhiteNoise. Конфігурація лише через змінні оточення, тож переїзд на платний хостинг не потребує змін коду.

## Considered Options

- Railway — після пробного періоду $1/міс, замало для Django + Postgres.
- Vercel — serverless: холодні старти, міграції з CI, cron раз на добу.
- PythonAnywhere — без Postgres і з білим списком вихідних з'єднань.
