#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="paid-bot"
INSTALL_DIR="${INSTALL_DIR:-/opt/${PROJECT_NAME}}"
ENV_DIR="/etc/${PROJECT_NAME}"
BOT_SERVICE="${PROJECT_NAME}.service"
DASHBOARD_SERVICE="${PROJECT_NAME}-dashboard.service"
REMOVE_DATA="${REMOVE_DATA:-false}"

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

warn() {
  echo -e "\033[1;33m[WARN]\033[0m $*"
}

error() {
  echo -e "\033[1;31m[ERROR]\033[0m $*"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    error "Please run this uninstaller as root (or with sudo)."
    exit 1
  fi
}

stop_disable_service() {
  local service="$1"
  if systemctl list-unit-files | grep -q "^${service}"; then
    info "Stopping and disabling ${service}..."
    systemctl stop "${service}" || true
    systemctl disable "${service}" || true
  else
    warn "Service ${service} not found. Skipping."
  fi
}

remove_unit_file() {
  local service="$1"
  local path="/etc/systemd/system/${service}"
  if [[ -f "${path}" ]]; then
    info "Removing ${path}..."
    rm -f "${path}"
  fi
}

remove_data_files() {
  if [[ "${REMOVE_DATA}" == "true" ]]; then
    warn "REMOVE_DATA=true detected. Removing ${INSTALL_DIR} and ${ENV_DIR}..."
    rm -rf "${INSTALL_DIR}" "${ENV_DIR}"
  else
    info "Keeping project files and config."
    echo "To remove data too, re-run with:"
    echo "  REMOVE_DATA=true bash uninstall.sh"
  fi
}

main() {
  require_root

  stop_disable_service "${BOT_SERVICE}"
  stop_disable_service "${DASHBOARD_SERVICE}"

  remove_unit_file "${BOT_SERVICE}"
  remove_unit_file "${DASHBOARD_SERVICE}"

  info "Reloading systemd daemon..."
  systemctl daemon-reload

  remove_data_files

  info "Uninstall completed."
}

main "$@"