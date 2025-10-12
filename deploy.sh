#!/bin/bash

# Deploy script for Django project on VPS
set -x
set -e  # Exit on any error

PROJECT_DIR="/var/www/tpdb"
VENV_DIR="$PROJECT_DIR/venv"
USER="tpdb"
GROUP="caddy"
BACKUP_DIR="/var/backups/tpdb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/tpdb/deploy.log
}

# Error handling function
handle_error() {
    log "ERROR: Deployment failed at line $1"
    log "Rolling back to previous version if backup exists..."

    if [ -d "$BACKUP_DIR/latest" ]; then
        log "Restoring from backup..."
        cp -r "$BACKUP_DIR/latest/"* "$PROJECT_DIR/" || true
        sudo /bin/systemctl restart tpdb || true
        log "Rollback attempted. Please check manually."
    fi

    exit 1
}

# Set error trap
trap 'handle_error $LINENO' ERR

log "Starting deployment..."

# Check if we're running as the correct user
if [ "$(whoami)" != "$USER" ]; then
    log "ERROR: This script must be run as user '$USER'"
    exit 1
fi

# Navigate to project directory
cd $PROJECT_DIR || { log "ERROR: Cannot access project directory"; exit 1; }

# Create backup directory if it doesn't exist (tpdb user owns it)
mkdir -p $BACKUP_DIR

# Create backup before deployment
log "Creating backup..."
if [ -d "$BACKUP_DIR/latest" ]; then
    rm -rf "$BACKUP_DIR/previous"
    mv "$BACKUP_DIR/latest" "$BACKUP_DIR/previous"
fi
mkdir -p "$BACKUP_DIR/latest"
cp -r $PROJECT_DIR/* "$BACKUP_DIR/latest/" 2>/dev/null || true

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

# Update file permissions (already running as tpdb user)
log "Updating file permissions..."
chmod -R 755 $PROJECT_DIR
chmod 644 $PROJECT_DIR/.env 2>/dev/null || true

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
    if ! curl -f -s -o /dev/null --unix-socket /var/www/tpdb/tpdb.sock http://localhost/; then
        log "WARNING: Application health check failed"
    else
        log "Application health check passed"
    fi
fi

# Restart Caddy
log "Restarting Caddy..."
sudo /bin/systemctl restart caddy

# Wait for Caddy to start
sleep 3

if ! sudo /bin/systemctl is-active --quiet caddy; then
    log "ERROR: Caddy service failed to start"
    sudo /bin/systemctl status caddy
    exit 1
fi

# Clean up old backups (keep last 5) - tpdb owns backup dir, no sudo needed
log "Cleaning up old backups..."
find $BACKUP_DIR -maxdepth 1 -type d -name "backup_*" | sort -r | tail -n +6 | xargs rm -rf

log "Deployment completed successfully at $(date)"
log "Application is running on: https://tpsdatabase.com.br"