"""
Django test settings for MicroVolunteer project.

Uses SQLite in-memory database for fast, isolated test runs.
No PostgreSQL dependency required.
"""
from .base import *  # noqa: F401,F403

DEBUG = False

# SQLite in-memory — fast, no external DB needed
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Faster password hashing for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable axes during tests (avoids lockout issues)
AXES_ENABLED = False

# Console email backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Disable CSRF checks in tests for simpler POST requests
MIDDLEWARE = [m for m in MIDDLEWARE if 'csrf' not in m.lower()]  # noqa: F405
