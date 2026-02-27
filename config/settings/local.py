"""
local.py — Développement uniquement
Utilisation : DJANGO_SETTINGS_MODULE=config.settings.local
"""
from .base import *  # noqa
from dotenv import load_dotenv
import os

load_dotenv(BASE_DIR / ".env")  # noqa

# ── Sécurité ───────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = True
ALLOWED_HOSTS = ["*"]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# ── Base de données ────────────────────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    },
}

# ── Email (console en dev, pas besoin de serveur SMTP) ────────────────────────

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── API Keys ───────────────────────────────────────────────────────────────────

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")