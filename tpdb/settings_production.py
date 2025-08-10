"""
Production settings for tpdb project.
"""

import os
from .settings import *

# Security settings for production
DEBUG = False
SECRET_KEY = os.environ.get("SECRET_KEY")

# Update this with your actual domain
ALLOWED_HOSTS = [
    os.environ.get("DOMAIN_NAME"),
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]

# Database configuration for production
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "tpdb"),
        "USER": os.environ.get("DB_USER", "tpdb_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "tpdb_password"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Static files settings for production
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# Session security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "/var/log/tpdb/tpdb.log",
            "formatter": "verbose",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
