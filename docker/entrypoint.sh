#!/usr/bin/env bash
set -e

# Wait for MySQL using the same driver Django uses, so a pass proves a real
# connection (not just an open port).
echo "Waiting for MySQL at ${MYSQL_HOST:-db}:${MYSQL_PORT:-3306}..."
until python -c "
import os, MySQLdb
MySQLdb.connect(
    host=os.environ.get('MYSQL_HOST', 'db'),
    port=int(os.environ.get('MYSQL_PORT', '3306')),
    user=os.environ.get('MYSQL_USER', 'surveillance'),
    passwd=os.environ.get('MYSQL_PASSWORD', 'surveillance'),
    db=os.environ.get('MYSQL_DATABASE', 'surveillance'),
).close()
" 2>/dev/null; do
  sleep 2
done
echo "MySQL is up."

python manage.py migrate --noinput
python manage.py load_data
python manage.py collectstatic --noinput

echo "Starting server on 0.0.0.0:8000"
exec python manage.py runserver 0.0.0.0:8000
