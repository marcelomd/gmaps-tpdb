"""
Production settings for tpdb project.
"""

import copy
import os
from .settings import *

DEBUG = False

DOMAIN_NAME = os.environ["DOMAIN_NAME"]
# Login links are built from this, never from the request's Host header
SITE_URL = f"https://{DOMAIN_NAME}"

# localhost is for the deploy health check, which talks to the gunicorn socket directly
ALLOWED_HOSTS = [DOMAIN_NAME, "localhost", "127.0.0.1"]

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

LOGGING = copy.deepcopy(LOGGING)
LOGGING["handlers"]["file"] = {
    "level": "INFO",
    "class": "logging.FileHandler",
    "filename": "/var/log/tpdb/tpdb.log",
    "formatter": "verbose",
}
LOGGING["root"]["handlers"].append("file")
LOGGING["loggers"]["django"]["handlers"].append("file")
