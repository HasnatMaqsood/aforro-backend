import os
from celery import Celery

# Tell Celery where Django settings are
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aforro.settings")

app = Celery("aforro")

# Load config from Django settings, using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()