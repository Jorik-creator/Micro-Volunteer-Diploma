"""
Django development settings for MicroVolunteer project.

Extends base.py with DEBUG=True. Uses SQLite unless DATABASE_URL is set.
"""

from .base import *  # noqa: F403

DEBUG = True

# Serve static files straight from app directories without collectstatic
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
