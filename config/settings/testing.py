"""
Django test settings for MicroVolunteer project.

Uses SQLite in-memory database for fast, isolated test runs.
No PostgreSQL or .env file required.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-only-insecure-key")

from .base import *  # noqa: F403

DEBUG = False

# SQLite in-memory — fast, no external DB needed
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# WhiteNoise is irrelevant for tests and warns about the missing STATIC_ROOT
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405

# Faster password hashing for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable axes during tests (avoids lockout issues)
AXES_ENABLED = False

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
