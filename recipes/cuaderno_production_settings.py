"""Secure deployment profile for Cuaderno behind an explicitly configured HTTPS ingress."""
import os

# AI is disabled in this profile; LiteLLM must use its bundled map during import.
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'

from recipes.settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured
import re

if DEBUG or SECRET_KEY == 'INSECURE_STANDARD_KEY_SET_IN_ENV' or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Producción exige DEBUG=0 y SECRET_KEY propia de al menos 50 caracteres.')
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Producción exige ALLOWED_HOSTS explícitos.')
if not CSRF_TRUSTED_ORIGINS or any(not origin.startswith('https://') for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured('Producción exige orígenes CSRF con HTTPS.')
if os.environ.get('PLUGINS_BUILD', '0') != '0':
    raise ImproperlyConfigured('Producción utiliza los assets verificados de la imagen: PLUGINS_BUILD debe ser 0.')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
LANGUAGE_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = True
# The documented host HTTPS proxy is the only ingress to the loopback listener.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r'^' + re.escape((FORCE_SCRIPT_NAME or '').strip('/')) + ('/' if FORCE_SCRIPT_NAME else '') + r'health/ready/$']
ENABLE_SIGNUP = False
SPACE_AI_ENABLED = False
SPACE_DEFAULT_ALLOW_SHARING = False
DISABLE_EXTERNAL_CONNECTORS = True
