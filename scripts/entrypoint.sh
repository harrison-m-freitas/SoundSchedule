#!/usr/bin/env bash
set -e

python manage.py collectstatic --noinput || true
python manage.py migrate
python manage.py create_roles || true
python manage.py compilemessages || true

# Dev: runserver; Prod: use gunicorn if GUNICORN=1
if [ "${GUNICORN:-0}" = "1" ]; then
  exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3
else
  exec python manage.py runserver 0.0.0.0:8000
fi
