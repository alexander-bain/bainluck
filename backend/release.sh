#!/bin/bash
set -e

echo "=== Release Phase Diagnostics ==="
echo "Python: $(python --version 2>&1)"
echo "Working directory: $(pwd)"
echo "Contents: $(ls -la)"
echo ""

echo "=== Checking dependencies ==="
python -c "import alembic; print(f'alembic: {alembic.__version__}')" 2>&1 || echo "FAILED: alembic import"
python -c "import psycopg2; print(f'psycopg2: {psycopg2.__version__}')" 2>&1 || echo "FAILED: psycopg2 import"
python -c "import sqlalchemy; print(f'sqlalchemy: {sqlalchemy.__version__}')" 2>&1 || echo "FAILED: sqlalchemy import"
echo ""

echo "=== Checking DATABASE_URL ==="
python -c "
import os
url = os.getenv('DATABASE_URL', 'NOT SET')
if url == 'NOT SET':
    print('DATABASE_URL is NOT SET!')
else:
    # Print scheme and host only (hide credentials)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    print(f'Scheme: {parsed.scheme}')
    print(f'Host: {parsed.hostname}')
    print(f'Port: {parsed.port}')
    print(f'DB: {parsed.path}')
" 2>&1
echo ""

echo "=== Checking alembic.ini ==="
if [ -f alembic.ini ]; then
    echo "alembic.ini found"
else
    echo "ERROR: alembic.ini NOT found!"
    ls -la *.ini 2>/dev/null || echo "No .ini files in $(pwd)"
fi
echo ""

echo "=== Testing database connection ==="
python -c "
import os
from sqlalchemy import create_engine, text

url = os.getenv('DATABASE_URL', '')
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)
if '+asyncpg' in url:
    url = url.replace('+asyncpg', '', 1)

connect_args = {}
if 'localhost' not in url and '127.0.0.1' not in url:
    connect_args['sslmode'] = 'require'

print(f'Connecting with URL scheme: {url.split(\"://\")[0]}://')
engine = create_engine(url, connect_args=connect_args)
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print(f'Database connection: OK')
    result = conn.execute(text(\"SELECT version_num FROM alembic_version\"))
    rows = result.fetchall()
    print(f'Current alembic version: {rows}')
engine.dispose()
" 2>&1 || echo "FAILED: database connection test"
echo ""

echo "=== Running alembic upgrade head ==="
alembic upgrade head 2>&1
echo "=== Release phase complete ==="
