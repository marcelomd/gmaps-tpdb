#!/bin/bash

# Release steps, run by deploy.sh after it has put the new code in place.
# Kept apart from deploy.sh because bash reads a script as it runs: a step added here
# takes effect on the deploy that ships it, whereas deploy.sh is still the old copy
# until its own "git reset" has run. Failures (non-zero exit) make deploy.sh roll back.
set -x
set -e

PROJECT_DIR="/var/www/tpdb"
VENV_DIR="$PROJECT_DIR/venv"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/tpdb/deploy.log
}

cd "$PROJECT_DIR" || { log "ERROR: Cannot access project directory"; exit 1; }

# One compound command so bash parses it all before running any of it
{
# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    log "ERROR: Virtual environment not found at $VENV_DIR"
    exit 1
fi

# Activate virtual environment
log "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    log "ERROR: requirements.txt not found"
    exit 1
fi

# Install/update dependencies
log "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check Django settings
log "Checking Django configuration..."
DJANGO_SETTINGS="tpdb.settings_production"

# Run Django system check
log "Running Django system check..."
python manage.py check --settings=$DJANGO_SETTINGS

# Run database migrations
log "Running database migrations..."
python manage.py migrate --settings=$DJANGO_SETTINGS

# Collect static files
log "Collecting static files..."
python manage.py collectstatic --noinput --settings=$DJANGO_SETTINGS

# Setup/update cron job for Excel import processing
log "Setting up cron job for Excel import processing..."
CRON_JOB="* * * * * cd $PROJECT_DIR && $VENV_DIR/bin/python manage.py process_pending_imports --max-files 1 --settings=tpdb.settings_production >> /var/log/tpdb/excel_imports.log 2>&1"
(crontab -l 2>/dev/null | grep -v "process_pending_imports" || true; echo "$CRON_JOB") | crontab -

# .env holds secrets; systemd reads it as root, so only the owner needs access
log "Updating file permissions..."
chmod -R 755 $PROJECT_DIR
chmod 600 $PROJECT_DIR/.env 2>/dev/null || true
# Uploads and images are only read by gunicorn and cron (both run as $USER)
chmod 700 $PROJECT_DIR/media 2>/dev/null || true

# Test Django application
log "Testing Django application..."
if ! python manage.py check --settings=$DJANGO_SETTINGS --deploy; then
    log "WARNING: Django deployment check found issues"
fi

# Restart services
log "Restarting services..."
sudo /bin/systemctl restart tpdb

# Wait for service to start
sleep 5

# Check if services are running
if ! sudo /bin/systemctl is-active --quiet tpdb; then
    log "ERROR: tpdb service failed to start"
    sudo /bin/systemctl status tpdb
    exit 1
fi

# Test application response
log "Testing application response..."
if command -v curl &> /dev/null; then
    # Pretend to be the proxy, otherwise SECURE_SSL_REDIRECT answers 301 and no view ever runs
    if ! curl -f -s -o /dev/null -H "X-Forwarded-Proto: https" --unix-socket /var/www/tpdb/tpdb.sock http://localhost/; then
        log "WARNING: Application health check failed"
    else
        log "Application health check passed"
    fi
fi

# Reload Caddy (graceful, keeps connections open)
log "Reloading Caddy..."
sudo /bin/systemctl reload caddy

# Wait for Caddy to start
sleep 3

if ! sudo /bin/systemctl is-active --quiet caddy; then
    log "ERROR: Caddy service failed to start"
    sudo /bin/systemctl status caddy
    exit 1
fi

log "Deployment completed successfully at $(date)"
log "Application is running on: https://tpsdatabase.com.br"
} # end of release body
exit $?
