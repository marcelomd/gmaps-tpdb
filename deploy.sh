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

# Everything that changes between releases lives in scripts/release.sh. It is run as a
# child process, so bash reads the freshly checked-out copy, and a failure in it still
# reaches the ERR trap above and rolls back.
if [ ! -f "scripts/release.sh" ]; then
    log "ERROR: scripts/release.sh not found"
    exit 1
fi
bash scripts/release.sh

} # end of deployment body
exit $?
