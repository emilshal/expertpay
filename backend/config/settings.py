"""Django settings for ExpertPay backend."""

from datetime import timedelta
import os
import sys
from pathlib import Path

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-me")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


# Application definition

INSTALLED_APPS = [
    "corsheaders",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "rest_framework",
    "accounts",
    "ledger",
    "payments",
    "integrations",
    "audit",
    "wallet",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.getenv("DB_NAME", "expertpay"),
        "USER": os.getenv("DB_USER", "expertpay"),
        "PASSWORD": os.getenv("DB_PASSWORD", "expertpay"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5433"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Tbilisi")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("THROTTLE_ANON", "120/hour"),
        "user": os.getenv("THROTTLE_USER", "1200/hour"),
        "auth_otp_request": os.getenv("THROTTLE_AUTH_OTP_REQUEST", "30/hour"),
        "auth_otp_verify": os.getenv("THROTTLE_AUTH_OTP_VERIFY", "60/hour"),
        "money_write": os.getenv("THROTTLE_MONEY_WRITE", "240/hour"),
        "money_status_write": os.getenv("THROTTLE_MONEY_STATUS_WRITE", "120/hour"),
        "yandex_write": os.getenv("THROTTLE_YANDEX_WRITE", "180/hour"),
        "yandex_read": os.getenv("THROTTLE_YANDEX_READ", "600/hour"),
    },
}

if "test" in sys.argv:
    # Keep CI tests deterministic and avoid throttle-related flakiness.
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
}

CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
CORS_ALLOW_HEADERS = [
    *default_headers,
    "x-request-id",
    "idempotency-key",
    "x-fleet-name",
]

YANDEX_ENABLED = os.getenv("YANDEX_ENABLED", "false").lower() == "true"
YANDEX_MODE = os.getenv("YANDEX_MODE", "sim").lower()
YANDEX_BASE_URL = os.getenv("YANDEX_BASE_URL", "https://fleet-api.taxi.yandex.net").rstrip("/")
YANDEX_PARK_ID = os.getenv("YANDEX_PARK_ID", "").strip()
YANDEX_CLIENT_ID = os.getenv("YANDEX_CLIENT_ID", "").strip()
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "").strip()
YANDEX_REQUEST_TIMEOUT_SECONDS = int(os.getenv("YANDEX_REQUEST_TIMEOUT_SECONDS", "20"))
YANDEX_MAX_RETRIES = int(os.getenv("YANDEX_MAX_RETRIES", "3"))
YANDEX_RETRY_BASE_SECONDS = float(os.getenv("YANDEX_RETRY_BASE_SECONDS", "0.5"))

BOG_ENABLED = os.getenv("BOG_ENABLED", "false").lower() == "true"
BOG_TOKEN_URL = os.getenv(
    "BOG_TOKEN_URL",
    "https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token",
).strip()
BOG_BASE_URL = os.getenv("BOG_BASE_URL", "https://api.businessonline.ge/api").rstrip("/")
BOG_CLIENT_ID = os.getenv("BOG_CLIENT_ID", "").strip()
BOG_CLIENT_SECRET = os.getenv("BOG_CLIENT_SECRET", "").strip()
BOG_SCOPE = os.getenv("BOG_SCOPE", "").strip()
BOG_REQUEST_TIMEOUT_SECONDS = int(os.getenv("BOG_REQUEST_TIMEOUT_SECONDS", "20"))
BOG_SOURCE_ACCOUNT_NUMBER = os.getenv("BOG_SOURCE_ACCOUNT_NUMBER", "").strip()
BOG_PAYER_INN = os.getenv("BOG_PAYER_INN", "").strip()
BOG_PAYER_NAME = os.getenv("BOG_PAYER_NAME", "").strip()
BOG_DOCUMENT_PREFIX = os.getenv("BOG_DOCUMENT_PREFIX", "EPW").strip() or "EPW"
BOG_DEPOSIT_REFERENCE_PREFIX = os.getenv("BOG_DEPOSIT_REFERENCE_PREFIX", "EXP").strip() or "EXP"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "integrations": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "payments": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "wallet": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "accounts": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,
        )
    except Exception:
        # Keep app boot resilient when sentry package/config is unavailable.
        pass

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
