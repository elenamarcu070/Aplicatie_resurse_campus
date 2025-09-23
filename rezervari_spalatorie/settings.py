import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

# Încarcă variabilele din .env (DOAR local, Railway folosește env vars direct)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------
# SECURITY
# --------------------
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-secret-key")
DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "")
if ALLOWED_HOSTS == "*":
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS.split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in CSRF_TRUSTED_ORIGINS.split(",") if o.strip()]


# --------------------
# APLICAȚII
# --------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # allauth
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    # aplicațiile tale
    "booking",  # modifică aici cu numele app-ului tău
]

SITE_ID = 1

# --------------------
# MIDDLEWARE
# --------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # pentru static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # necesar pt. allauth
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rezervari_spalatorie.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "booking.context_processors.rol_utilizator",
            ],
        },
    },
]

WSGI_APPLICATION = "rezervari_spalatorie.wsgi.application"

# --------------------
# DATABASE
# --------------------
DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True,
    )
}

# --------------------
# AUTENTIFICARE
# --------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

#ACCOUNT_LOGIN_METHODS = {"email"}
#ACCOUNT_SIGNUP_FIELDS = ["email*"]  # doar email

ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = False
ACCOUNT_EMAIL_VERIFICATION = "none"

LOGIN_REDIRECT_URL = "/callback/"
LOGOUT_REDIRECT_URL = "/"

# Nu mai cere signup separat, creează user-ul direct
SOCIALACCOUNT_AUTO_SIGNUP = True

# Folosește doar emailul, fără username
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
SOCIALACCOUNT_ADAPTER = "booking.adapters.MySocialAccountAdapter"
# --------------------
# STATIC & MEDIA
# --------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# WhiteNoise: comprimă și face cache static files
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --------------------
# EMAIL
# --------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = os.getenv("EMAIL_PORT", 587)
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

# --------------------
# LOCALE
# --------------------
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "ro")
TIME_ZONE = os.getenv("TIME_ZONE", "Europe/Bucharest")
USE_I18N = True
USE_TZ = True

# --------------------
# DEFAULT
# --------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
#SECURE_SSL_REDIRECT = True