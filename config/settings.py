"""
Django settings for config project.

Production-grade configuration with Supabase PostgreSQL, Supabase Storage,
and OpenAPI 3.0 / Swagger documentation via drf-spectacular.
"""

import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
import dj_database_url
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-8m%*0@6a9l&(t^^_0jg3vn(s#8r23%k^pnt%sd^_t3h_)gn^l$",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "drf_spectacular",
    # Local apps
    "tasks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


import sys

# Database - Supabase PostgreSQL Connection
raw_database_url = os.getenv("DATABASE_URL", "").strip()
if raw_database_url.startswith("postgresql+psycopg2://"):
    raw_database_url = raw_database_url.replace("postgresql+psycopg2://", "postgresql://", 1)

if not raw_database_url and "test" not in sys.argv:
    raise ImproperlyConfigured(
        "DATABASE_URL is not set in environment variables. "
        "Supabase connection string is required."
    )

if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    DATABASES = {
        "default": dj_database_url.parse(
            raw_database_url,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }



# Supabase Storage configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
).strip()
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "results").strip()


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# REST Framework & Swagger OpenAPI Configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Adapt.io Lead Generation & Verification API",
    "DESCRIPTION": (
        "High-performance backend API for automated B2B lead scraping from Adapt.io, "
        "intelligent email permutations generation, MailTester verification, "
        "and secure cloud artifact storage via Supabase."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "filter": True,
    },
    "COMPONENT_SPLIT_REQUEST": True,
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"