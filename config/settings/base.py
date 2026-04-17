"""
Django base settings for MicroVolunteer project.

Shared configuration inherited by development.py and production.py.
Secrets loaded via python-decouple from .env file.
"""

from pathlib import Path

from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")

# Hosts allowed to serve the application
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Django built-in
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third-party
    "axes",
    "crispy_forms",
    "crispy_bootstrap5",
    # Project apps
    "apps.accounts",
    "apps.requests",
    "apps.reviews",
    "apps.notifications",
    "apps.stats",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.notifications.context_processors.unread_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "uk"

TIME_ZONE = "Europe/Kyiv"

USE_I18N = True

USE_TZ = True


# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [BASE_DIR / "static"]


# ---------------------------------------------------------------------------
# Media files (user uploads)
# ---------------------------------------------------------------------------

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Crispy Forms — Bootstrap 5
# ---------------------------------------------------------------------------

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

CRISPY_TEMPLATE_PACK = "bootstrap5"


# ---------------------------------------------------------------------------
# django-axes — brute force protection
# ---------------------------------------------------------------------------

AXES_FAILURE_LIMIT = 5

AXES_COOLOFF_TIME = 1  # hours

AXES_LOCKOUT_TEMPLATE = None  # use default

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]


# ---------------------------------------------------------------------------
# Authentication URLs
# ---------------------------------------------------------------------------

LOGIN_URL = "/accounts/login/"

LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = "/"
