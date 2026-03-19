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

print_summary() {
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