#!/bin/sh
set -e

echo "==> Waiting for database..."
python - <<'EOF'
import os, sys, time, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.db import connection

for attempt in range(1, 31):
    try:
        connection.ensure_connection()
        print(f"    Database ready after {attempt} attempt(s).")
        sys.exit(0)
    except Exception as exc:
        print(f"    [{attempt}/30] Not ready: {exc}")
        time.sleep(1)

print("ERROR: Database did not become ready after 30 retries.")
sys.exit(1)
EOF

echo "==> Running make migrations..."
python manage.py makemigrations --noinput

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Starting application..."
exec "$@"
