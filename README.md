# Paid-bot 🚀

Telegram sales bot + admin dashboard with one-command VPS deployment.

> This file is the single source of truth for deployment and operations docs.

## Quick Install (VPS)

Run this on your VPS as root:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/install.sh)
```

This installer will:
- install system dependencies
- clone/update project to `/opt/paid-bot`
- create Python virtual environment and install requirements
- create and start systemd services for bot + dashboard
- ask which storage mode you want (Firebase / migrate / local JSON)

## Storage Mode Options

During install you will see:

1. Migrate current `config.json` to Firebase now
2. Keep Firebase auto behavior (default)
3. Skip Firebase and force local `config.json`

### Non-interactive install mode

```bash
STORAGE_MODE=migrate bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/install.sh)
# or STORAGE_MODE=firebase
# or STORAGE_MODE=json
```

## Change Storage Mode Later (No Reinstall)

Interactive:

```bash
ACTION=switch-storage bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/install.sh)
```

Non-interactive:

```bash
ACTION=switch-storage STORAGE_MODE=json bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/install.sh)
```

## Service Names

- `paid-bot.service`
- `paid-bot-dashboard.service`

## Service Commands

```bash
systemctl status paid-bot.service --no-pager
systemctl status paid-bot-dashboard.service --no-pager
journalctl -u paid-bot.service -f
journalctl -u paid-bot-dashboard.service -f
systemctl restart paid-bot.service paid-bot-dashboard.service
```

## Important Paths

- App folder: `/opt/paid-bot`
- Env file: `/etc/paid-bot/paid-bot.env`
- Main config: `/opt/paid-bot/config.json`
- Firebase key: `/opt/paid-bot/firebase-credentials.json`

## First-Time Configuration

1. Edit config:

```bash
nano /opt/paid-bot/config.json
```

2. Add your Telegram bot token and admin IDs.
3. Add panel, packages, locations, payment methods.
4. If using Firebase, upload `firebase-credentials.json`.
5. Restart services:

```bash
systemctl restart paid-bot.service paid-bot-dashboard.service
```

## Update Existing Installation

Re-run installer:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/install.sh)
```

This updates code/dependencies and restarts services.

## Uninstall

Remove services only:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/uninstall.sh)
```

Full remove (services + files):

```bash
REMOVE_DATA=true bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/uninstall.sh)
```

## Optional Environment Overrides

You can override defaults at install time:

```bash
REPO_BRANCH=main INSTALL_DIR=/opt/paid-bot SERVICE_USER=root bash <(curl -Ls https://raw.githubusercontent.com/x-kevinbro/Paid-bot/main/install.sh)
```

## Local Development (Optional)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
python admin_dashboard.py
```

## Notes

- If Firebase credentials are missing, app falls back to JSON mode automatically.
- To force JSON mode, use storage option `json` (writes `BOT_DISABLE_FIREBASE=true` to env file).
- Dashboard default port is `5000`.