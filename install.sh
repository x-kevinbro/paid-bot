#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="paid-bot"
INSTALL_DIR="${INSTALL_DIR:-/opt/${PROJECT_NAME}}"
SERVICE_USER="${SERVICE_USER:-root}"
REPO_URL="${REPO_URL:-https://github.com/x-kevinbro/Paid-bot.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
ENV_FILE="/etc/${PROJECT_NAME}/${PROJECT_NAME}.env"
BOT_SERVICE="${PROJECT_NAME}.service"
DASHBOARD_SERVICE="${PROJECT_NAME}-dashboard.service"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STORAGE_MODE="${STORAGE_MODE:-ask}"
ACTION="${ACTION:-install}"
CONFIGURE_CORE="${CONFIGURE_CORE:-ask}"
BOT_TOKEN_INPUT="${BOT_TOKEN_INPUT:-}"
ADMIN_IDS_INPUT="${ADMIN_IDS_INPUT:-}"
SELECTED_STORAGE_MODE=""

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

warn() {
  echo -e "\033[1;33m[WARN]\033[0m $*"
}

error() {
  echo -e "\033[1;31m[ERROR]\033[0m $*"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"

  if grep -qE "^[[:space:]]*${key}=" "${file}"; then
    sed -i "s|^[[:space:]]*${key}=.*|${key}=${value}|" "${file}"
  else
    echo "${key}=${value}" >> "${file}"
  fi
}

remove_env_key() {
  local key="$1"
  local file="$2"
  sed -i "/^[[:space:]]*${key}=/d" "${file}"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    error "Please run this installer as root (or with sudo)."
    exit 1
  fi
}

detect_package_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "apt"
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    echo "dnf"
    return
  fi
  if command -v yum >/dev/null 2>&1; then
    echo "yum"
    return
  fi
  error "No supported package manager found. Supported: apt, dnf, yum"
  exit 1
}

install_system_packages() {
  local manager
  manager="$(detect_package_manager)"

  info "Installing system dependencies with ${manager}..."
  case "${manager}" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y git curl ca-certificates ${PYTHON_BIN} python3-venv python3-pip tesseract-ocr
      ;;
    dnf)
      dnf install -y git curl ca-certificates python3 python3-pip python3-virtualenv tesseract
      ;;
    yum)
      yum install -y git curl ca-certificates python3 python3-pip tesseract
      ;;
  esac
}

ensure_project_files() {
  info "Preparing project files in ${INSTALL_DIR}..."
  mkdir -p "${INSTALL_DIR}"

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Existing git repo found. Pulling latest changes..."
    git -C "${INSTALL_DIR}" fetch --all --prune
    git -C "${INSTALL_DIR}" checkout "${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" pull origin "${REPO_BRANCH}"
  else
    if [[ -n "$(ls -A "${INSTALL_DIR}" 2>/dev/null)" ]]; then
      warn "${INSTALL_DIR} is not empty and not a git repo. Cleaning directory..."
      rm -rf "${INSTALL_DIR:?}/"*
    fi
    git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
  fi
}

setup_virtualenv() {
  info "Creating/updating virtual environment..."
  cd "${INSTALL_DIR}"
  ${PYTHON_BIN} -m venv venv
  ./venv/bin/pip install --upgrade pip
  ./venv/bin/pip install -r requirements.txt
}

setup_config_files() {
  info "Preparing configuration files..."

  if [[ ! -f "${INSTALL_DIR}/config.json" && -f "${INSTALL_DIR}/config.sample.json" ]]; then
    cp "${INSTALL_DIR}/config.sample.json" "${INSTALL_DIR}/config.json"
    warn "Created config.json from config.sample.json. You must edit it before production use."
  fi

  mkdir -p "/etc/${PROJECT_NAME}"

  if [[ ! -f "${ENV_FILE}" ]]; then
    cat > "${ENV_FILE}" <<'EOF'
# Optional overrides
# TELEGRAM_BOT_TOKEN=123456:ABCDEF
# PORT=5000
# ENABLE_SAFE_PROVISION_QUEUE=false
# ENABLE_UNLIMITED_CREATION_FLOW=false
EOF
    warn "Created ${ENV_FILE}. Add environment variables there if needed."
  fi

  chmod 600 "${ENV_FILE}"

  if [[ ! -f "${INSTALL_DIR}/firebase-credentials.json" ]]; then
    warn "firebase-credentials.json not found. Bot will fallback to local JSON mode if Firebase init fails."
  fi
}

select_storage_mode() {
  if [[ "${STORAGE_MODE}" != "ask" ]]; then
    case "${STORAGE_MODE}" in
      migrate|firebase|json)
        SELECTED_STORAGE_MODE="${STORAGE_MODE}"
        ;;
      *)
        warn "Invalid STORAGE_MODE='${STORAGE_MODE}'. Falling back to interactive selection."
        STORAGE_MODE="ask"
        ;;
    esac
  fi

  if [[ "${STORAGE_MODE}" == "ask" ]]; then
    echo
    echo "Select storage mode:"
    echo "  [1] Migrate current config.json to Firebase now"
    echo "  [2] Continue with current Firebase backup behavior (default)"
    echo "  [3] Skip Firebase and force local config.json mode"
    read -rp "Enter choice (1/2/3) [2]: " mode_choice
    mode_choice="${mode_choice:-2}"

    case "${mode_choice}" in
      1) SELECTED_STORAGE_MODE="migrate" ;;
      2) SELECTED_STORAGE_MODE="firebase" ;;
      3) SELECTED_STORAGE_MODE="json" ;;
      *)
        warn "Invalid choice. Using default option [2]."
        SELECTED_STORAGE_MODE="firebase"
        ;;
    esac
  fi

  if [[ -z "${SELECTED_STORAGE_MODE}" ]]; then
    SELECTED_STORAGE_MODE="firebase"
  fi
}

apply_storage_mode() {
  info "Applying storage mode: ${SELECTED_STORAGE_MODE}"

  case "${SELECTED_STORAGE_MODE}" in
    migrate)
      remove_env_key "BOT_DISABLE_FIREBASE" "${ENV_FILE}"
      remove_env_key "DISABLE_FIREBASE" "${ENV_FILE}"
      remove_env_key "USE_FIREBASE" "${ENV_FILE}"
      if [[ ! -f "${INSTALL_DIR}/firebase-credentials.json" ]]; then
        warn "Cannot migrate: firebase-credentials.json not found. Continuing with fallback behavior."
      else
        info "Migrating config.json to Firebase..."
        if "${INSTALL_DIR}/venv/bin/python" - <<'PY' "${INSTALL_DIR}"
import os
import sys

project_dir = sys.argv[1]
sys.path.insert(0, project_dir)

from firebase_db import migrate_to_firebase

ok, msg = migrate_to_firebase()
print(msg)
sys.exit(0 if ok else 1)
PY
        then
          info "Migration completed successfully."
        else
          warn "Migration failed. Services will still start with normal Firebase fallback behavior."
        fi
      fi
      ;;
    firebase)
      remove_env_key "BOT_DISABLE_FIREBASE" "${ENV_FILE}"
      remove_env_key "DISABLE_FIREBASE" "${ENV_FILE}"
      remove_env_key "USE_FIREBASE" "${ENV_FILE}"
      ;;
    json)
      set_env_value "BOT_DISABLE_FIREBASE" "true" "${ENV_FILE}"
      ;;
  esac
}

configure_core_settings() {
  local token_value="${BOT_TOKEN_INPUT}"
  local admin_ids_value="${ADMIN_IDS_INPUT}"
  local should_configure="yes"

  if [[ "${ACTION}" != "install" ]]; then
    return
  fi

  if [[ "${CONFIGURE_CORE}" == "no" ]]; then
    should_configure="no"
  elif [[ "${CONFIGURE_CORE}" == "ask" ]]; then
    read -rp "Configure telegram_bot_token and admin_ids now? (Y/n): " configure_choice
    configure_choice="${configure_choice:-y}"
    if [[ ! "${configure_choice}" =~ ^[Yy]$ ]]; then
      should_configure="no"
    fi
  fi

  if [[ "${should_configure}" != "yes" ]]; then
    return
  fi

  if [[ -z "${token_value}" ]]; then
    read -rp "Enter Telegram bot token (leave empty to skip): " token_value
  fi

  if [[ -z "${admin_ids_value}" ]]; then
    read -rp "Enter admin ID(s), comma-separated (e.g. 12345,67890). Leave empty to skip: " admin_ids_value
  fi

  if [[ -z "${token_value}" && -z "${admin_ids_value}" ]]; then
    info "Skipped core settings update."
    return
  fi

  info "Saving core settings to config.json..."
  if "${INSTALL_DIR}/venv/bin/python" - <<'PY' "${INSTALL_DIR}" "${token_value}" "${admin_ids_value}"
import json
import os
import re
import sys

project_dir = sys.argv[1]
token = (sys.argv[2] or '').strip()
admin_ids_raw = (sys.argv[3] or '').strip()
config_path = os.path.join(project_dir, 'config.json')

if not os.path.exists(config_path):
    print("config.json not found")
    sys.exit(1)

with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

if token:
    config['telegram_bot_token'] = token

if admin_ids_raw:
    parts = [part.strip() for part in admin_ids_raw.split(',') if part.strip()]
    if not parts:
        print("No valid admin IDs provided")
        sys.exit(1)
    parsed_ids = []
    for part in parts:
        if not re.fullmatch(r'\d+', part):
            print(f"Invalid admin ID: {part}")
            sys.exit(1)
        parsed_ids.append(int(part))
    config['admin_ids'] = parsed_ids

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

print("Core settings saved.")
PY
  then
    info "Core settings saved successfully."
  else
    warn "Failed to save core settings. You can edit ${INSTALL_DIR}/config.json manually."
  fi
}

create_systemd_services() {
  info "Creating systemd services..."

  cat > "/etc/systemd/system/${BOT_SERVICE}" <<EOF
[Unit]
Description=Paid Bot Telegram Worker
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  cat > "/etc/systemd/system/${DASHBOARD_SERVICE}" <<EOF
[Unit]
Description=Paid Bot Admin Dashboard
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=-${ENV_FILE}
Environment=PORT=5000
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/admin_dashboard.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
}

start_services() {
  info "Reloading systemd and starting services..."
  systemctl daemon-reload
  systemctl enable "${BOT_SERVICE}" "${DASHBOARD_SERVICE}"
  systemctl restart "${BOT_SERVICE}" "${DASHBOARD_SERVICE}"
}

restart_services_if_present() {
  info "Restarting services if installed..."
  systemctl daemon-reload

  if systemctl list-unit-files | grep -q "^${BOT_SERVICE}"; then
    systemctl restart "${BOT_SERVICE}"
  else
    warn "${BOT_SERVICE} not found. Skipping restart."
  fi

  if systemctl list-unit-files | grep -q "^${DASHBOARD_SERVICE}"; then
    systemctl restart "${DASHBOARD_SERVICE}"
  else
    warn "${DASHBOARD_SERVICE} not found. Skipping restart."
  fi
}

get_public_ip() {
  local ip=""

  if command -v curl >/dev/null 2>&1; then
    ip="$(curl -4 -fsS --max-time 4 https://api.ipify.org 2>/dev/null || true)"
  fi

  if [[ -z "${ip}" ]] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi

  echo "${ip}"
}

print_summary() {
  local dashboard_port="5000"
  local public_ip=""

  public_ip="$(get_public_ip)"

  echo
  info "Installation complete."
  echo "- Project directory : ${INSTALL_DIR}"
  echo "- Bot service       : ${BOT_SERVICE}"
  echo "- Dashboard service : ${DASHBOARD_SERVICE}"
  echo "- Env file          : ${ENV_FILE}"
  echo
  echo "Next commands:"
  echo "  systemctl status ${BOT_SERVICE} --no-pager"
  echo "  systemctl status ${DASHBOARD_SERVICE} --no-pager"
  echo "  journalctl -u ${BOT_SERVICE} -f"
  echo "  journalctl -u ${DASHBOARD_SERVICE} -f"
  echo
  echo "Dashboard login URLs:"
  echo "  http://127.0.0.1:${dashboard_port}/login"
  if [[ -n "${public_ip}" ]]; then
    echo "  http://${public_ip}:${dashboard_port}/login"
  fi
  echo
  echo "First-time setup (required):"
  echo "  1) Edit ${INSTALL_DIR}/config.json"
  echo "     - set telegram_bot_token"
  echo "     - set at least one admin_id"
  echo "  2) Restart services"
  echo "     systemctl restart ${BOT_SERVICE} ${DASHBOARD_SERVICE}"
  echo "  3) Open dashboard /login and send /active to your bot to get login code"
  echo
  echo "If needed, edit config then restart:"
  echo "  nano ${INSTALL_DIR}/config.json"
  echo "  systemctl restart ${BOT_SERVICE} ${DASHBOARD_SERVICE}"
}

main() {
  require_root

  case "${ACTION}" in
    install)
      install_system_packages
      ensure_project_files
      setup_virtualenv
      setup_config_files
      configure_core_settings
      select_storage_mode
      apply_storage_mode
      create_systemd_services
      start_services
      print_summary
      ;;
    switch-storage)
      setup_config_files
      select_storage_mode
      apply_storage_mode
      restart_services_if_present
      info "Storage mode update completed."
      ;;
    *)
      error "Invalid ACTION='${ACTION}'. Supported values: install, switch-storage"
      exit 1
      ;;
  esac
}

main "$@"