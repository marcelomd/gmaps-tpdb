#!/bin/bash

# Deploy script for Django project on VPS
set -x
set -e  # Exit on any error

PROJECT_DIR="/var/www/tpdb"
VENV_DIR="$PROJECT_DIR/venv"
USER="tpdb"
GROUP="caddy"
BACKUP_DIR="/var/backups/tpdb"
# Code only: media and the venv are large, and restoring old media would discard newer uploads
BACKUP_EXCLUDES=(--exclude=./venv --exclude=./media --exclude=./.git)
BACKUP_DONE=false

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/tpdb/deploy.log
}

# Error handling function
handle_error() {
    log "ERROR: Deployment failed at line $1"
    log "Rolling back to previous version if backup exists..."

    # Before this deploy's backup exists, "latest" is an older deploy's code
    if [ "$BACKUP_DONE" = true ]; then
        log "Restoring from backup..."
        cp -r "$BACKUP_DIR/latest/"* "$PROJECT_DIR/" || true
        sudo /bin/systemctl restart tpdb || true
        log "Rollback attempted. Code only: migrations that already ran are NOT undone. Please check manually."
    fi

    exit 1
}

# Set error trap
trap 'handle_error $LINENO' ERR

# The body is one compound command so bash parses all of it before running any;
# otherwise "git reset --hard" below rewrites this file while bash is still reading it.
{
log "Starting deployment..."

# Check if we're running as the correct user
if [ "$(whoami)" != "$USER" ]; then
    log "ERROR: This script must be run as user '$USER'"
    exit 1
fi

# Navigate to project directory
cd $PROJECT_DIR || { log "ERROR: Cannot access project directory"; exit 1; }

# Files owned by another user (e.g. after running git/pip as root) make the
# chmod below fail after migrations have already run, so check before touching anything
FOREIGN_FILE=$(find "$PROJECT_DIR" -not -user "$USER" -print -quit)
if [ -n "$FOREIGN_FILE" ]; then
    log "ERROR: $FOREIGN_FILE is not owned by '$USER'; run: sudo chown -R $USER:$GROUP $PROJECT_DIR"
    exit 1
fi

# Create backup directory if it doesn't exist (tpdb user owns it)
mkdir -p $BACKUP_DIR

# Create backup before deployment
log "Creating backup..."
if [ -d "$BACKUP_DIR/latest" ]; then
    rm -rf "$BACKUP_DIR/previous"
    mv "$BACKUP_DIR/latest" "$BACKUP_DIR/previous"
fi
mkdir -p "$BACKUP_DIR/latest"
tar -C "$PROJECT_DIR" "${BACKUP_EXCLUDES[@]}" -cf - . | tar -C "$BACKUP_DIR/latest" -xf -
BACKUP_DONE=true

# Check Git repository status
log "Checking Git repository status..."
if ! git status &>/dev/null; then
    log "ERROR: Not a valid Git repository"
    exit 1
fi

# Stash any local changes
if ! git diff-index --quiet HEAD --; then
    log "WARNING: Local changes detected, stashing..."
    git stash
fi

# Pull latest code
log "Pulling latest code from Git..."
git fetch origin
git reset --hard origin/main

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
} # end of deployment body
exit $?
