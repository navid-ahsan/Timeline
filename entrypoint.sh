#!/bin/sh
set -e

echo ">>> Running Django migrations..."
python manage.py migrate --noinput

echo ">>> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo ">>> Starting Gunicorn..."
exec gunicorn timeline_project.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile -
