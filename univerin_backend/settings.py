from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ['SECRET_KEY']
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

CSRF_TRUSTED_ORIGINS = [
    'https://api.univerin.in',
    'https://univerin.in',
    'https://*.up.railway.app',
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
ALLOWED_HOSTS = [
    'api.univerin.in',
    'web-production-a8b49.up.railway.app',
    'localhost',
    '127.0.0.1',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'cloudinary_storage',        # ← ADDED (must be before staticfiles)
    'django.contrib.staticfiles',
    'cloudinary',                # ← ADDED
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # Shop2me apps
    'users',
    'vendors',
    'invoices',
    'orders',
    'wallet',
    'delivery_partner',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'univerin_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'univerin_backend.wsgi.application'

import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ["DATABASE_URL"]
    )
}

# Dedicated local test database
if os.environ.get("UNIVERIN_TEST_DB") == "1":
    DATABASES["default"]["TEST"] = {
        "NAME": "univerin_deletion_test_20261115",
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "https://univerin.in",
    "https://www.univerin.in",
    "http://localhost:3000",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:19006",
    "http://127.0.0.1:19006",
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'users.authentication.ActiveAccountJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'UNAUTHENTICATED_USER': None,
}

# JWT Settings
SIMPLE_JWT = {
    "TOKEN_REFRESH_SERIALIZER": "users.token_refresh.ActiveAccountTokenRefreshSerializer",
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=60),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Media Files (local fallback)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ─── Cloudinary Settings ──────────────────────────────────────────────────────
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Cloudinary supports CLOUDINARY_URL (Railway) or separate environment variables.
from urllib.parse import urlparse, unquote

cloudinary_url = os.environ.get("CLOUDINARY_URL")

if cloudinary_url:
    parsed = urlparse(cloudinary_url)
    if parsed.scheme != "cloudinary" or not all(
        [parsed.username, parsed.password, parsed.hostname]
    ):
        raise ValueError("Invalid CLOUDINARY_URL configuration")

    cloudinary_credentials = {
        "CLOUD_NAME": parsed.hostname,
        "API_KEY": unquote(parsed.username),
        "API_SECRET": unquote(parsed.password),
    }
else:
    cloudinary_credentials = {
        "CLOUD_NAME": os.environ["CLOUDINARY_CLOUD_NAME"],
        "API_KEY": os.environ["CLOUDINARY_API_KEY"],
        "API_SECRET": os.environ["CLOUDINARY_API_SECRET"],
    }

CLOUDINARY_STORAGE = cloudinary_credentials

cloudinary.config(
    cloud_name=CLOUDINARY_STORAGE["CLOUD_NAME"],
    api_key=CLOUDINARY_STORAGE["API_KEY"],
    api_secret=CLOUDINARY_STORAGE["API_SECRET"],
    secure=True,
)

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# UNIVERIN HTTPS cookie security
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG


# UNIVERIN HSTS security
SECURE_HSTS_SECONDS = 0  # Enable after verifying Railway HTTPS proxy configuration
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


# Shared database-backed cache for authentication throttling.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'univerin_login_cache',
        'TIMEOUT': 900,
    }
}

# Account deletion: Cloudinary read-only verification.
# Disabled by default. No storage deletion is enabled by this flag.
ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED = (
    os.environ.get(
        "ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED",
        "false",
    ).lower() in ("1", "true", "yes")
)

# Automatic account deletion worker.
# Disabled by default. Enabling this flag alone does not execute deletions.
# The worker must independently enforce authorization and safety checks.
ACCOUNT_DELETION_AUTOMATIC_ENABLED = (
    os.environ.get("ACCOUNT_DELETION_AUTOMATIC_ENABLED", "False") == "True"
)


# Explicit production authorization for the automatic deletion worker.
# Keep False until production rollout is approved.
ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED = (
    os.environ.get(
        "ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED",
        "False",
    ) == "True"
)


# Railway environment verification for automatic account deletion.
ACCOUNT_DELETION_RAILWAY_ENVIRONMENT = os.environ.get(
    "RAILWAY_ENVIRONMENT_NAME", ""
)
