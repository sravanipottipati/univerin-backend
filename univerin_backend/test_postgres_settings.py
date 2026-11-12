"""
Isolated local PostgreSQL settings for account deletion testing.

Never use with Railway or production.
"""

from .test_settings import *

LOCAL_DB_NAME = "univerin_deletion_isolated"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": LOCAL_DB_NAME,
        "USER": "sravanipottipati",
        "PASSWORD": "",
        "HOST": "127.0.0.1",
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "TEST": {
            "NAME": "test_univerin_deletion_isolated",
        },
    }
}

TESTING_ACCOUNT_DELETION_CLEANUP = True
