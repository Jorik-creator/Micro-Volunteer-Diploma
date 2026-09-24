"""
Django production settings for MicroVolunteer project.

Extends base.py with DEBUG=False and strict security settings.
Requires SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
"""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

# The host terminates TLS and forwards the original scheme in this header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SECURE_CONTENT_TYPE_NOSNIFF = True

SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = True

CSRF_COOKIE_SECURE = True

X_FRAME_OPTIONS = "DENY"

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)

SECURE_HSTS_INCLUDE_SUBDOMAINS = True

SECURE_HSTS_PRELOAD = True
