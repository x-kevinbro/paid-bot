# V2Ray Sales Bot 🚀

A complete Telegram bot for selling V2Ray accounts with automated payment approval and account creation.

## Features

✅ **Automated Sales Flow**
- Package selection (Starter, Pro, Premium, etc.)
- Data amount selection (10GB, 20GB, 50GB, etc.)
- Server location selection
- Payment details display

✅ **Payment Processing**
- Display payment methods (Bank Transfer, Crypto, etc.)
- Payment receipt upload (photo/document)
- Admin approval workflow

✅ **Automated Account Creation**
- Auto-create V2Ray clients on 3x-ui panel
- Send account details to customers
- 30-day subscription expiry

✅ **Admin Features**
- Pending order management
- Order approval/rejection
- Order statistics and history
- Receipt viewing

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow instructions to create your bot
4. Copy the bot token

### 3. Configure

Edit `config.json`:

```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
  "admin_ids": [YOUR_ADMIN_ID],
  "admin_password": "your_secure_password",
  "payment_details": {
    "method": "Bank Transfer / Crypto",
    "account_name": "Your Company",
    "account_number": "XXXXX",
    "bank_name": "Your Bank",
    "crypto_type": "BTC/ETH/USDT",
    "crypto_address": "Your_Address_Here"
  },
  "panels": [
    {
      "id": 1,
      "name": "Main Panel",
      "url": "https://your-panel.com:2053",
      "username": "admin",
      "password": "admin_password",
      "api_port": 54321
    }
  ]
}
```

### 4. Configure Packages & Locations

In `config.json`, customize:

**Packages:**
```json
"packages": [
  {
    "id": "starter",
    "name": "Starter",
    "base_price": 5.00,
    "description": "Light browsing"
  }
]
```

**GB Options:**
```json
"gb_options": [10, 20, 50, 100, 200, 500]
```

**Locations/Inbounds:**
```json
"locations": [
  {
    "id": "us_ny",
    "name": "🇺🇸 USA - New York",
    "inbound_tag": "INBOUND_US_NY",
    "panel_id": 1,
    "description": "Fast US server"
  }
]
```

### 5. Run Bot

```bash
python bot.py
```

## Usage Flow

### For Customers

1. **Start**: `/start`
2. **Select Package**: Choose Starter/Pro/Premium
3. **Select Data**: Choose GB amount
4. **Choose Location**: Select server location
5. **View Payment Details**: Bank/Crypto info shown
6. **Upload Receipt**: Send payment screenshot
7. **Confirmation**: Order waiting for approval

### For Admins

1. **Get Notified**: Receive new order alerts
2. **Review**: Click "View Order" to see details
3. **View Receipt**: Payment proof shown
4. **Approve**: Click "Approve" to create account
5. **Account Sent**: Customer gets V2Ray config

## Order States

- **pending** - Waiting for admin approval
- **approved** - Account created, sent to user
- **rejected** - Payment not approved

## Pricing Formula

```
Total Price = Base Package Price + (GB * Price per GB)
```

Example:
- Pro Package: $10.00
- 50GB Option: 50 × $0.50 = $25.00
- **Total: $35.00**

## Database

Orders stored in `config.json` under `pending_approvals`:

```json
{
  "order_id": "ORD_123456789_1707500000",
  "user_id": 123456789,
  "username": "customer_username",
  "package_id": "pro",
  "gb": 50,
  "location_id": "us_ny",
  "total_price": 35.00,
  "status": "pending",
  "receipt_file_id": "AgACAgIAAxkBAAI...",
  "created_at": "2026-02-03T10:30:00",
  "approved_at": null,
  "approved_by": null
}
```

## 3x-ui Integration

Bot integrates with 3x-ui panel to:

1. **Login**: Authenticate to panel
2. **Get Inbounds**: Fetch available inbounds
3. **Add Client**: Create new V2Ray client with:
   - Unique UUID
   - Customer email
   - Data limit
   - Expiry (30 days)
   - Enable/Disable state

## Admin Commands

- `/start` - Show main menu
- **✅ Approve Orders** - Review pending orders
- **📊 Orders Status** - See statistics

## Security

⚠️ **Important:**

- Keep `config.json` secure (contains panel credentials)
- Use strong admin password
- Use HTTPS for panel URLs
- Restrict file permissions: `chmod 600 config.json`
- Don't share credentials

## Customization

### Change Currency

Edit in `config.json`:
```json
"currency": "EUR"  // or USD, GBP, etc.
```

### Add More Packages

```json
"packages": [
  {
    "id": "ultra",
    "name": "Ultra",
    "base_price": 50.00,
    "description": "Unlimited everything"
  }
]
```

### Add More Locations

```json
"locations": [
  {
    "id": "jp_tokyo",
    "name": "🇯🇵 Japan - Tokyo",
    "inbound_tag": "INBOUND_JP_TOKYO",
    "panel_id": 1,
    "description": "Ultra-fast Asia connection"
  }
]
```

## Troubleshooting

**Bot doesn't respond:**
- Check bot token is correct
- Verify Python script is running
- Check internet connection

**Can't create accounts:**
- Verify panel credentials in config
- Check panel API is enabled
- Ensure inbound tags match your panel

**Admin not receiving notifications:**
- Check admin_ids in config
- Verify Telegram connection
- Check logs for errors

**Orders not approving:**
- Verify inbound_tag exists on panel
- Check panel API port (default 54321)
- Review panel logs

## File Structure

```
Paid-bot/
├── bot.py              # Main bot application
├── config.json         # Configuration & orders
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## Support

For issues:
1. Check the logs: `python bot.py 2>&1`
2. Verify panel connectivity
3. Test config.json syntax: `python -c "import json; json.load(open('config.json'))"`
4. Check Telegram API: `curl -s https://api.telegram.org/botTOKEN/getMe`

## Features Overview

| Feature | Status |
|---------|--------|
| Package Selection | ✅ |
| Data Amount Selection | ✅ |
| Location Selection | ✅ |
| Payment Display | ✅ |
| Receipt Upload | ✅ |
| Admin Approval | ✅ |
| Account Auto-Creation | ✅ |
| Account Delivery | ✅ |
| Order History | ✅ |
| Statistics | ✅ |

---

**Made with ❤️ for V2Ray Sales**

**Version**: 1.0  
**Last Updated**: February 3, 2026  
**Status**: ✅ Production Ready
