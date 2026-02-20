"""
Django development settings for MicroVolunteer project.

Extends base.py with DEBUG=True, local PostgreSQL, and console email.
"""
from .base import *  # noqa: F401,F403

from decouple import config

DEBUG = True

# For local development without Docker, fallback to SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# For Docker / PostgreSQL, uncomment below and comment out SQLite above:
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': config('POSTGRES_DB', default='microvolunteer'),
#         'USER': config('POSTGRES_USER', default='microvolunteer'),
#         'PASSWORD': config('POSTGRES_PASSWORD', default='microvolunteer'),
#         'HOST': config('DB_HOST', default='localhost'),
#         'PORT': config('DB_PORT', default='5432'),
#     }
# }

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
