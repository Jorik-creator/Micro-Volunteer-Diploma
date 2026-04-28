# MicroVolunteer

A web platform that connects people who need help with everyday tasks to volunteers ready to provide quick local support.

## Technologies

### Backend
- Python 3.12
- Django 5.x
- PostgreSQL 16
- Gunicorn

### Frontend
- Django Templates
- Bootstrap 5
- Leaflet.js (interactive map)
- Chart.js (statistics charts)

### DevOps
- Docker + docker-compose
- Nginx

## Quick Start

### Requirements
- Docker and Docker Compose
- Git

### Running with Docker

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd microvolunteer
   ```

2. Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```

3. Start the containers:
   ```bash
   docker-compose up --build
   ```

4. Run migrations and load initial data:
   ```bash
   docker-compose exec web python manage.py migrate
   docker-compose exec web python manage.py loaddata apps/requests/fixtures/initial_categories.json
   ```

5. Create a superuser:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

6. Open in your browser: http://localhost:8000

### Local Setup (without Docker)

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file and configure the database connection

4. Run migrations, load initial data, and start the server:
   ```bash
   python manage.py migrate
   python manage.py loaddata apps/requests/fixtures/initial_categories.json
   python manage.py runserver
   ```

## Project Structure

```
microvolunteer/
├── config/                 # Django configuration
│   └── settings/           # Split settings (base/dev/prod)
├── apps/
│   ├── accounts/           # Authentication and profiles
│   ├── requests/           # Help requests
│   ├── reviews/            # Ratings and reviews
│   ├── notifications/      # Notifications
│   └── stats/              # Statistics
├── templates/              # HTML templates
├── static/                 # Static files
├── media/                  # Uploaded files
├── nginx/                  # Nginx configuration
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Testing

```bash
pytest
```

Or with coverage:
```bash
coverage run -m pytest
coverage report
```

## License

Diploma project — all rights reserved.
