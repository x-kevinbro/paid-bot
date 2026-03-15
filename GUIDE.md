# Paid-Bot — Complete Operator Guide

> **Stack:** Python 3.13 · aiogram 3 · Flask · Firebase Firestore · 3x-ui panels  
> **Processes:** `worker` (bot, long-polling) + `web` (admin dashboard, Flask)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Initial Setup](#3-initial-setup)
4. [Config Reference](#4-config-reference)
5. [Admin Dashboard](#5-admin-dashboard)
6. [Telegram Bot — User Flow](#6-telegram-bot--user-flow)
7. [Telegram Bot — Admin Commands](#7-telegram-bot--admin-commands)
8. [Referral & Coupon System](#8-referral--coupon-system)
9. [Receipt Verification](#9-receipt-verification)
10. [Provisioning System](#10-provisioning-system)
11. [Premium Channel & Expiry Removal](#11-premium-channel--expiry-removal)
12. [Languages & Custom Messages](#12-languages--custom-messages)
13. [Payment Methods](#13-payment-methods)
14. [Stripe Integration](#14-stripe-integration)
15. [Firebase Storage](#15-firebase-storage)
16. [System Settings Reference](#16-system-settings-reference)
17. [Deployment](#17-deployment)
18. [Environment Variables](#18-environment-variables)
19. [Troubleshooting](#19-troubleshooting)

---

## 1. Overview

Paid-Bot is a **Telegram-based V2Ray subscription sales system**. Customers purchase VPN/proxy packages directly inside Telegram. Admins review payment receipts through a web dashboard and approve orders. The bot then automatically creates a 3x-ui panel account and delivers the subscription config to the customer.

**Core capabilities:**

| Feature | Notes |
|---|---|
| Multi-ISP, multi-package catalog | Admin managed via dashboard |
| Referral code system | Auto-generated per user after first purchase |
| Admin coupon codes | Generated on-demand, configurable discount & usage limit |
| Custom package builder | User picks GB + days, price calculated automatically |
| Automatic 3x-ui account creation | Supports VLESS, VMess, Trojan, Shadowsocks |
| Multi-panel with failover | Primary + backup panel per location |
| Premium Telegram channel access | One-time invite link per approved user |
| Automated channel removal | Kicks expired members daily |
| Receipt OCR + verification | Amount matching, duplicate tx detection |
| Firebase Firestore sync | Optional cloud storage with local JSON fallback |
| Stripe payment gateway | Optional, currently disabled |
| Bilingual UI | English + Sinhala (fully customizable per key) |

---

## 2. Architecture

```
config.json / Firebase Firestore
        │
        ├── bot.py  (aiogram worker process)
        │     ├── Purchase FSM flow
        │     ├── Referral / coupon system
        │     ├── provision_loop (every 5s)
        │     ├── notifications_loop (every 10s)
        │     └── schedule_loop → remove_expired_members (daily 00:10)
        │
        └── admin_dashboard.py  (Flask web process)
              ├── Order management (approve / reject / resend / revoke)
              ├── Panel / location / package / ISP CRUD
              ├── Receipt OCR & verification
              ├── Payment method management
              └── System settings
```

Both processes share state through **`load_config()` / `save_config()`** — reads/writes go to Firestore first, then JSON file. No in-memory state is shared between the two processes.

---

## 3. Initial Setup

### 3.1 Prerequisites

- Python 3.10+ (3.13 recommended)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- At least one running 3x-ui panel with a configured inbound
- (Optional) Firebase project with Firestore enabled

### 3.2 Install

```bash
git clone <your-repo>
cd Paid-bot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3.3 Configure

Copy and edit the sample config:

```bash
cp config.sample.json config.json
```

Minimum required fields:

```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "admin_ids": [YOUR_TELEGRAM_USER_ID],
  "currency": "LKR",
  "panels": [
    {
      "id": 1,
      "name": "Panel 1",
      "url": "https://yourpanel.com:2053/path/",
      "username": "admin",
      "password": "password"
    }
  ],
  "locations": [
    {
      "id": "loc1",
      "name": "Singapore",
      "panel_id": 1,
      "backup_panel_id": null,
      "inbound_tag": "INBOUND_SG"
    }
  ],
  "packages": [
    {
      "id": "pkg1",
      "name": "Basic 30GB",
      "gb": 30,
      "price": 500,
      "description": "30GB for 30 days"
    }
  ],
  "payment_details": {
    "methods": [
      {
        "id": "bank1",
        "name": "Bank Transfer",
        "type": "bank",
        "bank_name": "Your Bank",
        "account_name": "Your Name",
        "account_number": "1234567890"
      }
    ]
  }
}
```

### 3.4 Run

```bash
# Terminal 1 — Telegram bot
python bot.py

# Terminal 2 — Admin dashboard
python admin_dashboard.py
```

Dashboard runs at `http://localhost:5000` by default.

### 3.5 First Login to Dashboard

1. Open `http://localhost:5000` — you will see a 6-character login code on screen.
2. Send `/active <CODE>` from your Telegram account to the bot.
3. Submit the code in the browser — you are now logged in.

---

## 4. Config Reference

All configuration lives in `config.json` (and optionally mirrored to Firebase). Every key is live-reloaded — no restart needed after saving.

### Top-Level Keys

| Key | Type | Default | Purpose |
|---|---|---|---|
| `telegram_bot_token` | string | — | Bot API token from BotFather |
| `admin_ids` | int[] | — | Telegram IDs with admin privileges |
| `admin_password` | string | `""` | Legacy; not used in current flow |
| `currency` | string | `"LKR"` | Currency label shown to users |
| `subscription_duration` | int | `30` | Default subscription days |
| `premium_channel_id` | string | `""` | Telegram channel ID for premium access |
| `backup_channel_id` | string | `""` | Channel for account delivery logs |
| `panel_backup_db_path` | string | `""` | Local path to 3x-ui DB for backup uploads |
| `referrals_enabled` | bool | `true` | Allow users to claim codes |
| `referral_claim_limit` | int | `3` | Max claims per window per user |
| `referral_claim_window_minutes` | int | `60` | Window duration in minutes |
| `admin_coupon_cooldown_minutes` | int | `60` | Cooldown after hitting claim limit |
| `default_code_max_redemptions` | int | `0` | 0 = unlimited |
| `coupon_min_order_amount` | float | `0` | Min order total for coupon to activate |
| `receipt_amount_tolerance_percent` | float | `2` | ±% tolerance for OCR amount match |
| `tx_ref_pattern` | string | `""` | Regex to extract tx reference from receipts |
| `maintenance_mode` | bool | `false` | Block non-admin bot usage |
| `maintenance_banner_text` | string | `"Bot is under development."` | Shown to users during maintenance |
| `safe_provision_queue_enabled` | bool | `false` | Single-worker provisioning |
| `unlimited_style_creation_enabled` | bool | `false` | Protocol-aware 3x-ui payload builder |
| `auto_panel_failover_enabled` | bool | `false` | Try backup panel on creation failure |
| `provision_max_attempts` | int | `5` | Max retries before marking provision failed |
| `custom_package_enabled` | bool | `false` | Enable custom GB/days option |
| `stripe_enabled` | bool | `false` | Enable Stripe payment gateway |

### Packages

```json
"packages": [
  {
    "id": "pkg1",
    "name": "Basic 30GB",
    "gb": 30,
    "price": 500,
    "description": "30GB · 30 days"
  }
]
```

### Locations

```json
"locations": [
  {
    "id": "loc1",
    "name": "Singapore Premium",
    "panel_id": 1,
    "backup_panel_id": null,
    "inbound_tag": "INBOUND_SG",
    "description": ""
  }
]
```

`backup_panel_id` is used when `auto_panel_failover_enabled = true` and the primary panel fails.

### Panels

```json
"panels": [
  {
    "id": 1,
    "name": "Singapore Panel",
    "url": "https://panel.example.com:2053/secret/",
    "username": "admin",
    "password": "password",
    "api_port": null,
    "manual_address": ""
  }
]
```

`manual_address`: override the host used when building subscription links (useful when panel is behind NAT).

### ISP Providers

```json
"isp_providers": [
  {
    "id": "dialog",
    "name": "Dialog",
    "description": "Dialog Axiata",
    "packages": [
      {
        "id": "dialog_youtube",
        "name": "YouTube",
        "sni": "youtube.com",
        "address": "",
        "port": 443,
        "use_location_sni": false
      }
    ]
  }
]
```

### Custom Package Pricing

```json
"custom_package_pricing": {
  "price_per_gb": 10,
  "price_per_day": 5,
  "min_gb": 10,
  "max_gb": 1000,
  "min_days": 1,
  "max_days": 365
}
```

---

## 5. Admin Dashboard

Access at `http://localhost:5000` (or your deployed URL).

### Sections

| Page | URL | What you can do |
|---|---|---|
| Dashboard | `/` | Overview stats: packages, ISPs, locations, panels, order counts |
| Orders | `/orders` | Review, approve, reject, resend, revoke orders; OCR and verify receipts |
| Packages | `/packages` | Add/edit/delete V2Ray packages |
| Locations | `/locations` | Add/edit/delete server locations; assign primary + backup panels |
| Panels | `/panels` | Add/edit/delete 3x-ui panels |
| ISPs | `/isps` | Add/edit/delete ISP providers and their sub-packages |
| User Packages | `/user-packages` | Manage user-facing package options |
| Buyers | `/buyers` | List of all buyers with Telegram ID, package, and purchase date |
| Payment Methods | `/payment-methods` | Add/edit/delete bank, eZcash, and crypto payment methods |
| Messages | `/messages` | Override any bot message text in EN or Sinhala |
| Settings | `/settings` | General settings (token, currency) |
| System Settings | `/system-settings` | Advanced flags, provisioning controls, receipt verification |
| System | `/system` | Admin IDs management; Firebase status; config backup download |

### Order Management

This is the most important page in the dashboard. Each row is one customer order waiting to be reviewed or managed.

### What each column means

| Column | Meaning |
|---|---|
| Order ID | Unique order reference. Use this when checking logs or asking support questions. |
| User | Telegram username and Telegram user ID of the buyer. |
| ISP / App | The ISP the customer selected, plus the app/profile they want to use. |
| Package | The package name the customer bought. |
| Location | The selected server/location ID. |
| Price | Final amount for this order. This may already include fees or discounts. |
| Date | When the order was created. |
| Status | Purchase status: pending, approved, or rejected. |
| Receipt | Tools for checking the payment proof. |
| Actions | What you can do with the order after review. |

### Status badges

There are two different status layers shown in the order row:

| Badge Type | Meaning |
|---|---|
| `⏳ Pending` | Order is waiting for admin review. Nothing has been provisioned yet. |
| `✓ Approved` | Order was accepted and the account was or will be provisioned. |
| `✗ Rejected` | Order was rejected. The user can upload a new receipt through the retry flow. |
| `✓ Receipt OK` | Receipt verification passed. |
| `⚠ Partial` | Some receipt data was found, but not enough for a strong match. |
| `✗ Mismatch` | Receipt amount does not match the order total closely enough. |
| `⚠ Duplicate` | The same transaction reference appears in another order. Review carefully. |
| `✓ Manual OK` | Admin manually accepted the receipt check. |
| `⚑ Flagged` | Admin manually flagged the receipt as suspicious or needing attention. |

### Recommended review workflow

For a normal pending order, use this sequence:

1. Click **View** to open the receipt and check the payment proof.
2. If the receipt looks valid, click **Approve**.
3. If the receipt is clearly wrong or unpaid, click **Reject**.


### Receipt button

| Button | Use it when | Result |
|---|---|---|
| View | You want to inspect the uploaded receipt | Opens the original receipt in a new tab |

### Order action buttons

These buttons affect the actual service/account, not just the receipt review:

| Button | Available when | What it does |
|---|---|---|
| Approve | Pending | Accepts the order, creates the referral reward/code updates, and queues account provisioning |
| Reject | Pending | Rejects the order and lets the user retry with a new receipt |
| Resend | Approved | Sends the already-created config/account message to the user again |
| Revoke | Approved | Removes the user from the panel/account setup |
| Regenerate | Approved | Creates a new panel account for the same order |

### Important distinction

`Approved` does not mean the receipt check was perfect. It only means the order itself was accepted. A row can show `✓ Approved` together with `⚑ Flagged` or another receipt-verification badge. That is why you should treat:

- the main status badge as the order decision
- the receipt badge as the payment-proof quality check

If your team gets confused, tell them to read the row in this order:

1. Is the order `Pending`, `Approved`, or `Rejected`?
2. Is the receipt `OK`, `Partial`, `Mismatch`, `Duplicate`, or manually flagged?
3. Which button is appropriate now: approve/reject, or resend/revoke/regenerate?

---

## 6. Telegram Bot — User Flow

### Complete Purchase Journey

```
1. /start
   └─ Select Language (English / සිංහල)

2. Main Menu
   └─ 🛒 Buy Account

3. Select ISP (e.g., Dialog, Mobitel)

4. Select App / Sub-Package (e.g., YouTube, WhatsApp)

5. Select Package Type
   ├─ Predefined: pick from package list (e.g., 30GB — LKR 500)
   └─ Custom: enter GB → enter days → price auto-calculated

6. Select Location (e.g., Singapore Premium)
   └─ Best discount auto-applied here (referral reward or coupon)

7. Select Payment Method
   └─ Payment account details shown

8. Enter Your Name (used as panel username)

9. Upload Payment Receipt (photo or PDF)

10. Optional: Add a note for admin

11. ✅ Order submitted — admin notified
```

### After Admin Approves

1. Bot creates V2Ray account on the 3x-ui panel
2. User receives:
   - Subscription link (VLESS / VMess / Trojan / Shadowsocks)
   - Link to join premium Telegram channel
3. Account summary sent to backup channel
4. Panel DB backup sent to backup channel

### After Admin Rejects

- User receives a rejection message in their language
- A **Retry** button lets them re-upload a new receipt without re-selecting the package

---

## 7. Telegram Bot — Admin Commands

All commands require the sender's Telegram ID to be in `admin_ids`.

| Command | Syntax | What it does |
|---|---|---|
| `/active` | `/active CODE` | Verifies dashboard login code sent from browser |
| `/genref` | `/genref <count> <discount%> <max_uses>` | Generates N admin coupon codes |
| `/refstats` | `/refstats` | Shows all referral codes, usage counts, rewards pipeline |
| `/broadcast` | `/broadcast` then send message | Sends HTML message to all users who ever used the bot |

### `/genref` Examples

```
/genref 5 20 0       → 5 codes, 20% off, unlimited uses
/genref 10 15 1      → 10 codes, 15% off, single use each
/genref 1 50 3       → 1 code, 50% off, max 3 uses
```

Generated codes look like: `ADMIN_A3K9P2`

### Admin Inline Buttons (in bot chat)

When a user orders, all admins receive a notification with:

- **✅ Approve** — creates account immediately via bot
- **❌ Reject** — sends rejection message to user
- **👁 View Order** — shows full order details and receipt

---

## 8. Referral & Coupon System

### User Referral Codes

- **Auto-generated** after a user's first order is approved
- Format: `REF{last4ofID}{XX}` (e.g., `REF1234AB`)
- Gives the buyer **10% off**
- The referrer earns a **pending reward** (10% off their next purchase) when their referred friend's order is approved
- A 24-hour validity tracking window applies; codes are single-use per claimant

### Admin Coupon Codes

- Created with `/genref count discount% max_uses`
- Can be used at checkout or via `/apply CODE`
- Rate limits apply (configurable in System Settings):
  - Max claims per window: `referral_claim_limit` (default 3)
  - Window duration: `referral_claim_window_minutes` (default 60 min)
  - After limit hit: cooldown of `admin_coupon_cooldown_minutes` minutes

### Claiming a Code

**Method 1 — at checkout:**  
The best applicable discount is auto-applied when the user reaches the payment screen. No manual action needed.

**Method 2 — `/apply` command:**  
```
/apply ADMIN_A3K9P2
```
The code is saved to the user's session and applied on the next purchase.

### Discount Selection Logic

When a user reaches the payment screen, the system:

1. Collects all pending referral rewards for the user
2. Collects any claimed coupon codes
3. Selects the **single best discount** (highest `discount_amount`, then `discount_percent`, then rewards preferred over coupons on tie)
4. Applies it to the order total

> Only one discount applies per order. Used codes are removed from the user's claimed list.

### Minimum Order Amount

Set `coupon_min_order_amount` in System Settings. If the order total is below this value, no discount is applied.

### `/referral` Command

Shows the user:
- Their personal referral code
- How many people used it
- Their pending rewards (discounts earned from referrals)
- How the program works with shareable invite message

---

## 9. Receipt Verification

The dashboard can automatically check payment receipts to help admins spot issues before approving.

### How It Works

1. **OCR** (optional) — click **OCR** button on an order. If Pillow + pytesseract are installed on the server, text is extracted from the receipt image and saved to the order.
2. **Verify** — click **Verify** button. The system:
   - Combines OCR text + user note
   - Extracts an amount (looks for LKR, Rs., USD, $, or bare numbers)
   - Extracts a transaction reference (uses your custom regex or built-in patterns: TXN…, REF…, long numeric strings)
   - Checks for duplicate transaction references across all orders
   - Compares extracted amount vs expected order total within your tolerance %

### Verification Statuses

| Badge | Meaning |
|---|---|
| ✓ Receipt OK (green) | Amount matches within tolerance, no duplicate |
| ✗ Mismatch (red) | Amount differs beyond tolerance |
| ⚠ Duplicate (orange) | Same transaction reference found in another order |
| ⚠ Partial (yellow) | Amount could not be extracted, but tx ref present |
| Unverified (none) | Not yet verified |
| ✓ Manual OK (green) | Admin manually marked as OK |
| ⚑ Flagged (red) | Admin manually flagged |

### Configuration (System Settings → Receipt Verification)

| Setting | Default | Notes |
|---|---|---|
| Amount Match Tolerance % | `2` | ±2% of order total. Set higher for loose matching. |
| Transaction Reference Regex | `""` | Optional. E.g. `[A-Z]{3}[0-9]{10,16}`. Leave empty for built-in patterns. |

### Installing OCR Dependencies

OCR is **optional** and silently disabled if packages are missing:

```bash
pip install Pillow pytesseract
# Also requires Tesseract binary:
# Ubuntu: sudo apt install tesseract-ocr
# Windows: install from https://github.com/UB-Mannheim/tesseract/wiki
```

---

## 10. Provisioning System

When an order is approved (via bot button or dashboard), a provision request is queued in `provision_requests`. The bot's `provision_loop` (runs every 5 seconds) picks it up.

### Provision Request Types

| Type | Triggered From | What Happens |
|---|---|---|
| `provision` | Order approved | Creates V2Ray account on panel, sends config to user |
| `resend` | Dashboard Resend | Re-sends existing account config to user |
| `revoke` | Dashboard Revoke | Removes client from panel |
| `regenerate` | Dashboard Regenerate | Creates new panel account (new UUID) for the order |

### Panel Selection Order

1. Location's `panel_id` (primary)
2. Location's `backup_panel_id` (if `auto_panel_failover_enabled = true`)
3. Any remaining panels in the config

### Account Creation Methods (tried in order)

1. **Unlimited Style** (`unlimited_style_creation_enabled = true`) — protocol-aware payload builder, most compatible
2. **Standard addClient** — `POST /panel/api/inbounds/addClient`
3. **updateInbound fallback** — patches inbound settings JSON directly

### Retry Behavior

- Failed requests retry up to `provision_max_attempts` times
- After max attempts: order marked `status: failed`, admin notified
- Admins can trigger **Regenerate** from dashboard to retry

### Safe Queue Mode

When `safe_provision_queue_enabled = true`, only one provision request is processed at a time. Use this if your panel has issues handling concurrent API calls.

---

## 11. Premium Channel & Expiry Removal

### Premium Channel

When a user's order is approved, the bot generates a **one-time invite link** (`member_limit=1`) to the premium Telegram channel.

The invite is:
- Automatically revoked once the user joins
- One per user per approved order

Configure the channel ID via:
- Dashboard → System Settings → Premium Channel ID
- Or environment variable `PREMIUM_CHANNEL_ID`

### Automated Expiry Removal

Every day at **00:10** (Asia/Colombo), the bot scans all approved orders and kicks users who have expired accounts.

**Conditions to be removed:**
1. The account's panel `expiry` timestamp has passed, AND
2. At least 33 days have elapsed since `approved_at` / `created_at`

The removal is a kick + immediate unban so the user can re-join after purchasing again.

---

## 12. Languages & Custom Messages

### Supported Languages

| Code | Language |
|---|---|
| `en` | English |
| `si` | සිංහල (Sinhala) |

Users select their language on first `/start`. Their preference is saved per `user_id`.

### Customizing Messages

Go to **Dashboard → Messages**. Every text string in the bot can be overridden per language, including:

- Welcome screen text
- Account-ready delivery message
- All buttons labels, prompts, and error messages

### Account-Ready Message Placeholders

When editing the account-ready template, these placeholders are replaced:

| Placeholder | Value |
|---|---|
| `{order_id}` | Order ID |
| `{package_name}` | Package name |
| `{gb_limit}` | Data limit in GB |
| `{location_name}` | Location name |
| `{port}` | Panel port |
| `{protocol}` | VLESS / VMess / Trojan / Shadowsocks |
| `{username}` | 3x-ui client email/username |
| `{expiry_date}` | Formatted expiry date |
| `{subscription_link}` | Full subscription URI |

---

## 13. Payment Methods

Go to **Dashboard → Payment Methods** to add methods.

### Bank Transfer

| Field | Description |
|---|---|
| Bank Name | e.g., "People's Bank" |
| Account Name | Name on account |
| Account Number | Bank account number |

### eZcash / mCash

| Field | Description |
|---|---|
| Mobile Number | Registered mobile number |

> **Note:** eZcash orders automatically add a **+40 LKR service fee** to the displayed total.

### Crypto

| Field | Description |
|---|---|
| Crypto Type | e.g., "USDT (TRC20)" |
| Wallet Address | Recipient wallet address |

---

## 14. Stripe Integration

Stripe support is included but **disabled by default**. To enable:

1. Uncomment `stripe>=8.0.0` in `requirements.txt` and run `pip install stripe`
2. Set environment variables:
   ```
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   BOT_WEBHOOK_URL=https://yourdomain.com
   ```
3. Set `stripe_enabled: true` in `config.json`

**Capabilities:**
- Creates Stripe Checkout Sessions per order (1-hour expiry)
- Webhook handler for `checkout.session.completed` events
- Auto-marks orders `stripe_verified: true` on payment
- Supports full and partial refunds via `create_refund()`

---

## 15. Firebase Storage

Firebase Firestore is **optional** but recommended for production (survives restarts without losing config).

### Setup

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a project → enable **Firestore Database**
3. Project Settings → Service Accounts → Generate new private key → save as `firebase-credentials.json` in the project folder
4. Run migration once: `python migrate_to_firebase.py`

### Storage Strategy

| Action | What Happens |
|---|---|
| `load_config()` | Reads from Firestore first; falls back to `config.json` |
| `save_config()` | Always writes `config.json`; also writes to Firestore if available |

Even with Firebase active, a local `config.json` backup is always maintained.

### Serverless / Cloud Deployment

Instead of a credentials file, set the `FIREBASE_CREDENTIALS_JSON` environment variable to the full JSON string of your service account credentials.

---

## 16. System Settings Reference

Available at **Dashboard → System Settings**.

### Channels

| Field | Purpose |
|---|---|
| Premium Channel ID | Telegram channel where buyers get access |
| Backup Channel ID | Receives account-ready logs and panel DB backups |
| Panel Backup DB Path | Local path to `x-ui.db` file for backups |

### Referral & Coupon Controls

| Field | Default | Purpose |
|---|---|---|
| Referral Claims Status | On | Master toggle for code claiming |
| Referral Claim Limit | 3 | Max claims allowed per window per user |
| Claim Window (minutes) | 60 | Duration of the rate-limit window |
| Admin Coupon Cooldown | 60 min | Cooldown after a user hits the claim limit |
| Default Per-Code Max Redemptions | 0 | 0 = unlimited; >0 caps how many times any code is claimed |
| Minimum Order Amount | 0 | Discounts only activate above this total |

### Receipt Verification

| Field | Default | Purpose |
|---|---|---|
| Amount Match Tolerance % | 2 | How closely extracted amount must match order total |
| Transaction Reference Regex | (empty) | Custom regex for tx reference extraction |

### Provisioning

| Field | Default | Purpose |
|---|---|---|
| Safe Provision Queue | Off | Process one provision request at a time |
| Unlimited Style Creation | Off | Use protocol-aware panel payload builder |
| Auto Panel Failover | On | Try backup panel if primary fails |
| Max Provision Attempts | 5 | Retries before marking provision as failed |

### Maintenance Mode

| Field | Default | Purpose |
|---|---|---|
| Maintenance Mode | Off | Blocks all non-admin bot interactions |
| Banner Text | "Bot is under development." | Message shown to users during maintenance |

### Custom Packages

| Field | Default | Purpose |
|---|---|---|
| Custom Packages toggle | Off | Show custom GB/days option in purchase flow |
| Price Per GB | 2.0 | Cost per 1 GB |
| Price Per Day | 5.0 | Cost per 1 day |
| Min / Max GB | 10 / 1000 | Range user can input |
| Min / Max Days | 1 / 365 | Range user can input |

---

## 17. Deployment

### Heroku / Railway

Two processes defined in `Procfile`:

```
worker: python bot.py
web: python admin_dashboard.py
```

Set all required environment variables in the platform dashboard.

### Linux (systemd)

Create `/etc/systemd/system/v2ray-bot.service`:

```ini
[Unit]
Description=V2Ray Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=/root/Paid-bot
ExecStart=/root/Paid-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
EnvironmentFile=/root/Paid-bot/.env

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/v2ray-dashboard.service`:

```ini
[Unit]
Description=V2Ray Admin Dashboard
After=network.target

[Service]
User=root
WorkingDirectory=/root/Paid-bot
ExecStart=/root/Paid-bot/venv/bin/python admin_dashboard.py
Restart=always
RestartSec=10
EnvironmentFile=/root/Paid-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable v2ray-bot v2ray-dashboard
sudo systemctl start v2ray-bot v2ray-dashboard
sudo systemctl status v2ray-bot
```

### Nginx Reverse Proxy (dashboard)

```nginx
server {
    listen 80;
    server_name dashboard.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 18. Environment Variables

These can be set in a `.env` file or as system environment variables.

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes (or in config.json) | Bot API token |
| `FIREBASE_CREDENTIALS_JSON` | No | Full Firebase service account JSON string |
| `BOT_CONFIG_PATH` | No | Override path to config.json |
| `PREMIUM_CHANNEL_ID` | No | Override premium channel ID |
| `BACKUP_CHANNEL_ID` | No | Override backup channel ID |
| `PANEL_BACKUP_DB_PATH` | No | Override panel DB backup path |
| `ENABLE_SAFE_PROVISION_QUEUE` | No | `true` to force single-worker queue |
| `ENABLE_UNLIMITED_CREATION_FLOW` | No | `true` to force protocol-aware creation |
| `ENABLE_AUTO_PANEL_FAILOVER` | No | `true` to force panel failover |
| `PROVISION_MAX_ATTEMPTS` | No | Override provision retry limit |
| `STRIPE_SECRET_KEY` | No | Stripe secret key (when Stripe enabled) |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook signing secret |
| `BOT_WEBHOOK_URL` | No | Public HTTPS URL for Stripe success redirect |
| `PORT` | No | Dashboard port (default `5000`) |
| `SECRET_KEY` | No | Flask session secret key |

---

## 19. Troubleshooting

### Bot not responding

- Check `python bot.py` is still running (`systemctl status v2ray-bot`)
- Verify `telegram_bot_token` in config is correct
- Make sure no other process is running the same bot token

### Dashboard login code not working

- Send `/active CODE` from a Telegram account that is in `admin_ids`
- Codes are case-sensitive
- Each code is consumed after one use — generate a new one by refreshing the login page

### Orders not being provisioned

- Check `provision_requests` list in config.json is being processed (look at bot logs)
- Verify panel URL, username, and password in config are correct
- Test panel connectivity: visit the panel URL directly in a browser
- Check `provision_max_attempts` — if exceeded, order shows `status: failed`; use **Regenerate** from dashboard

### 3x-ui panel API errors

- Ensure the panel URL ends with the subpath (e.g., `/F7oNktbdVuSZD2Mx9m/`)
- Enable `unlimited_style_creation_enabled` in System Settings for better compatibility
- Check `auto_panel_failover_enabled` is on if you have a backup panel
- Make sure the inbound exists and `inbound_tag` in the location matches the inbound tag in the panel

### Receipt OCR not working

- Install `pip install Pillow pytesseract` and the Tesseract binary
- If deps are missing, OCR buttons are silently disabled — verify in server logs
- OCR works best on clear, high-resolution images

### Referral codes not applying

- Make sure `referrals_enabled = true` in System Settings
- Check the user hasn't exceeded `referral_claim_limit` for the current window
- Verify `coupon_min_order_amount` isn't set too high
- Check the code's `max_uses` hasn't been reached (`/refstats`)

### Firebase not connecting

- Confirm `firebase-credentials.json` exists and is valid service account JSON
- Or set `FIREBASE_CREDENTIALS_JSON` env variable
- The bot will automatically fall back to `config.json` if Firebase is unavailable

### Premium channel invite not sending

- Set `premium_channel_id` in System Settings
- Make sure the bot is an **Administrator** in the premium channel with the ability to invite users
- Invites are per-user, one-time use only

### Users not removed from channel at expiry

- Check `premium_channel_id` is set
- The bot must be an admin in the channel with **Ban Members** permission
- Removal runs daily at 00:10 (Asia/Colombo). Check bot logs for `remove_expired_members` output
- Removal only triggers if ≥ 33 days have passed since approval AND account is expired
