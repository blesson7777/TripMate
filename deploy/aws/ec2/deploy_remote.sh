#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo or as root."
  exit 1
fi

APP_USER="${APP_USER:-ubuntu}"
APP_GROUP="${APP_GROUP:-www-data}"
APP_DIR="${APP_DIR:-/home/${APP_USER}/tripmate-backend}"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:-/tmp/tripmate-backend.tgz}"
SERVICE_NAME="${SERVICE_NAME:-tripmate}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-tripmate}"
BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
BIND_PORT="${BIND_PORT:-8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"
SERVER_NAME="${SERVER_NAME:-}"
TLS_DOMAIN="${TLS_DOMAIN:-}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ -n "${TLS_DOMAIN}" && -z "${SERVER_NAME}" ]]; then
  SERVER_NAME="${TLS_DOMAIN}"
fi

if [[ -z "${SERVER_NAME}" ]]; then
  SERVER_NAME="_"
fi

if [[ ! -f "${RELEASE_ARCHIVE}" ]]; then
  echo "Release archive not found: ${RELEASE_ARCHIVE}"
  exit 1
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
  echo "App user does not exist: ${APP_USER}"
  echo "Run deploy/aws/ec2/bootstrap_ubuntu.sh first."
  exit 1
fi

WORK_DIR="$(mktemp -d /tmp/tripmate-release.XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT

tar -xzf "${RELEASE_ARCHIVE}" -C "${WORK_DIR}"

if [[ ! -f "${WORK_DIR}/manage.py" ]]; then
  echo "Archive is missing manage.py at its root."
  exit 1
fi

mkdir -p "${APP_DIR}" "${APP_DIR}/media" "${APP_DIR}/staticfiles"

rsync -a --delete \
  --exclude ".env" \
  --exclude "backups/" \
  --exclude "media/" \
  --exclude "staticfiles/" \
  --exclude "venv/" \
  --exclude ".git/" \
  --exclude ".vscode/" \
  --exclude "mobile_app/" \
  "${WORK_DIR}/" "${APP_DIR}/"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "Missing ${APP_DIR}/.env"
  echo "Copy ${APP_DIR}/deploy/aws/ec2/.env.production.example to ${APP_DIR}/.env and fill in production values."
  exit 1
fi

run_as_app_user() {
  local command="$1"
  runuser -u "${APP_USER}" -- bash -lc "cd '${APP_DIR}' && ${command}"
}

run_as_app_user "'${PYTHON_BIN}' -m venv '${APP_DIR}/venv'"
run_as_app_user "'${APP_DIR}/venv/bin/pip' install --upgrade pip"
run_as_app_user "'${APP_DIR}/venv/bin/pip' install -r requirements.txt"
run_as_app_user "'${APP_DIR}/venv/bin/python' manage.py migrate --noinput"
run_as_app_user "'${APP_DIR}/venv/bin/python' manage.py collectstatic --noinput"
run_as_app_user "'${APP_DIR}/venv/bin/python' manage.py check"

TEMPLATE_DIR="${APP_DIR}/deploy/aws/ec2/templates"
SERVICE_TEMPLATE="${TEMPLATE_DIR}/tripmate.service.template"
NGINX_HTTP_TEMPLATE="${TEMPLATE_DIR}/nginx_tripmate.conf.template"
NGINX_SSL_TEMPLATE="${TEMPLATE_DIR}/nginx_tripmate_ssl.conf.template"
NGINX_TEMPLATE="${NGINX_HTTP_TEMPLATE}"
HAS_TLS_CERT="false"

if [[ -n "${TLS_DOMAIN}" ]]; then
  CERT_LIVE_DIR="/etc/letsencrypt/live/${TLS_DOMAIN}"
  if [[ -f "${CERT_LIVE_DIR}/fullchain.pem" && -f "${CERT_LIVE_DIR}/privkey.pem" ]]; then
    HAS_TLS_CERT="true"
    NGINX_TEMPLATE="${NGINX_SSL_TEMPLATE}"
  fi
fi

if [[ ! -f "${SERVICE_TEMPLATE}" ]]; then
  echo "Missing deployment templates under ${TEMPLATE_DIR}"
  exit 1
fi

if [[ ! -f "${NGINX_TEMPLATE}" ]]; then
  echo "Missing deployment templates under ${TEMPLATE_DIR}"
  exit 1
fi

render_template() {
  local template_path="$1"
  local output_path="$2"

  sed \
    -e "s|__APP_USER__|${APP_USER}|g" \
    -e "s|__APP_GROUP__|${APP_GROUP}|g" \
    -e "s|__APP_DIR__|${APP_DIR}|g" \
    -e "s|__SERVER_NAME__|${SERVER_NAME}|g" \
    -e "s|__TLS_DOMAIN__|${TLS_DOMAIN}|g" \
    -e "s|__BIND_ADDRESS__|${BIND_ADDRESS}|g" \
    -e "s|__BIND_PORT__|${BIND_PORT}|g" \
    -e "s|__WORKERS__|${GUNICORN_WORKERS}|g" \
    "${template_path}" > "${output_path}"
}

render_template "${SERVICE_TEMPLATE}" "/etc/systemd/system/${SERVICE_NAME}.service"
render_template "${NGINX_TEMPLATE}" "/etc/nginx/sites-available/${NGINX_SITE_NAME}"

ln -sfn \
  "/etc/nginx/sites-available/${NGINX_SITE_NAME}" \
  "/etc/nginx/sites-enabled/${NGINX_SITE_NAME}"

if [[ "${NGINX_SITE_NAME}" == "tripmate" ]]; then
  rm -f /etc/nginx/sites-enabled/tripmate.conf
elif [[ "${NGINX_SITE_NAME}" == "tripmate.conf" ]]; then
  rm -f /etc/nginx/sites-enabled/tripmate
fi
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl reload nginx

if [[ -n "${TLS_DOMAIN}" ]]; then
  if [[ "${HAS_TLS_CERT}" != "true" ]]; then
    if [[ -n "${LETSENCRYPT_EMAIL}" ]]; then
      certbot --nginx --non-interactive --agree-tos \
        --email "${LETSENCRYPT_EMAIL}" \
        -d "${TLS_DOMAIN}" \
        --redirect
    else
      certbot --nginx --non-interactive --agree-tos \
        --register-unsafely-without-email \
        -d "${TLS_DOMAIN}" \
        --redirect
    fi

    systemctl reload nginx
  fi
fi

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

cat <<EOF
Deployment complete.

Application directory: ${APP_DIR}
Service: ${SERVICE_NAME}
Nginx site: ${NGINX_SITE_NAME}
EOF
