#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo or as root."
  exit 1
fi

APP_USER="${APP_USER:-ubuntu}"
APP_GROUP="${APP_GROUP:-www-data}"
APP_DIR="${APP_DIR:-/home/${APP_USER}/tripmate-backend}"
INSTALL_POSTGRES="${INSTALL_POSTGRES:-true}"
INSTALL_CERTBOT="${INSTALL_CERTBOT:-true}"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  python3 \
  python3-pip \
  python3-venv \
  build-essential \
  libpq-dev \
  nginx \
  rsync

if [[ "${INSTALL_POSTGRES}" == "true" ]]; then
  apt-get install -y postgresql postgresql-contrib
fi

if [[ "${INSTALL_CERTBOT}" == "true" ]]; then
  apt-get install -y certbot python3-certbot-nginx
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "${APP_USER}"
fi

if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
  groupadd "${APP_GROUP}"
fi

usermod -aG "${APP_GROUP}" "${APP_USER}"

mkdir -p "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chmod 775 "${APP_DIR}"

systemctl enable nginx

cat <<EOF
Bootstrap complete.

Next steps:
1. Create ${APP_DIR}/.env from deploy/aws/ec2/.env.production.example.
2. Create the PostgreSQL database and user if you are using local Postgres.
3. Run deploy/aws/ec2/deploy_remote.sh with sudo.
EOF
