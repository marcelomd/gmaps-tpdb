# Production Deployment Instructions

## 1. Server Setup

Update the following placeholders in your configuration files:

### In `Caddyfile`:
- Replace `yourdomain.com` with your actual domain

### In `tpdb.service`:
- Replace `/path/to/your/tpdb/project` with the actual path to your project
- Replace `/path/to/your/venv/bin/gunicorn` with the actual path to your virtual environment
- Update environment variables with your actual values

## 2. Installation Steps

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Collect static files:**
   ```bash
   python manage.py collectstatic --settings=tpdb.settings_production
   ```

3. **Run migrations:**
   ```bash
   python manage.py migrate --settings=tpdb.settings_production
   ```

4. **Create log directories:**
   ```bash
   sudo mkdir -p /var/log/django
   sudo chown www-data:www-data /var/log/django
   sudo mkdir -p /var/log/caddy
   ```

5. **Install systemd service:**
   ```bash
   sudo cp tpdb.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable tpdb
   sudo systemctl start tpdb
   ```

6. **Install and start Caddy:**
   ```bash
   sudo systemctl enable caddy
   sudo systemctl start caddy
   ```

## 3. Environment Variables

Set these environment variables in your production environment:
- `SECRET_KEY`: Django secret key
- `DOMAIN_NAME`: Your domain name
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: Database configuration

## 4. Verify Deployment

- Check Gunicorn status: `sudo systemctl status tpdb`
- Check Caddy status: `sudo systemctl status caddy`
- View logs: `sudo journalctl -u tpdb -f`