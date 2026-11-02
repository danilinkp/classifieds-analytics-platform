import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DATABASE_URI"]

BABEL_DEFAULT_LOCALE = "ru"
LANGUAGES = {
    "ru": {"flag": "ru", "name": "Русский"},
    "en": {"flag": "us", "name": "English"},
}

FEATURE_FLAGS = {
    "DASHBOARD_CROSS_FILTERS": True,
    "ENABLE_TEMPLATE_PROCESSING": True,
}

# Local demo stack served over plain HTTP: HTTPS-only headers would break the UI.
TALISMAN_ENABLED = False
SESSION_COOKIE_SECURE = False

ROW_LIMIT = 50_000
SUPERSET_WEBSERVER_TIMEOUT = 120
