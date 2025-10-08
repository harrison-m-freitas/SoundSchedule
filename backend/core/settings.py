import os
from pathlib import Path
import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(
    DJANGO_DEBUG=(bool, True),
    DJANGO_SECRET_KEY=(str, "insecure-key"),
    DJANGO_ALLOWED_HOSTS=(str, "localhost,127.0.0.1"),
    TIME_ZONE=(str, "America/Sao_Paulo"),
    CSRF_TRUSTED_ORIGINS=(str, ""),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),

    DEFAULT_MORNING_TIME=(str, "09:00"),
    DEFAULT_EVENING_TIME=(str, "18:00"),
    DEFAULT_MONTHLY_LIMIT=(int, 2),

    COUNT_EXTRA_IN_LAST_SERVED = (bool, False),
    SUGGEST_FOR_EXTRA =(bool, False),

    POSTGRES_DB=(str, "sound_schedule"),
    POSTGRES_USER=(str, "sound_user"),
    POSTGRES_PASSWORD=(str, "sound_pass"),
    POSTGRES_HOST=(str, "db"),
    POSTGRES_PORT=(int, 5432),

    REDIS_URL=(str, "redis://redis:6379/0"),
    SCHEDULE_GENERATION_DAY=(int, 25),
    SCHEDULE_GENERATION_HOUR=(int, 12),

    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, ""),
    EMAIL_PORT=(int, 587),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    EMAIL_USE_TLS=(bool, True),
    DEFAULT_FROM_EMAIL=(str, "noreply@example.com"),
)
environ.Env.read_env(os.path.join(BASE_DIR.parent, ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS").split(",")]

CSRF_TRUSTED_ORIGINS = [h.strip() for h in env("CSRF_TRUSTED_ORIGINS").split(",") if h.strip()]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "scheduling",
    "widget_tweaks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core.middleware.StrictSlashRedirectMiddleware", # custom middleware to enforce trailing slashes
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "core.middleware.ErrorLoggingMiddleware",  # custom middleware to log errors
    "core.middleware.CurrentUserMiddleware", # custom middleware to track current user
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.LoginRequiredMiddleware", # custom middleware to enforce login
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "scheduling" / "ui" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "builtins": ["scheduling.templatetags.stringx"],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
    }
}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"]
}

DEFAULT_MORNING_TIME = env("DEFAULT_MORNING_TIME")
DEFAULT_EVENING_TIME = env("DEFAULT_EVENING_TIME")
DEFAULT_MONTHLY_LIMIT = env("DEFAULT_MONTHLY_LIMIT")
SCHEDULE_GENERATION_DAY = env("SCHEDULE_GENERATION_DAY")
SCHEDULE_GENERATION_HOUR = env("SCHEDULE_GENERATION_HOUR")
COUNT_EXTRA_IN_LAST_SERVED = env("COUNT_EXTRA_IN_LAST_SERVED")
SUGGEST_FOR_EXTRA = env("SUGGEST_FOR_EXTRA")

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "monthly-draft": {
        "task": "scheduling.tasks.monthly_draft_generation",
        "schedule": crontab(minute=0, hour=SCHEDULE_GENERATION_HOUR, day_of_month=SCHEDULE_GENERATION_DAY),
    },

    "daily-reminder": {
        "task": "scheduling.tasks.daily_reminder",
        "schedule": crontab(minute=0, hour=8),
    },
}

EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="escala@igreja.local")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "rotating_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "app.log",
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
            "formatter": "detailed",
        }
    },
    "loggers": {
        "scheduling": {"handlers": ["console", "rotating_file"], "level": "INFO"},

        "django": {"handlers": ["console", "rotating_file"], "level": "INFO", "propagate": True},
        "django.request": {"handlers": ["console", "rotating_file"], "level": "ERROR", "propagate": False},
        "gunicorn.error": {"handlers": ["console", "rotating_file"], "level": "INFO", "propagate": False},
    },
}

# ==== Auth settings ====
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

LOGIN_EXEMPT_PREFIXES = (
    "/accounts/login/",
    "/accounts/logout/",
    "/admin/login/",
    "/api/auth/",
    "/static/",
    "/favicon.ico",
    "/favicon.png",
)

APPEND_SLASH = True

LANGUAGES = [
    ('en', 'English'),
    ('pt-br', 'Português (Brasil)'),
    ('es', 'Español (España)'),
    ('fr', 'Français (France)'),
    ('de', 'Deutsch (Deutschland)'),
    ('it', 'Italiano (Italia)'),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]
