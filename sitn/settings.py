import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('.env', override=True)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEVELOPMENT_MODE = False

IS_INTRANET = True if os.environ.get("IS_INTRANET") == "True" else False

if 'DEVELOPMENT_MODE' in os.environ and os.environ['DEVELOPMENT_MODE'] == "True":
    DEVELOPMENT_MODE = True
    GDAL_PATH = os.environ.get('GDAL_PATH')
    GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH')
    GEOS_LIBRARY_PATH = os.environ.get('GEOS_LIBRARY_PATH')
else:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'
    if IS_INTRANET:
        # Allows cross origin cookies for PEGGI trying to reach secured sitnintra endpoints
        # Only in production otherwise cookies will not be set on localhost because not HTTPS
        CSRF_COOKIE_SAMESITE = 'None'
        SESSION_COOKIE_SAMESITE = 'None'
        CORS_ALLOW_CREDENTIALS = True

DEBUG = DEVELOPMENT_MODE

# Application definition

# List of apps that must not be visible on internet
INTRANET_ONLY_APPS = [
    'cats',
    'parcel_historisation',
    'intranet_proxy',
    'ecap_intra'
]

INTERNET_ONLY_APPS = [
    'action_sociale',
    'ecap',
    'forest_forpriv',
    'health',
    'stationnement',
    'ppe',
]

INSTALLED_APPS = [
    'sitn',
    'roads',
    'cadastre',
    'panoview',
    "corsheaders",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "django.contrib.gis",
    "django_extended_ol",
    'registre_foncier',
    'rest_framework',
    'rest_framework_gis',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'django_dotnetid',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.openid_connect',
]

if IS_INTRANET:
    INSTALLED_APPS = INTRANET_ONLY_APPS + INSTALLED_APPS
else:
    INSTALLED_APPS = INTERNET_ONLY_APPS + INSTALLED_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware'
]

AUTHENTICATION_BACKENDS = [
    'allauth.account.auth_backends.AuthenticationBackend',
]

SERIALIZATION_MODULES = {
    "geojson": "django.contrib.gis.serializers.geojson", 
 }

ROOT_URLCONF = 'sitn.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'sitn/templates'
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ["PGDATABASE"],
        'USER': os.environ["PGUSER"],
        'HOST': os.environ["PGHOST"],
        'PORT': os.environ["PGPORT"],
        'PASSWORD': os.environ["PGPASSWORD"],
        'OPTIONS': {
            'options': '-c search_path=' + os.environ["PGSCHEMA"] + ',ppe,public'
        },
    },
    'terris': {
        'ENGINE': 'django.db.backends.oracle',
        'NAME': os.environ["TERRIS_HOST"] + ':' + os.environ["TERRIS_PORT"] + '/' + os.environ["TERRIS_SERVICE"],
        'USER': os.environ["TERRIS_USER"],
        'PASSWORD': os.environ["TERRIS_PASSWORD"],
        'TEST': {
            # prevents the creation of a test database
            'MIRROR': 'terris',
        },
    },
}

DATABASE_ROUTERS = [
    "sitn.database_router.TerrisRouter",
]

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'fr-ch'

TIME_ZONE = 'Europe/Zurich'

USE_I18N = True

USE_TZ = True

# CORS, CSRF AND SSL

ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(",")

CORS_DEV_ORIGINS = [
    "http://localhost:4200",
    "http://localhost:4300",
    "https://localhost:4200",
    "https://localhost:4300",
    "http://localhost:5173"
]

CORS_ALLOWED_ORIGINS = CORS_DEV_ORIGINS + list(map(str.rstrip, os.environ["CORS_ALLOWED_ORIGINS"].split(",")))

CSRF_USE_SESSIONS = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_DOMAIN = os.environ["CSRF_COOKIE_DOMAIN"]
CSRF_TRUSTED_ORIGINS = []
for host in CORS_ALLOWED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(host)

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

FORCE_SCRIPT_NAME = os.environ.get('ROOTURL', '')

STATIC_URL = FORCE_SCRIPT_NAME + '/assets/'

STATIC_ROOT = os.path.join(BASE_DIR, 'assets')

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

WHITENOISE_STATIC_PREFIX = "/assets/"

DOWNLOAD_ROOT = "/data/"
MEDIA_ROOT = "/upload/"
MEDIA_URL = os.environ.get('MEDIA_URL', 'upload/')

DEFAULT_FROM_EMAIL = 'no-reply@ne.ch'

ACTIVATE_MAILING_IN_DEV_MODE = os.environ.get('DEV_MAIL_ON', False)
if DEVELOPMENT_MODE:
    if ACTIVATE_MAILING_IN_DEV_MODE:
        DEFAULT_FROM_EMAIL='no-reply-ppe@ne.ch'
        EMAIL_HOST='smtp.ne.ch'
    else: 
        EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
        EMAIL_FILE_PATH = BASE_DIR / "emails_sent"
else:
    EMAIL_HOST = os.environ["EMAIL_HOST"]


NEARCH2_CONSULTATION = os.environ.get('NEARCH2_CONSULTATION')

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {module} {filename} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOGGING_LEVEL', 'ERROR'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('LOGGING_LEVEL', 'ERROR'),
            'propagate': False,
        },
        # Unncomment this for SQL logs
        #"django.db.backends": {
        #    "handlers": ["console"],
        #    "level": "DEBUG",
        #},
    },
}

INTRANET_PROXY = {
    'geoshop_user': os.getenv('GEOSHOP_USER', ''),
    'geoshop_password': os.getenv('GEOSHOP_PASSWORD', ''),
    'geoshop_url': os.getenv('GEOSHOP_URL', 'https://sitn.ne.ch/geoshop2_api/'),
    'test_url': 'metadata/at701_potentiel_sda',
    'vcron_url': os.getenv('VCRON_URL'),
    'vcron_user': os.getenv('VCRON_USER'),
    'vcron_password': os.getenv('VCRON_PASSWORD'),
    'infolica_api_url': os.getenv('INFOLICA_API_URL'),
}

HEALTH = {
    'front_url': os.getenv('DOCTORS_URL', 'http://localhost:5173/edit/')
}

# Be aware that by changing the PAGE_SIZE parameter, you will have to
# adjust the client page pagination parameter (limit) as well, like as in 
# parcel_historisation\static\parcel_historisation\parcel_historisation.js
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'PAGE_SIZE': 20
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Sitn REST API',
    'DESCRIPTION': 'Home of SITN REST Services',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

DEFAULT_SRID = 2056


OLWIDGET = {
    "globals": {
        "srid": 2056,
        "default_center": [2551470, 1211190], # optional
        "default_resolution": 18, # optional
        "extent": [2420000, 1030000, 2900000, 1360000],
        "resolutions": [250, 100, 50, 20, 10, 5, 2.5, 2, 1.5, 1, 0.5, 0.25, 0.125, 0.0625]
    },
    "wmts": {
        "layer_name": 'plan_cadastral',
        "style": 'default',
        "matrix_set": 'EPSG2056',
        "attributions": '<a target="new" href="https://sitn.ne.ch/web/conditions_utilisation/contrat_SITN_MO.htm'
            + '">© SITN</a>', # optional
        "url_template": 'https://sitn.ne.ch/mapproxy95/wmts/1.0.0/{layer}/{style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png',
        "request_encoding": 'REST', # optional
        "format": 'image/png' # optional
    },
    "search": {
        "url_template": 'https://sitn.ne.ch/search?limit=10&partitionlimit=2&interface=desktop&query={search_term}'
    }
}

SOCIALACCOUNT_PROVIDERS = {
    'dotnetidprovider': {
        'APP': {
            'provider_id': 'dotnetid',
            'name': 'Etat de Neuchâtel',
            'client_id': os.environ['DOTNETID_CLIENT_ID'],
            'secret': os.environ['DOTNETID_CLIENT_SECRET'],
            'settings': {
                'server_url': os.environ['DOTNETID_SERVER_URL'],
            },
        },
        'SCOPE': [
            'profile',
            'openid',
            'glados',
        ],
        'EXTRA_ATTRIBUTES_PREFIX': os.environ['DOTNETID_EXTRA_ATTRIBUTES_PREFIX'],
        'EXTRA_ATTRIBUTES_NAMES': [
            'groups',
            'admin',
        ],
        'OAUTH_PKCE_ENABLED': True,
        'ID_TOKEN_ISSUER': os.environ['DOTNETID_SERVER_URL'],
    }
}
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_ADAPTER  = 'django_dotnetid.adapter.DotnetIdAccountAdapter'
SOCIALACCOUNT_ONLY = True
LOGIN_URL = f"{FORCE_SCRIPT_NAME}/accounts/login/" if FORCE_SCRIPT_NAME else "index"
LOGIN_REDIRECT_URL = FORCE_SCRIPT_NAME if FORCE_SCRIPT_NAME else "index"
LOGOUT_REDIRECT_URL = FORCE_SCRIPT_NAME if FORCE_SCRIPT_NAME else "index"
SITE_ID = 1
