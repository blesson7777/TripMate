# AWS EC2 Deployment

This backend is set up for a standard Ubuntu EC2 deployment:

- `nginx` serves `/static/` and `/media/`
- `gunicorn` runs the Django app on `127.0.0.1:8000`
- `systemd` keeps the service alive

## One-time EC2 bootstrap

On the EC2 instance:

```bash
chmod +x deploy/aws/ec2/bootstrap_ubuntu.sh
sudo APP_USER=ubuntu APP_DIR=/home/ubuntu/tripmate-backend bash deploy/aws/ec2/bootstrap_ubuntu.sh
```

If you are using local PostgreSQL on the EC2 instance, create the database and user:

```bash
sudo -u postgres psql
CREATE DATABASE tripmate_db;
CREATE USER tripmate_user WITH PASSWORD 'replace-with-your-db-password';
GRANT ALL PRIVILEGES ON DATABASE tripmate_db TO tripmate_user;
\q
```

Create the production env file:

```bash
cp deploy/aws/ec2/.env.production.example .env
chmod 600 .env
```

## Deploy from Windows

From this repository on Windows:

```powershell
.\deploy\aws\ec2\deploy_from_windows.ps1 `
  -RemoteHost 13.60.219.105 `
  -KeyPath C:\path\to\tripmate.pem `
  -ServerName 13-60-219-105.sslip.io `
  -TlsDomain 13-60-219-105.sslip.io `
  -Bootstrap `
  -UploadDotEnv
```

`-UploadDotEnv` uploads the local repo `.env` to the EC2 app directory. Use it only if your local `.env` already contains the correct production values.

If `-TlsDomain` is set but `-LetsEncryptEmail` is omitted, the deploy script will run certbot with `--register-unsafely-without-email`.

## Deploy directly on the EC2 instance

After copying a backend bundle to `/tmp/tripmate-backend.tgz`:

```bash
chmod +x deploy/aws/ec2/deploy_remote.sh
sudo APP_USER=ubuntu \
  APP_DIR=/home/ubuntu/tripmate-backend \
  RELEASE_ARCHIVE=/tmp/tripmate-backend.tgz \
  SERVER_NAME=13-60-219-105.sslip.io \
  TLS_DOMAIN=13-60-219-105.sslip.io \
  bash deploy/aws/ec2/deploy_remote.sh
```

## Operational checks

```bash
sudo systemctl status tripmate
sudo systemctl status nginx
journalctl -u tripmate -n 100 --no-pager
curl -I http://127.0.0.1:8000
```
