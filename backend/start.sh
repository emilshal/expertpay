#!/usr/bin/env sh
set -eu

PORT="${PORT:-8000}"

echo "Starting ExpertPay backend on port ${PORT}"
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --access-logfile - \
  --error-logfile -
