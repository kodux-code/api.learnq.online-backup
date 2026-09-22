from celery.schedules import crontab
import environ
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_file):
    environ.Env.read_env(env_file)

SECRET_KEY = env('SECRET_KEY')

DEBUG = env('DEBUG')

ALLOWED_HOSTS = ["learnq.online", "192.168.1.70", "127.0.0.1", "localhost"]

CORS_ALLOWED_ORIGINS = [
    "https://learnq.online",
    "https://www.learnq.online",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.1.70:3000"
]

DEFAULT_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

CUSTOM_APPS = [
    'client.apps.ClientConfig',
    'auth.apps.CustomAuthConfig',
    'account.apps.AccountConfig',
    'question.apps.QuestionConfig',
    'message.apps.MessageConfig',
    'video.apps.VideoConfig',
    'course.apps.CourseConfig',
    'blog.apps.BlogConfig',
    'assessment.apps.AssessmentConfig',
    'certificate.apps.CertificateConfig',
    'earning.apps.EarningConfig',
    'notification.apps.NotificationConfig',
    'payment.apps.PaymentConfig',
    'transaction.apps.TransactionConfig',
    'analytic.apps.AnalyticConfig',
]

PLUGINS = [
    'daphne',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'channels',
    'django_filters',
    'django_redis',
]

INSTALLED_APPS = PLUGINS + DEFAULT_APPS + CUSTOM_APPS

ASGI_APPLICATION = "settings.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': None,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'registration': '5/hour',
    }
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
}

MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": env('EMAIL_HOST'),
                "port": env('EMAIL_PORT', cast=int),
                "username": env('EMAIL_HOST_USER'),
                "password": env('EMAIL_HOST_PASSWORD'),
                "use_tls": env('EMAIL_USE_TLS', cast=bool),
            },
        }
    }
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')
# EMAIL_FRONTEND_URL = env('EMAIL_FRONTEND_URL', default='https://learnq.online')
EMAIL_FRONTEND_URL = env('EMAIL_FRONTEND_URL', default='http://localhost:3000')
REFRESH_COOKIE_DOMAIN = ".learnq.online"

LIVEKIT_API_KEY = env('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = env('LIVEKIT_API_SECRET')
LIVEKIT_WS_URL = env('LIVEKIT_WS_URL')

VAPID_PRIVATE_KEY = env('VAPID_PRIVATE_KEY')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

ROOT_URLCONF = 'settings.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'settings.wsgi.application'


# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': env('DB_NAME'),
#         'USER': env('DB_USER'),
#         'PASSWORD': env('DB_PASS'),
#         'HOST': 'localhost',
#         'PORT': '5432',
#         'OPTIONS': {
#             'options': '-c timezone=UTC'
#         }
#     }
# }
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'

STATIC_ROOT = BASE_DIR / 'static'

AUTH_USER_MODEL = "client.Client"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "learnq",
    },
}

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://127.0.0.1:6379/0",
)

CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "Europe/London"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_SOFT_TIME_LIMIT = 45
CELERY_TASK_TIME_LIMIT = 60


WEASYPRINT_BASE_URL = 'https://learnq.online'
# Schedule periodic tasks
CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-certificates': {
        'task': 'certificate.tasks.cleanup_expired_certificates',
        'schedule': crontab(hour=2, minute=0),
    },
}