"""
DataFlow Agent — Django Settings

Para desenvolvimento local (sem .env):
  - Usa SQLite automáticamente
  - SECRET_KEY gerado automaticamente
  - Ollama usa localhost:11434

Para produção: crie um .env com as variáveis necessárias
"""
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ──────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────
# Gera chave automaticamente se não existir (dev only)
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
# DEBUG — lido do ambiente, False em produção
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = ["*"]
# hostname interno do Docker — necessário quando o proxy Vite usa changeOrigin: true
# if "backend" not in ALLOWED_HOSTS:
#    ALLOWED_HOSTS.append("backend")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────
# Apps
# ──────────────────────────────────────────────
INSTALLED_APPS = [
    "daphne",  # deve ficar antes do staticfiles para patch do runserver
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "django_celery_results",
    "django_celery_beat",
    "channels",
    # Local
    "dataflow",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────
# Se DB_ENGINE=postgresql usa PostgreSQL, senão usa SQLite (dev)
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite")

if DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "dataflow_agent"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    # SQLite para desenvolvimento local
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Celery

# ──────────────────────────────────────────────
# Celery
# ──────────────────────────────────────────────
# Usa Redis se USE_REDIS=True, senão usa broker locmem (dev sem Redis)
if USE_REDIS:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
else:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "memory://")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TRACK_STARTED = True

# ──────────────────────────────────────────────
# REST Framework
# ──────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ──────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    *os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5101",
    ).split(","),
]

# ──────────────────────────────────────────────
# Anthropic
# ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_MOCK = os.getenv("AGENT_MOCK", "True").lower() == "true"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", default="claude-sonnet-4-20250514")

# Custo por milhão de tokens (claude-sonnet-4-x — preços em USD)
# Blended = estimativa 80% input + 20% output
ANTHROPIC_INPUT_COST_PER_M = float(os.getenv("ANTHROPIC_INPUT_COST_PER_M", default=3.0))
ANTHROPIC_OUTPUT_COST_PER_M = float(os.getenv("ANTHROPIC_OUTPUT_COST_PER_M", default=15.0))
ANTHROPIC_BLENDED_COST_PER_M = (
        ANTHROPIC_INPUT_COST_PER_M * 0.8 + ANTHROPIC_OUTPUT_COST_PER_M * 0.2
)  # ≈ 5.40 USD/M

# ──────────────────────────────────────────────
# Django Channels
# ──────────────────────────────────────────────
USE_REDIS = os.getenv("USE_REDIS", "True").lower() == "true"

if USE_REDIS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1")]},
        }
    }
else:
    # In-memory channel layer para desenvolvimento sem Redis
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# ──────────────────────────────────────────────
# DuckDB
# ──────────────────────────────────────────────
DUCKDB_PATH = os.getenv("DUCKDB_PATH", default=str(BASE_DIR / "analytics.duckdb"))

# ──────────────────────────────────────────────
# Static / Templates
# ──────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ──────────────────────────────────────────────
# Upload limits
# ──────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

AGENT_TIMEOUT = os.getenv("AGENT_TIMEOUT", 180)
AGENT_MAX_ITERATIONS = os.getenv("AGENT_MAX_ITERATIONS", 15)
AGENT_MAX_DECISIONS = os.getenv("AGENT_MAX_DECISIONS", 100)
AGENT_MAX_DATA_CHARS = os.getenv("AGENT_MAX_DATA_CHARS", 5000)
AGENT_RETRY_ATTEMPTS = os.getenv("AGENT_RETRY_ATTEMPTS", 3)

AGENT_RETRY_BACKOFF = os.getenv("AGENT_RETRY_BACKOFF", 2.0)
