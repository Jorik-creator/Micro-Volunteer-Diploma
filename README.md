# MicroVolunteer

Веб-платформа для з'єднання людей, що потребують допомоги у повсякденних справах, з волонтерами, готовими надати швидку локальну підтримку.

## Технології

### Backend
- Python 3.12
- Django 5.x
- PostgreSQL 16
- Gunicorn

### Frontend
- Django Templates
- Bootstrap 5
- Leaflet.js (інтерактивна карта)
- Chart.js (графіки статистики)

### DevOps
- Docker + docker-compose
- Nginx

## Швидкий старт

### Вимоги
- Docker та Docker Compose
- Git

### Запуск через Docker

1. Клонуйте репозиторій:
   ```bash
   git clone <repository-url>
   cd microvolunteer
   ```

2. Створіть файл `.env` з `.env.example`:
   ```bash
   cp .env.example .env
   ```

3. Запустіть контейнери:
   ```bash
   docker-compose up --build
   ```

4. Виконайте міграції та завантажте початкові дані:
   ```bash
   docker-compose exec web python manage.py migrate
   docker-compose exec web python manage.py loaddata apps/requests/fixtures/initial_categories.json
   ```

5. Створіть суперкористувача:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

6. Відкрийте у браузері: http://localhost:8000

### Локальний запуск (без Docker)

1. Створіть віртуальне середовище:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. Встановіть залежності:
   ```bash
   pip install -r requirements.txt
   ```

3. Створіть `.env` та налаштуйте підключення до БД

4. Виконайте міграції, завантажте початкові дані та запустіть сервер:
   ```bash
   python manage.py migrate
   python manage.py loaddata apps/requests/fixtures/initial_categories.json
   python manage.py runserver
   ```

## Структура проекту

```
microvolunteer/
├── config/                 # Конфігурація Django
│   └── settings/           # Розділені налаштування (base/dev/prod)
├── apps/
│   ├── accounts/           # Автентифікація та профілі
│   ├── requests/           # Запити допомоги
│   ├── reviews/            # Рейтинги та відгуки
│   ├── notifications/      # Сповіщення
│   └── stats/              # Статистика
├── templates/              # HTML-шаблони
├── static/                 # Статичні файли
├── media/                  # Завантажені файли
├── nginx/                  # Конфігурація Nginx
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Тестування

```bash
pytest
```

Або з покриттям:
```bash
coverage run -m pytest
coverage report
```

## Ліцензія

Дипломний проект — всі права захищені.
