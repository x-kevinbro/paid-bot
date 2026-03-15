# 🚀 V2Ray Sales Bot - Complete Step-by-Step Deployment Guide

**Version:** 1.0  
**Last Updated:** February 2026  
**Status:** ✅ Production Ready

---

## 📋 Quick Navigation

- **[Beginner?](#-complete-setup-from-zero)** → Start here if this is your first time
- **[Already have bot?](#-add-firebase-to-existing-bot)** → Jump to Firebase setup
- **[Deploy to server?](#-production-deployment-linux)** → Go to production section
- **[Using WSL?](#-running-with-wsl)** → Windows + Linux guide
- **[Custom domain?](#-setup-custom-domain-for-dashboard)** → Admin dashboard with domain

---

## 🎯 Complete Setup from Zero

Follow these steps in order. Each step builds on the previous one.

### STEP 1: Get Telegram Bot Token (5 minutes)

1. Open Telegram and search for **@BotFather**
2. Send message: `/newbot`
3. Follow the prompts:
   - Enter bot name (e.g., "PrimeV2ray Bot")
   - Enter bot username (e.g., "primelkv2ray_bot")
4. Copy the API token you receive
5. Save it somewhere safe - you'll need it soon

**Example token:** `123456789:ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890`

---

### STEP 2: Download & Install Python (5 minutes)

**Windows:**
1. Go to [python.org](https://www.python.org/downloads)
2. Download Python 3.10 or higher
3. Run installer
4. ✅ **IMPORTANT:** Check "Add Python to PATH"
5. Click Install Now
6. Wait for completion

**Verify installation:**
```bash
python --version
```

Should show: `Python 3.10.x` or higher

---

### STEP 3: Clone or Extract Project (2 minutes)

**Option A: Clone with Git**
```bash
git clone https://github.com/your-username/multi-panel-bot.git
cd multi-panel-bot
```

**Option B: Extract ZIP**
1. Download project ZIP
2. Extract to folder: `C:\Users\YourName\Music\multi-panel-bot`
3. Open terminal in that folder

---

### STEP 4: Create Python Virtual Environment (3 minutes)

A virtual environment keeps dependencies isolated.

apt install python3.10-venv

```bash
# Create virtual environment
python3 -m venv venv

# Activate it (Windows)
.\venv\Scripts\activate

# Activate it (macOS/Linux)
source venv/bin/activate
```

**You should see** `(venv)` at the start of your terminal line.

---

### STEP 5: Install Dependencies (5 minutes)

```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Install all packages
pip install -r requirements.txt
```

**Wait for completion.** This downloads ~200MB of packages.

**Verify installation:**
```bash
python -c "import aiogram, firebase_admin, flask; print('✅ All packages installed')"
```

---

### STEP 6: Configure Bot Settings (10 minutes)

Edit `config.json` with your details:

```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
  "admin_ids": [YOUR_TELEGRAM_ID],
  "safe_provision_queue_enabled": false,
  "unlimited_style_creation_enabled": false,
  
  "packages": [
    {
      "id": "basic_1month",
      "name": "Basic 1 Month",
      "price": 50,
      "traffic": "500GB",
      "expiry_days": 30
    }
  ],
  
  "locations": [
    {
      "id": "us",
      "name": "🇺🇸 United States",
      "panels": ["panel1"]
    }
  ],
  
  "panels": [
    {
      "id": "panel1",
      "name": "Main Panel",
      "host": "your-panel.com",
      "port": 443,
      "username": "admin@example.com",
      "password": "your_password",
      "inbound_id": 1
    }
  ],
  
  "payment_details": {
    "methods": [
      {
        "id": "bank",
        "type": "Bank Transfer",
        "account_holder": "Your Name",
        "account_number": "1234567890",
        "bank_name": "Your Bank"
      }
    ]
  }
}
```

Optional: set `ENABLE_SAFE_PROVISION_QUEUE=true` in environment variables to force safe single-worker provisioning mode without editing config.

Optional: set `ENABLE_UNLIMITED_CREATION_FLOW=true` in environment variables to enable Unlimited Data style protocol-aware client payload creation (legacy creation remains fallback).

**Get your Telegram ID:**
1. Send any message to bot
2. Look for "User ID:" in bot logs, OR
3. Use online tool: search "get telegram id" + send message to @userinfobot

---

### STEP 7: Create Firebase Project (10 minutes)

Firebase is a cloud database. Your data syncs automatically.

**Step 1: Create Project**
1. Go to [Firebase Console](https://console.firebase.google.com)
2. Click "Add project"
3. Enter project name (e.g., "V2Ray Bot")
4. Accept terms
5. Click "Create project"
6. Wait 1-2 minutes for setup

**Step 2: Enable Firestore**
1. In left menu, click "Build" → "Firestore Database"
2. Click "Create database"
3. Choose location closest to you
4. Click "Next"
5. Start in **production mode** (or test mode for testing)
6. Click "Create"
7. Wait for setup to complete

**Step 3: Create Service Account**
1. Click gear icon ⚙️ → "Project Settings"
2. Go to "Service Accounts" tab
3. Click "Generate New Private Key"
4. A JSON file downloads automatically
5. Save it as `firebase-credentials.json` in your bot folder

**Verify:** The file should be in:
```
C:\Users\YourName\Music\multi-panel-bot\firebase-credentials.json
```

---

### STEP 8: Test Bot Locally (5 minutes)

```bash
# Make sure (venv) shows in terminal
# Run the bot
python bot.py
```

**You should see:**
```
INFO:firebase_db:✅ Firebase initialized successfully
INFO:__main__:🔥 Using Firebase for data storage
INFO:__main__:🤖 V2Ray Sales Bot starting...
INFO:aiogram.dispatcher:Start polling
```

**If you see Firebase error**, check:
- ✅ `firebase-credentials.json` exists in the folder
- ✅ Firebase Firestore database is enabled
- ✅ No typos in `config.json`

**Test in Telegram:**
1. Open Telegram
2. Search for your bot (e.g., @primelkv2ray_bot)
3. Send `/start`
4. Should see welcome message
5. Check terminal for "New user" message

---

### STEP 9: Set Up Admin Dashboard (5 minutes)

Open **another terminal window** and run:

```bash
# Navigate to project folder
cd C:\Users\YourName\Music\multi-panel-bot

# Activate virtual environment
.\venv\Scripts\activate

# Run dashboard
python admin_dashboard.py
```

**You should see:**
```
🔥 Admin Dashboard using Firebase for data storage
 * Running on http://0.0.0.0:5000
 * Running on http://127.0.0.1:5000
```

**Access dashboard:**
1. Open your browser
2. Go to: `http://localhost:5000`
3. You'll see login page

**Login to dashboard:**
1. In Telegram, send your bot: `/active`
2. Bot replies with a code (e.g., "ABC123")
3. Paste code on dashboard login page
4. Click "Login"
5. You're in! 🎉

**What you can do:**
- ✅ View pending orders
- ✅ Approve/reject purchases
- ✅ Add/edit payment methods
- ✅ Manage users
- ✅ View real-time updates

---

### STEP 10: Migrate Data to Firebase (2 minutes)

This uploads your `config.json` to Firebase cloud:

```bash
# Make sure (venv) is activated
python migrate_to_firebase.py
```

**You'll see:**
```
1. Checking Firebase status...
   ✓ Firebase initialized: True
   
2. Loading current configuration...
   • Packages: 3
   • Locations: 2
   • Panels: 2
   
3. Ready to migrate

Proceed with migration? (yes/no): yes

✅ SUCCESS: Successfully migrated 18 config keys to Firebase
```

**What happened:**
- All your settings uploaded to Firebase
- `config.json` kept as local backup
- Bot now uses cloud database
- Changes in dashboard auto-sync to Firebase

---

## ✅ You're Done! 

Your bot is now:
- ✅ Running locally
- ✅ Connected to Telegram
- ✅ Using Firebase cloud database
- ✅ Admin dashboard accessible
- ✅ Ready for testing and sales

---

## 🔄 Add Firebase to Existing Bot

Already running the bot without Firebase? Here's how to add it:

### Step 1: Get Firebase Credentials

Follow **STEP 7** from above to create Firebase project and download `firebase-credentials.json`.

Place it in your bot folder.

### Step 2: Install Firebase Package

```bash
.\venv\Scripts\activate
pip install firebase-admin>=6.4.0
```

### Step 3: Run Migration


## 🔒 Protecting Code (Best Practical Option)

```bash

python migrate_to_firebase.py

```



### Step 4: Restart Bot

```bash
python bot.py
```



You should see:
```
INFO:firebase_db:✅ Firebase initialized successfully
INFO:__main__:🔥 Using Firebase for data storage
```


---


## 🌐 Production Deployment (Linux)

For running on a real server 24/7.



### Prerequisites

- VPS/Server with Ubuntu 20.04+
- SSH access

- Domain name (optional but recommended)

- ✅ Ships as compiled executables
- ✅ Users don’t need Python installed

### Complete Setup

- ❌ Templates and config files may still be visible inside EXE

**1. SSH into server:**

- **Keep Firebase credentials off the server** or inject at runtime
- **Use GitHub private repo** to control access

```

**2. Update system:**
```bash
sudo apt update && sudo apt upgrade -y
```

**3. Install Python:**
```bash
sudo apt install -y python3.10 python3-pip python3-venv git
```

**4. Clone project:**
```bash
git clone https://github.com/your-username/multi-panel-bot.git
cd multi-panel-bot
```

**5. Setup Python:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**6. Copy config files:**
```bash
# From your computer:
scp config.json user@server.com:~/multi-panel-bot/
scp firebase-credentials.json user@server.com:~/multi-panel-bot/
```

**7. Test on server:**
```bash
# SSH into server
ssh user@server.com
cd multi-panel-bot
source venv/bin/activate
python bot.py
```

Should show Firebase connected.

**8. Install systemd services:**

Create `/etc/systemd/system/v2ray-bot.service`:

```bash
sudo nano /etc/systemd/system/v2ray-bot.service
```

Paste this:
```ini
[Unit]
Description=V2Ray Sales Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Paid-bot
ExecStart=/root/Paid-bot/venv/bin/python /root/Paid-bot/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+X` → `Y` → `Enter`

Create `/etc/systemd/system/v2ray-dashboard.service`:

```bash
sudo nano /etc/systemd/system/v2ray-dashboard.service
```

Paste:
```ini
[Unit]
Description=V2Ray Sales Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Paid-bot
ExecStart=/root/Paid-bot/venv/bin/python /root/Paid-bot/admin_dashboard.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+X` → `Y` → `Enter`

**9. Enable and start services:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable v2ray-bot v2ray-dashboard
sudo systemctl start v2ray-bot v2ray-dashboard
```

**10. Verify services running:**

```bash
sudo systemctl status v2ray-bot
sudo systemctl status v2ray-dashboard
```

Both should show: **active (running)**

**11. View logs:**

```bash
# Bot logs
sudo journalctl -u v2ray-bot -f

# Dashboard logs
sudo journalctl -u v2ray-dashboard -f

# Last 50 lines
sudo journalctl -u v2ray-bot -n 50
```

**12. Setup Nginx Reverse Proxy (Optional)**

Access dashboard via domain:

```bash
sudo apt install -y nginx
sudo nano /etc/nginx/sites-available/dashboard
```

Paste:
```nginx
server {
    listen 448;
    server_name dashboard.uptunnel.dev;

    location / {
        proxy_pass http://143.198.93.106:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

Access at: `http://dashboard.example.com`

**13. Add HTTPS (Free):**

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d dashboard.example.com
```

Auto-renews every 90 days.

---

## 🐧 Running with WSL

Use Windows with Linux terminal.

### Install WSL

**Windows 11/10 (Build 19041+):**
```powershell
wsl --install
```

Restart your computer.

### Setup in WSL

```bash
# Open WSL terminal
wsl

# Update packages
sudo apt update && sudo apt install -y python3-pip python3-venv git

# Clone project
cd ~
git clone https://github.com/your-username/multi-panel-bot.git
cd multi-panel-bot

# Setup Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy config from Windows
cp /mnt/c/Users/YourName/Music/Paid-bot/config.json ./
cp /mnt/c/Users/YourName/Music/Paid-bot/firebase-credentials.json ./
```

### Run in WSL

**Terminal 1 - Bot:**
```bash
source venv/bin/activate
python bot.py
```

**Terminal 2 - Dashboard:**
```bash
source venv/bin/activate
python admin_dashboard.py
```

**Access from Windows browser:**
```
http://localhost:5000
```

### Keep Running After Terminal Close

```bash
# Install screen
sudo apt install -y screen

# Start bot in background
screen -d -m -S bot bash -c 'cd ~/multi-panel-bot && source venv/bin/activate && python bot.py'

# Start dashboard
screen -d -m -S dashboard bash -c 'cd ~/multi-panel-bot && source venv/bin/activate && python admin_dashboard.py'

# List running screens
screen -ls

# Reattach to bot
screen -r bot
```

---

## 🌐 Setup Custom Domain for Dashboard

Run your admin dashboard on a custom domain (e.g., `dashboard.example.com` instead of `localhost:5000`).

### What You Need

1. **Domain name** - Buy from GoDaddy, Namecheap, etc. (~$1-10/year)
2. **Server with public IP** - VPS on Vultr, DigitalOcean, Linode, etc.
3. **SSH access to server** - To install Nginx and certificates

### Option 1: Local Development with Domain (Windows/Mac)

Test dashboard on a custom domain locally without a real server.

**Edit Windows hosts file:**

```
C:\Windows\System32\drivers\etc\hosts
```

Add this line (replace example.local with your desired domain):

```
127.0.0.1    dashboard.local
127.0.0.1    admin.local
127.0.0.1    panel.local
```

Save file (requires administrator access).

**Run dashboard:**

```bash
python admin_dashboard.py
```

**Access in browser:**

```
http://dashboard.local:5000
http://admin.local:5000
```

No additional configuration needed - it just maps the domain to localhost!

---

### Option 2: Production Domain Setup (Linux Server)

Run dashboard on a real domain with HTTPS and SSL certificate.

#### Prerequisites

- Domain registered and available
- Server with Ubuntu 20.04+
- SSH access

#### Step 1: Point Domain to Server

1. Buy domain (e.g., example.com)
2. Go to domain registrar's DNS settings
3. Create/update A record:
   - **Type:** A
   - **Name:** dashboard (or @)
   - **Value:** Your server's IP address
4. Wait 5-15 minutes for DNS to propagate

**Verify DNS is working:**

```bash
# On your computer
nslookup dashboard.example.com

# Should show your server IP
```

#### Step 2: Install Nginx on Server

SSH into your server:

```bash
ssh user@your-server.com
```

Install Nginx:

```bash
sudo apt update
sudo apt install -y nginx
```

#### Step 3: Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/dashboard
```

Paste this configuration (replace `dashboard.example.com` with your domain):

```nginx
upstream v2ray_dashboard {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    listen [::]:80;
    server_name dashboard.example.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name dashboard.example.com;

    # SSL certificates (will be added by certbot)
    ssl_certificate /etc/letsencrypt/live/dashboard.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard.example.com/privkey.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    # Proxy settings
    location / {
        proxy_pass http://v2ray_dashboard;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Save: `Ctrl+X` → `Y` → `Enter`

#### Step 4: Enable Nginx Site

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Should show: "test is successful"
```

#### Step 5: Install SSL Certificate (Free)

Use Let's Encrypt to get free HTTPS certificate:

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d dashboard.example.com
```

**Follow prompts:**
- Enter email address
- Accept terms (A)
- Choose redirect (2 - Redirect to HTTPS)

**Verify certificate:**

```bash
sudo certbot certificates
```

Auto-renews every 90 days.

#### Step 6: Start Nginx

```bash
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```

Should show: **active (running)**

#### Step 7: Access Dashboard

Open browser and go to:

```
https://dashboard.example.com
```

You should see the login page with a lock icon (HTTPS secure).

---

### Option 3: Subdomain Setup

Use subdomain instead of full domain (e.g., `admin.yoursite.com`).

**Same steps as Option 2, but:**

1. In DNS, create subdomain record:
   - **Type:** A
   - **Name:** admin
   - **Value:** Your server IP

2. In Nginx config, use:

```nginx
server_name admin.yoursite.com;
```

3. Run certbot:

```bash
sudo certbot --nginx -d admin.yoursite.com
```

---

### Option 4: Alternative Domains on Same Server

Run multiple services on same server with different domains:

**Create multiple Nginx configs:**

```bash
# Dashboard
sudo nano /etc/nginx/sites-available/dashboard

# Monitoring
sudo nano /etc/nginx/sites-available/monitor

# API
sudo nano /etc/nginx/sites-available/api
```

**Enable all:**

```bash
sudo ln -s /etc/nginx/sites-available/* /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

**Get SSL for all:**

```bash
sudo certbot --nginx -d dashboard.example.com -d monitor.example.com -d api.example.com
```

---

### Configuration File Locations

| Item | Location |
|------|----------|
| Dashboard code | `/home/ubuntu/multi-panel-bot/admin_dashboard.py` |
| Nginx config | `/etc/nginx/sites-available/dashboard` |
| SSL certificates | `/etc/letsencrypt/live/dashboard.example.com/` |
| Nginx logs | `/var/log/nginx/access.log` |
| | `/var/log/nginx/error.log` |

---

### Nginx Commands

```bash
# Check configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# View logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Stop Nginx
sudo systemctl stop nginx

# Start Nginx
sudo systemctl start nginx
```

---

### Troubleshooting Domain Setup

**Dashboard accessible but no HTTPS?**

```bash
# Check if certificate installed
sudo certbot certificates

# Renew if expired
sudo certbot renew --dry-run

# Force renewal
sudo certbot renew --force-renewal
```

**Domain not resolving?**

```bash
# Wait 15 minutes and test
nslookup dashboard.example.com

# Or use online DNS checker:
# https://dnschecker.org
```

**Can't access from browser?**

```bash
# Check if Nginx is running
sudo systemctl status nginx

# Check if port 443 is open
sudo netstat -tlnp | grep 443

# Test locally on server
curl https://localhost
```

**Certificate errors?**

```bash
# Check certificate details
sudo certbot show dashboard.example.com

# Revoke and regenerate
sudo certbot revoke -d dashboard.example.com
sudo certbot certonly --nginx -d dashboard.example.com
```

---

### Security Best Practices

1. **Enable HTTPS always** - Use certbot for free SSL
2. **Use strong passwords** - For admin dashboard login
3. **Firewall rules** - Only open necessary ports:
   ```bash
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow 80/tcp    # HTTP
   sudo ufw allow 443/tcp   # HTTPS
   sudo ufw enable
   ```
4. **Keep certificates updated** - Auto-renewal via certbot
5. **Backup configuration** - Before making changes:
   ```bash
   sudo cp /etc/nginx/sites-available/dashboard /etc/nginx/sites-available/dashboard.backup
   ```

---

### Performance Optimization

**Add caching to Nginx config:**

```nginx
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

**Gzip compression:**

```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript;
gzip_min_length 1000;
```

---

## 🐛 Troubleshooting

### Bot Won't Start

**Error:** `ModuleNotFoundError: No module named 'firebase_admin'`

```bash
# Reinstall packages
pip install -r requirements.txt
```

**Error:** `FileNotFoundError: config.json`

```bash
# Check file exists
ls -la config.json

# If missing, copy from backup or create new one
```

### Firebase Not Connecting

**Error:** `FileNotFoundError: firebase-credentials.json`

```bash
# Verify file location
ls -la firebase-credentials.json

# If missing, download from Firebase Console:
# 1. Go to Firebase Console
# 2. Project Settings > Service Accounts
# 3. Generate New Private Key
# 4. Save as firebase-credentials.json
```

### Dashboard Login Issues

**Code not working:**

1. Get fresh code: Send `/active` to bot
2. Use immediately (codes expire in 5 minutes)
3. Check your Telegram ID in `config.json` under `admin_ids`

### Telegram Bot Not Responding

1. Check token is correct in `config.json`
2. Restart bot: `Ctrl+C` then `python bot.py`
3. Check internet connection
4. Verify bot created properly in @BotFather

### Slow Performance

```bash
# Check resource usage
top

# Restart services
sudo systemctl restart v2ray-bot v2ray-dashboard
```

---

## 📦 Project Structure

```
multi-panel-bot/
├── bot.py                      # Main bot code
├── admin_dashboard.py          # Admin web interface
├── firebase_db.py              # Firebase integration
├── migrate_to_firebase.py      # Data migration tool
├── config.json                 # Settings (YOUR DATA)
├── firebase-credentials.json   # Firebase key (YOUR DATA)
├── requirements.txt            # Python packages
├── static/                     # CSS, JS files
│   ├── style.css
│   └── script.js
├── templates/                  # HTML pages
│   ├── login.html
│   ├── dashboard.html
│   └── payment_methods.html
└── venv/                       # Virtual environment
```

---

## 🤖 Bot Commands

### User Commands
- `/start` - Start the bot
- `/help` - Show available commands
- `/status` - Check order status

### Admin Commands
- `/active` - Get verification code for dashboard
- `/stats` - Show statistics
- `/ban USER_ID` - Ban a user

---

## 💡 Tips & Best Practices

1. **Always use virtual environment** - Keeps dependencies isolated
2. **Keep firebase-credentials.json safe** - Never share this file
3. **Backup config.json regularly** - Contains your settings
4. **Check logs often** - Logs show what's happening
5. **Test locally first** - Before deploying to server
6. **Monitor Firebase usage** - Free tier has limits

---

## 📝 File Locations

| File | Location | Purpose |
|------|----------|---------|
| bot.py | C:\Users\YourName\Music\Paid-bot | Main bot code |
| config.json | C:\Users\YourName\Music\Paid-bot | Bot settings |
| firebase-credentials.json | C:\Users\YourName\Music\Paid-bot | Cloud access |
| admin_dashboard.py | C:\Users\YourName\Music\Paid-bot | Admin interface |

---

## ✨ Next Steps

1. ✅ Complete setup
2. ✅ Test bot in Telegram
3. ✅ Add payment methods in dashboard
4. ✅ Test purchase flow
5. ✅ Deploy to server when ready
6. ✅ Monitor and maintain

---

## 📞 Support

**Issue checklist:**
- [ ] Read troubleshooting section
- [ ] Check logs for error messages
- [ ] Verify config.json is correct
- [ ] Ensure all files in correct location
- [ ] Try restarting bot/dashboard

---

**Ready to get started? Begin with [STEP 1](#step-1-get-telegram-bot-token-5-minutes)!**
