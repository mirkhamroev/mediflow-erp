import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('mediflow-erp')
app.config_from_object('django.conf:settings', namespace='CELERY')

# This searches for tasks.py files in all installed Django apps
app.autodiscover_tasks()