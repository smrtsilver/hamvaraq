"""
تنظیمات پروژه‌ی هم‌ورق (HamVaraqDjangoServer).
"""

import sys
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

IS_TEST = "test" in sys.argv

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

_INSECURE_KEY = "django-insecure-hamvaraq-dev-key-change-me"
SECRET_KEY = env("SECRET_KEY", default=_INSECURE_KEY)
DEBUG = env.bool("DEBUG", default=True)

# با DEBUG=False و کلید پیش‌فرض سرور بالا نمیاد
if not DEBUG and SECRET_KEY == _INSECURE_KEY:
    raise ImproperlyConfigured("SECRET_KEY واقعی رو تو .env پروداکشن ست کن.")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_HTTPONLY = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

if not DEBUG:
    # تا وقتی nginx+SSL نداری USE_HTTPS=False بذار
    USE_HTTPS = env.bool("USE_HTTPS", default=True)
    if USE_HTTPS:
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        SECURE_SSL_REDIRECT = True
        SECURE_HSTS_SECONDS = 31536000
    SESSION_COOKIE_SECURE = USE_HTTPS
    CSRF_COOKIE_SECURE = USE_HTTPS

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "common",
    "accounts",
    "books",
    "exchanges",
    "trust",
    "notifications",
    "challenges",
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
    "common.seo.RobotsHeaderMiddleware",
]

ROOT_URLCONF = "HamVaraqDjangoServer.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            # فیلترهای فارسی (fa, jdate, jtime, ago…) تو همه‌ی قالب‌ها بدون load در دسترسن
            "builtins": ["common.templatetags.persian"],
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.notifications",
                "exchanges.context_processors.unread_chat",
            ],
        },
    },
]

WSGI_APPLICATION = "HamVaraqDjangoServer.wsgi.application"

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

# پیش‌فرض SQLite؛ برای Postgres فقط DATABASE_URL رو تو .env بذار
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

if IS_TEST:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ایمیل فقط برای بازیابی رمزه؛ تا SMTP ست نشده تو کنسول چاپ می‌شه
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="hamvaraq <noreply@hamvaraq.ir>")

# کش مشترک بین worker ها (شمارنده‌ی محدودیت نرخ + کش شابک). جدولش: manage.py createcachetable
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "hv_cache",
    }
}

# محدودیت نرخ. پشت nginx (X-Real-IP) باید TRUST_PROXY_HEADERS=True باشه
THROTTLE_ENABLED = env.bool("THROTTLE_ENABLED", default=True)
TRUST_PROXY_HEADERS = env.bool("TRUST_PROXY_HEADERS", default=False)

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if IS_TEST or DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# آدرسی که روی کارت اشتراک‌گذاری چاپ می‌شه
SITE_URL = env("SITE_URL", default="hamvaraq.ir")

# گزارش روزانه (manage.py daily_report --email) به این ایمیل‌ها می‌ره
ADMIN_EMAILS = env.list("ADMIN_EMAILS", default=[])

# بکاپ (manage.py backup_db)
BACKUP_DIR = env("BACKUP_DIR", default=str(BASE_DIR / "backups"))
BACKUP_KEEP = env.int("BACKUP_KEEP", default=14)

# لاگ تو خروجی استاندارد (docker logs). خطاهای ۵۰۰ و هشدارها همین‌جا میان.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "[{asctime}] {levelname} {name} — {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django.request": {"level": "WARNING"}},
}

# گزارش خطا به Sentry؛ فقط اگه SENTRY_DSN ست باشه و کتابخونه نصب باشه. اطلاعات شخصی (PII) نمی‌ره.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN and not IS_TEST:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="production" if not DEBUG else "development"),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
    )

# ---- قوانین دامنه‌ی هم‌ورق ----
VOTE_EDIT_HOURS = 24            # رأی تا این مدت قابل ویرایشه
LOW_REPUTATION_PERCENT = 60     # زیر این درصد (با حداقل رأی) هشدار «اعتبار پایین»
LOW_REPUTATION_MIN_VOTES = 5
MUTUAL_PAIR_FREE_LIMIT = 2      # بیشتر از این تعداد مبادله‌ی دو نفره، وزن رأی نصف می‌شه
NO_SHOW_REPORTS_FOR_RESTRICTION = 3
RESTRICTION_DAYS = 14
BADGE_COURIER_EXCHANGES = 10
BADGE_NEIGHBORHOOD_BOOKS = 5
STALE_REQUEST_DAYS = 3      # درخواست بی‌پاسخ بعد از این مدت تو داشبورد «گیرکرده» حساب می‌شه
STALE_ACCEPTED_DAYS = 7     # مبادله‌ی تأییدشده‌ی تموم‌نشده

# ---- چرخه‌ی عمر مبادله (python manage.py expire_exchanges؛ روزانه تو cron) ----
# عددها «روز» هستن. یادآوری‌ها بعد از این روزها، به ترتیب، فرستاده می‌شن.
REQUEST_REMIND_DAYS = [3]           # به صاحب کتابِ بی‌پاسخ
REQUEST_EXPIRE_DAYS = 7             # درخواست بی‌پاسخ لغو و امتیاز برگردونده می‌شه
ACCEPTED_REMIND_DAYS = [7, 14]      # به هر دو طرفِ مبادله‌ی تأییدشده‌ی بی‌حرکت
ACCEPTED_EXPIRE_DAYS = 21           # هیچ‌کس تحویل رو تأیید نکرده ← لغو و برگشت امتیاز
CONFIRM_REMIND_DAYS = [3]           # یه نفر تحویل رو تأیید کرده، نفر دوم نه
CONFIRM_DISPUTE_DAYS = 7            # بعدش خودکار اختلاف باز می‌شه و ادمین تصمیم می‌گیره
