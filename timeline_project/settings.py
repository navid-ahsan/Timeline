import os
import sys
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# LangGraph modules live in src/
sys.path.insert(0, str(BASE_DIR / "src"))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-change-in-production")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.patients",
    "apps.laws",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "timeline_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "front"],
        "APP_DIRS": False,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "timeline_project.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="postgresql://ls_user:change_this_password@postgres:5432/lastensuojelu_db",
        conn_max_age=60,
    )
}

# Static files — front/ directory is served as-is
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "front"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media — uploaded patient documents
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "data" / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

# LangSmith tracing (set in .env to activate)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=your_key
# LANGCHAIN_PROJECT=lastensuojelu-timeline

LANGCHAIN_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ls_user:change_this_password@postgres:5432/lastensuojelu_db",
)
