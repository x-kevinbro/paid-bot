import os
import asyncio
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from datetime import datetime
import random
import string
import base64
import io
import mimetypes
import requests
import re
from typing import Any, Optional

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None
# Import Firebase database module
from firebase_db import load_config, save_config, get_firebase_status, CONFIG_PATH as SHARED_CONFIG_PATH
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Change this to a random secret key
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True


def _parse_optional_panel_id(value: Any) -> Optional[int]:
    raw = str(value or '').strip()
    if not raw:
        return None
    return int(raw)


PLACEHOLDER_PATTERN = re.compile(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}")


def _extract_placeholders(text: str) -> set[str]:
    """Extract normalized placeholder names from a template string."""
    if not text:
        return set()
    return set(PLACEHOLDER_PATTERN.findall(str(text)))


def _validate_template_placeholders(field_name: str, text: str, allowed: set[str]) -> str | None:
    """Return an error message if template contains unsupported placeholders."""
    placeholders = _extract_placeholders(text)
    invalid = sorted(p for p in placeholders if p not in allowed)
    if invalid:
        allowed_text = ', '.join(sorted(allowed)) if allowed else 'none'
        invalid_text = ', '.join(invalid)
        return f"{field_name}: invalid placeholder(s): {invalid_text}. Allowed: {allowed_text}"
    return None


def _location_id_candidates(location_id: Any) -> list[str]:
    raw = str(location_id or '').strip()
    if not raw:
        return []

    candidates: list[str] = [raw]
    lower = raw.lower()
    if lower not in candidates:
        candidates.append(lower)

    if '_' in raw:
        parts = [p for p in raw.split('_') if p]
        for part in parts:
            if part not in candidates:
                candidates.append(part)
            part_lower = part.lower()
            if part_lower not in candidates:
                candidates.append(part_lower)

    return candidates


def _suggest_location_id(location_id: Any, locations: list[dict]) -> Optional[str]:
    if not locations:
        return None

    candidates = _location_id_candidates(location_id)
    if not candidates:
        return None

    existing_ids = [str(l.get('id', '')).strip() for l in locations]
    if any(c in existing_ids for c in candidates):
        return None

    for candidate in candidates:
        match = next((lid for lid in existing_ids if lid.lower() == candidate.lower()), None)
        if match:
            return match

    return None


def _get_order_receipt_bytes(order: dict, config: dict) -> tuple[bytes, str]:
    """Return receipt bytes and source label for OCR attempts."""
    b64 = order.get('receipt_base64')
    if b64:
        try:
            return base64.b64decode(b64), 'base64'
        except Exception:
            return b'', 'base64'

    url = order.get('receipt_url') or order.get('receipt_file_url')
    if url:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.content, 'url'
        except Exception:
            return b'', 'url'

    file_id = order.get('receipt_file_id') or order.get('telegram_file_id')
    if file_id:
        token = config.get('telegram_bot_token', '')
        if not token:
            return b'', 'telegram'
        data, _, _ = _fetch_telegram_file(token, file_id)
        return data or b'', 'telegram'

    return b'', 'none'


def _extract_amount_hint(text: str) -> Optional[str]:
    if not text:
        return None
    amount_pattern = re.compile(r"(?:LKR|Rs\.?|KR|USD|\$)?\s*([0-9]{2,}(?:[\.,][0-9]{1,2})?)", re.IGNORECASE)
    matches = amount_pattern.findall(text)
    if not matches:
        return None
    candidate = matches[0].replace(',', '')
    return candidate


def _extract_tx_reference(text: str, pattern: Optional[str] = None) -> Optional[str]:
    """Extract a transaction/payment reference number from text."""
    if not text:
        return None
    if pattern:
        try:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(0)
        except Exception:
            pass
    # Built-in patterns: common payment reference formats
    default_patterns = [
        r'\bTXN[0-9A-Z]{6,16}\b',
        r'\bREF[0-9A-Z]{6,16}\b',
        r'\b[A-Z]{2,4}[0-9]{8,16}\b',
        r'\b[0-9]{12,20}\b',
    ]
    for p in default_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def _verify_receipt(order: dict, config: dict, all_orders: list) -> dict:
    """Run automated receipt verification and return status + evidence dict."""
    tolerance_pct = float(config.get('receipt_amount_tolerance_percent', 2))
    tolerance = tolerance_pct / 100.0
    tx_pattern = (config.get('tx_ref_pattern') or '').strip()
    expected = float(order.get('total_price') or 0)

    text_parts = []
    if order.get('receipt_ocr_text'):
        text_parts.append(order['receipt_ocr_text'])
    if order.get('user_note'):
        text_parts.append(order['user_note'])
    combined = '\n'.join(text_parts)

    if not combined.strip():
        return {'status': 'unverified', 'amount_hint': None, 'tx_ref': None, 'notes': ['No text available for verification.']}

    amount_hint = _extract_amount_hint(combined)
    tx_ref = _extract_tx_reference(combined, tx_pattern or None)
    notes = []

    # Duplicate tx reference check across all orders
    if tx_ref:
        current_id = order.get('order_id')
        for other in all_orders:
            if other.get('order_id') == current_id:
                continue
            other_ref = other.get('receipt_tx_ref') or ''
            if other_ref and other_ref.upper() == tx_ref.upper():
                notes.append(f'Duplicate tx ref found in order {other["order_id"]}.')
                return {'status': 'duplicate', 'amount_hint': amount_hint, 'tx_ref': tx_ref, 'notes': notes}

    # Amount vs expected comparison
    if amount_hint and expected > 0:
        try:
            extracted = float(amount_hint.replace(',', ''))
            diff_ratio = abs(extracted - expected) / expected
            if diff_ratio <= tolerance:
                notes.append(f'Amount {extracted} matches expected {expected} (±{tolerance_pct:.0f}%).')
                status = 'match'
            else:
                notes.append(f'Amount {extracted} vs expected {expected} ({diff_ratio * 100:.1f}% off).')
                status = 'mismatch'
        except ValueError:
            notes.append('Could not parse extracted amount.')
            status = 'partial'
    elif tx_ref:
        notes.append('No amount extracted; tx ref present.')
        status = 'partial'
    else:
        notes.append('Insufficient data for full verification.')
        status = 'partial'

    return {'status': status, 'amount_hint': amount_hint, 'tx_ref': tx_ref, 'notes': notes}


# --- System Settings Route ---
@app.route('/system-settings', methods=['GET', 'POST'])
def system_settings():
    config = load_config()
    saved = False
    if request.method == 'POST':
        premium_channel_id = request.form.get('premium_channel_id', '').strip()
        backup_channel_id = request.form.get('backup_channel_id', '').strip()
        panel_backup_db_path = request.form.get('panel_backup_db_path', '').strip()
        config['premium_channel_id'] = premium_channel_id
        config['backup_channel_id'] = backup_channel_id
        config['panel_backup_db_path'] = panel_backup_db_path
        # Handle referral claims toggle (checkbox is checked if key exists in form)
        referrals_enabled = 'referrals_enabled' in request.form
        config['referrals_enabled'] = referrals_enabled

        try:
            referral_claim_limit = int(request.form.get('referral_claim_limit', 3))
            referral_claim_window_minutes = int(request.form.get('referral_claim_window_minutes', 60))
            admin_coupon_cooldown_minutes = int(request.form.get('admin_coupon_cooldown_minutes', 60))
            default_code_max_redemptions = int(request.form.get('default_code_max_redemptions', 0))
            coupon_min_order_amount = float(request.form.get('coupon_min_order_amount', 0))

            if referral_claim_limit < 1:
                referral_claim_limit = 1
            if referral_claim_window_minutes < 1:
                referral_claim_window_minutes = 1
            if admin_coupon_cooldown_minutes < 1:
                admin_coupon_cooldown_minutes = 1
            if default_code_max_redemptions < 0:
                default_code_max_redemptions = 0
            if coupon_min_order_amount < 0:
                coupon_min_order_amount = 0

            config['referral_claim_limit'] = referral_claim_limit
            config['referral_claim_window_minutes'] = referral_claim_window_minutes
            config['admin_coupon_cooldown_minutes'] = admin_coupon_cooldown_minutes
            config['default_code_max_redemptions'] = default_code_max_redemptions
            config['coupon_min_order_amount'] = coupon_min_order_amount
        except (ValueError, TypeError):
            flash('Referral/coupon limit settings must be valid numbers', 'error')
            return render_template('system_settings.html', config=config, saved=False)
        
        # Handle custom package settings
        custom_package_enabled = 'custom_package_enabled' in request.form
        config['custom_package_enabled'] = custom_package_enabled

        # Maintenance mode: block non-admin bot usage when enabled
        maintenance_mode = 'maintenance_mode' in request.form
        config['maintenance_mode'] = maintenance_mode
        config['maintenance_banner_text'] = request.form.get('maintenance_banner_text', '').strip()

        # Provisioning flow controls
        safe_provision_queue_enabled = 'safe_provision_queue_enabled' in request.form
        unlimited_style_creation_enabled = 'unlimited_style_creation_enabled' in request.form
        auto_panel_failover_enabled = 'auto_panel_failover_enabled' in request.form
        config['safe_provision_queue_enabled'] = safe_provision_queue_enabled
        config['unlimited_style_creation_enabled'] = unlimited_style_creation_enabled
        config['auto_panel_failover_enabled'] = auto_panel_failover_enabled

        try:
            provision_max_attempts = int(request.form.get('provision_max_attempts', 5))
            if provision_max_attempts < 1:
                provision_max_attempts = 1
            config['provision_max_attempts'] = provision_max_attempts
        except (ValueError, TypeError):
            flash('Provision max attempts must be a valid number', 'error')
            return render_template('system_settings.html', config=config, saved=False)
        
        # Update custom package pricing if provided
        if 'custom_package_pricing' not in config:
            config['custom_package_pricing'] = {}
        
        try:
            config['custom_package_pricing']['price_per_gb'] = float(request.form.get('price_per_gb', 2.0))
            config['custom_package_pricing']['price_per_day'] = float(request.form.get('price_per_day', 5.0))
            config['custom_package_pricing']['min_gb'] = int(request.form.get('min_gb', 10))
            config['custom_package_pricing']['max_gb'] = int(request.form.get('max_gb', 1000))
            config['custom_package_pricing']['min_days'] = int(request.form.get('min_days', 1))
            config['custom_package_pricing']['max_days'] = int(request.form.get('max_days', 365))
        except (ValueError, TypeError):
            flash('Invalid custom package pricing values', 'error')
            return render_template('system_settings.html', config=config, saved=False)
        
        # Receipt verification settings
        try:
            receipt_amount_tolerance_percent = float(request.form.get('receipt_amount_tolerance_percent', 2))
            receipt_amount_tolerance_percent = max(0.0, min(50.0, receipt_amount_tolerance_percent))
            config['receipt_amount_tolerance_percent'] = receipt_amount_tolerance_percent
        except (ValueError, TypeError):
            flash('Receipt tolerance must be a valid number', 'error')
            return render_template('system_settings.html', config=config, saved=False)
        config['tx_ref_pattern'] = request.form.get('tx_ref_pattern', '').strip()

        save_config(config)
        saved = True
    
    # Ensure referrals_enabled has a default value
    if 'referrals_enabled' not in config:
        config['referrals_enabled'] = True

    if 'referral_claim_limit' not in config:
        config['referral_claim_limit'] = 3

    if 'referral_claim_window_minutes' not in config:
        config['referral_claim_window_minutes'] = 60

    if 'admin_coupon_cooldown_minutes' not in config:
        config['admin_coupon_cooldown_minutes'] = 60

    if 'default_code_max_redemptions' not in config:
        config['default_code_max_redemptions'] = 0

    if 'coupon_min_order_amount' not in config:
        config['coupon_min_order_amount'] = 0
    
    # Ensure custom_package_enabled has a default value
    if 'custom_package_enabled' not in config:
        config['custom_package_enabled'] = False

    # Ensure maintenance_mode has a default value
    if 'maintenance_mode' not in config:
        config['maintenance_mode'] = False

    if 'maintenance_banner_text' not in config:
        config['maintenance_banner_text'] = 'Bot is under development.'

    # Ensure provisioning flow controls have default values
    if 'safe_provision_queue_enabled' not in config:
        config['safe_provision_queue_enabled'] = False

    if 'unlimited_style_creation_enabled' not in config:
        config['unlimited_style_creation_enabled'] = False

    if 'auto_panel_failover_enabled' not in config:
        config['auto_panel_failover_enabled'] = False

    if 'provision_max_attempts' not in config:
        config['provision_max_attempts'] = 5

    if 'receipt_amount_tolerance_percent' not in config:
        config['receipt_amount_tolerance_percent'] = 2

    if 'tx_ref_pattern' not in config:
        config['tx_ref_pattern'] = ''
    
    # Ensure custom_package_pricing has default values
    if 'custom_package_pricing' not in config:
        config['custom_package_pricing'] = {
            'price_per_gb': 2.0,
            'price_per_day': 5.0,
            'min_gb': 10,
            'max_gb': 1000,
            'min_days': 1,
            'max_days': 365
        }
    
    return render_template('system_settings.html', config=config, saved=saved)

# Firebase status
firebase_status = get_firebase_status()
if firebase_status['using_firebase']:
    print("🔥 Admin Dashboard using Firebase for data storage")
else:
    print("📁 Admin Dashboard using JSON file for data storage")

# Legacy CONFIG_PATH for compatibility
CONFIG_PATH = SHARED_CONFIG_PATH

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page with code verification via Telegram (no Jinja2)"""
    if request.method == 'POST':
        login_code = request.form.get('login_code')
        config = load_config()

        # Check if code is in verified codes
        verified_codes = config.get('verified_login_codes', [])
        if login_code in verified_codes:
            session['logged_in'] = True
            if config.get('admin_ids'):
                session['admin_id'] = config['admin_ids'][0]
            flash('Login successful!', 'success')

            # Remove used code
            verified_codes.remove(login_code)
            config['verified_login_codes'] = verified_codes
            save_config(config)

            return redirect(url_for('dashboard'))
        else:
            flash('Invalid or expired code!', 'error')

    # Generate a new login code for this session
    login_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    session['pending_code'] = login_code

    html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>Admin Access</title>
    <style>
        :root {{
            /* Light theme colors (default) */
            --bg-gradient-start: #667eea;
            --bg-gradient-end: #764ba2;
            --card-bg: rgba(255, 255, 255, 0.95);
            --text-primary: #0f172a;
            --text-secondary: #64748b;
            --text-tertiary: #334155;
            --accent-primary: #6366f1;
            --accent-secondary: #7c3aed;
            --input-bg: #f8fafc;
            --input-border: #e2e8f0;
            --code-bg: #f8fafc;
            --instructions-bg: #f0f4ff;
            --copy-status-text: #475569;
        }}

        [data-theme="dark"] {{
            /* Dark theme colors */
            --bg-gradient-start: #1e293b;
            --bg-gradient-end: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.95);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-tertiary: #cbd5e1;
            --accent-primary: #818cf8;
            --accent-secondary: #6366f1;
            --input-bg: #1e293b;
            --input-border: #334155;
            --code-bg: #0f172a;
            --instructions-bg: #1e293b;
            --copy-status-text: #94a3b8;
        }}

        * {{
            transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;
        }}

        html, body {{
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}

        .login-page {{
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);
            padding: 1.5rem;
            box-sizing: border-box;
        }}

        .theme-toggle {{
            position: absolute;
            top: 1.5rem;
            right: 1.5rem;
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            width: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.5rem;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10;
        }}

        .theme-toggle:hover {{
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.05);
        }}

        .login-card {{
            width: 100%;
            max-width: 360px;
            background: var(--card-bg);
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12);
            text-align: center;
        }}

        .login-header h1 {{
            font-size: 1.5rem;
            margin: 0 0 0.5rem 0;
            color: var(--text-primary);
            font-weight: 700;
        }}

        .login-header p {{
            color: var(--text-secondary);
            font-size: 0.85rem;
            margin: 0 0 1.25rem 0;
        }}

        .code-display {{
            background: var(--code-bg);
            border: 2px solid var(--accent-primary);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1.25rem;
            text-align: center;
        }}

        .code-label {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 0.75rem;
        }}

        .code-value {{
            font-size: 1.6rem;
            font-weight: 800;
            color: var(--accent-primary);
            font-family: \"Courier New\", monospace;
            letter-spacing: 0.2em;
            word-break: break-all;
        }}

        .copy-btn {{
            background: var(--accent-primary);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            font-size: 0.85rem;
            cursor: pointer;
            margin-top: 0.75rem;
        }}

        .copy-btn:hover {{
            opacity: 0.9;
        }}

        .copy-status {{
            margin-top: 0.5rem;
            font-size: 0.8rem;
            color: var(--copy-status-text);
            min-height: 1rem;
        }}

        .instructions {{
            background: var(--instructions-bg);
            border-left: 4px solid var(--accent-primary);
            padding: 0.85rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            text-align: left;
            font-size: 0.85rem;
            color: var(--text-tertiary);
            line-height: 1.6;
        }}

        .instructions code {{
            background: var(--code-bg);
            color: var(--accent-primary);
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-size: 0.8rem;
        }}

        .form-group {{
            text-align: left;
            margin-bottom: 1rem;
        }}

        .form-group label {{
            display: block;
            font-size: 0.9rem;
            color: var(--text-tertiary);
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}

        .form-group input {{
            width: 100%;
            padding: 0.75rem 0.9rem;
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 10px;
            color: var(--text-primary);
            font-size: 0.95rem;
            box-sizing: border-box;
        }}

        .submit-btn {{
            width: 100%;
            padding: 0.75rem 1rem;
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            box-shadow: 0 10px 20px rgba(99, 102, 241, 0.25);
        }}

        .submit-btn:hover {{
            opacity: 0.95;
        }}
    </style>
</head>
<body>
    <div class=\"login-page\">
        <button class=\"theme-toggle\" onclick=\"toggleTheme()\" title=\"Toggle theme\">
            <span id=\"themeIcon\">&#127769;</span>
        </button>
        <div class=\"login-card\">
            <div class=\"login-header\">
                <h1>&#128272; Admin Access</h1>
                <p>Telegram Bot Verification</p>
            </div>

            <div class=\"code-display\">
                <div class=\"code-label\">Your Login Code</div>
                <div class=\"code-value\" id=\"codeValue\">{login_code}</div>
                <button type=\"button\" class=\"copy-btn\" onclick=\"copyCode(event)\">Copy Code</button>
                <div class=\"copy-status\" id=\"copyStatus\"></div>
            </div>

            <div class=\"instructions\">
                <strong>How to verify:</strong>
                <ol>
                    <li>Copy your login code above</li>
                    <li>Open the Telegram bot</li>
                    <li>Send: <code>/active YOUR_CODE</code></li>
                    <li>Paste the code below and submit</li>
                </ol>
            </div>

            <form method=\"POST\">
                <div class=\"form-group\">
                    <label for=\"login_code\">Verification Code</label>
                    <input type=\"text\" id=\"login_code\" name=\"login_code\" placeholder=\"Enter the verified code\" required autofocus>
                </div>
                <button type=\"submit\" class=\"submit-btn\">Verify & Login</button>
            </form>
        </div>
    </div>

    <script>
    function copyCode(event) {{
        if (event) {{
            event.preventDefault();
            event.stopPropagation();
        }}
        const code = document.getElementById('codeValue').textContent.trim();

        if (navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(code).then(() => {{
                showCopyStatus('Code copied to clipboard.');
            }}).catch(() => {{
                fallbackCopy(code);
            }});
            return;
        }}

        fallbackCopy(code);
    }}

    function fallbackCopy(code) {{
        const temp = document.createElement('textarea');
        temp.value = code;
        temp.setAttribute('readonly', '');
        temp.style.position = 'absolute';
        temp.style.left = '-9999px';
        document.body.appendChild(temp);
        temp.select();
        try {{
            document.execCommand('copy');
            showCopyStatus('Code copied to clipboard.');
        }} catch (e) {{
            showCopyStatus('Copy failed. Please copy the code manually.');
        }}
        document.body.removeChild(temp);
    }}

    function showCopyStatus(message) {{
        const status = document.getElementById('copyStatus');
        if (!status) return;
        status.textContent = message;
        clearTimeout(window.__copyTimer);
        window.__copyTimer = setTimeout(() => {{
            status.textContent = '';
        }}, 2500);
    }}

    // Theme toggle functionality
    function toggleTheme() {{
        const html = document.documentElement;
        const currentTheme = html.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        
        html.setAttribute('data-theme', newTheme);
        localStorage.setItem('loginTheme', newTheme);
        updateThemeIcon(newTheme);
    }}

    function updateThemeIcon(theme) {{
        const icon = document.getElementById('themeIcon');
        if (icon) {{
            icon.innerHTML = theme === 'light' ? '&#127769;' : '&#9728;';
        }}
    }}

    // Load saved theme on page load
    (function() {{
        const savedTheme = localStorage.getItem('loginTheme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon(savedTheme);
    }})();
    </script>
</body>
</html>
"""

    return html


@app.route('/logout')
def logout():
    """Logout"""
    session.pop('logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    """Main dashboard"""
    config = load_config()
    
    # Count total packages across all ISPs
    total_isp_packages = sum(len(isp.get('packages', [])) for isp in config.get('isp_providers', []))
    
    stats = {
        'total_packages': len(config.get('packages', [])),
        'total_isps': len(config.get('isp_providers', [])),
        'total_isp_packages': total_isp_packages,
        'total_locations': len(config.get('locations', [])),
        'total_panels': len(config.get('panels', [])),
        'pending_orders': len([o for o in config.get('pending_approvals', []) if o.get('status') == 'pending']),
        'approved_orders': len([o for o in config.get('pending_approvals', []) if o.get('status') == 'approved']),
        'rejected_orders': len([o for o in config.get('pending_approvals', []) if o.get('status') == 'rejected']),
        'total_orders': len(config.get('pending_approvals', [])),
    }
    
    return render_template('dashboard.html', stats=stats, config=config)


# Add a link to system settings in the dashboard (optional, for navigation)


@app.route('/packages')
@login_required
def packages():
    """Manage packages"""
    config = load_config()
    return render_template('packages.html', packages=config.get('packages', []))


@app.route('/packages/add', methods=['POST'])
@login_required
def add_package():
    """Add new package"""
    config = load_config()
    
    new_package = {
        'id': request.form.get('id'),
        'name': request.form.get('name'),
        'price': float(request.form.get('price')),
        'gb': int(request.form.get('gb')),
        'description': request.form.get('description')
    }
    
    config['packages'].append(new_package)
    save_config(config)
    flash('Package added successfully!', 'success')
    return redirect(url_for('packages'))


@app.route('/packages/edit/<package_id>', methods=['POST'])
@login_required
def edit_package(package_id):
    """Edit package"""
    config = load_config()
    
    package_found = False
    for pkg in config['packages']:
        # Convert both to string for comparison to avoid type mismatch
        if str(pkg['id']) == str(package_id):
            pkg['name'] = request.form.get('name')
            pkg['price'] = float(request.form.get('price'))
            pkg['gb'] = int(request.form.get('gb'))
            pkg['description'] = request.form.get('description')
            package_found = True
            break
    
    if package_found:
        save_config(config)
        flash('Package updated successfully!', 'success')
    else:
        flash(f'Package with ID {package_id} not found!', 'error')
    
    return redirect(url_for('packages'))


@app.route('/packages/delete/<package_id>', methods=['POST'])
@login_required
def delete_package(package_id):
    """Delete package"""
    config = load_config()
    config['packages'] = [p for p in config['packages'] if p['id'] != package_id]
    save_config(config)
    flash('Package deleted successfully!', 'success')
    return redirect(url_for('packages'))


@app.route('/locations')
@login_required
def locations():
    """Manage locations"""
    config = load_config()
    locations_data = config.get('locations', [])
    location_issues = []

    for order in config.get('pending_approvals', []):
        order_id = order.get('order_id')
        location_id = order.get('location_id')
        if not order_id or not location_id:
            continue
        suggestion = _suggest_location_id(location_id, locations_data)
        if suggestion:
            location_issues.append({
                'order_id': order_id,
                'current_location_id': location_id,
                'suggested_location_id': suggestion,
                'status': order.get('status', 'unknown')
            })

    return render_template(
        'locations.html',
        locations=locations_data,
        panels=config.get('panels', []),
        location_issues=location_issues
    )


@app.route('/locations/fix-order-location/<order_id>', methods=['POST'])
@login_required
def fix_order_location(order_id):
    """Apply smart location id suggestion to an existing order."""
    config = load_config()
    suggested_location_id = request.form.get('suggested_location_id', '').strip()
    if not suggested_location_id:
        flash('Missing suggested location id.', 'error')
        return redirect(url_for('locations'))

    updated = False
    for order in config.get('pending_approvals', []):
        if str(order.get('order_id')) == str(order_id):
            order['location_id'] = suggested_location_id
            updated = True
            break

    if updated:
        save_config(config)
        flash(f'Updated order {order_id} location to {suggested_location_id}.', 'success')
    else:
        flash('Order not found for location fix.', 'error')

    return redirect(url_for('locations'))


@app.route('/locations/add', methods=['POST'])
@login_required
def add_location():
    """Add new location"""
    config = load_config()
    primary_panel_id = int(request.form.get('panel_id'))
    backup_panel_id = _parse_optional_panel_id(request.form.get('backup_panel_id'))
    if backup_panel_id == primary_panel_id:
        backup_panel_id = None
    
    new_location = {
        'id': request.form.get('id'),
        'name': request.form.get('name'),
        'inbound_tag': request.form.get('inbound_tag'),
        'panel_id': primary_panel_id,
        'backup_panel_id': backup_panel_id,
        'description': request.form.get('description')
    }
    
    config['locations'].append(new_location)
    save_config(config)
    flash('Location added successfully!', 'success')
    return redirect(url_for('locations'))


@app.route('/locations/edit/<location_id>', methods=['POST'])
@login_required
def edit_location(location_id):
    """Edit location"""
    config = load_config()
    primary_panel_id = int(request.form.get('panel_id'))
    backup_panel_id = _parse_optional_panel_id(request.form.get('backup_panel_id'))
    if backup_panel_id == primary_panel_id:
        backup_panel_id = None
    
    for loc in config['locations']:
        if loc['id'] == location_id:
            loc['name'] = request.form.get('name')
            loc['inbound_tag'] = request.form.get('inbound_tag')
            loc['panel_id'] = primary_panel_id
            loc['backup_panel_id'] = backup_panel_id
            loc['description'] = request.form.get('description')
            break
    
    save_config(config)
    flash('Location updated successfully!', 'success')
    return redirect(url_for('locations'))


@app.route('/locations/delete/<location_id>', methods=['POST'])
@login_required
def delete_location(location_id):
    """Delete location"""
    config = load_config()
    config['locations'] = [l for l in config['locations'] if l['id'] != location_id]
    save_config(config)
    flash('Location deleted successfully!', 'success')
    return redirect(url_for('locations'))


@app.route('/panels')
@login_required
def panels():
    """Manage panels"""
    config = load_config()
    return render_template('panels.html', panels=config.get('panels', []))


@app.route('/panels/add', methods=['POST'])
@login_required
def add_panel():
    """Add new panel"""
    config = load_config()
    
    new_panel = {
        'id': int(request.form.get('id')),
        'name': request.form.get('name'),
        'url': request.form.get('url'),
        'username': request.form.get('username'),
        'password': request.form.get('password'),
        'api_port': int(request.form.get('api_port')),
        'manual_address': request.form.get('manual_address', '')
    }
    
    config['panels'].append(new_panel)
    save_config(config)
    flash('Panel added successfully!', 'success')
    return redirect(url_for('panels'))


@app.route('/panels/edit/<int:panel_id>', methods=['POST'])
@login_required
def edit_panel(panel_id):
    """Edit panel"""
    config = load_config()
    
    for panel in config['panels']:
        if panel['id'] == panel_id:
            panel['name'] = request.form.get('name')
            panel['url'] = request.form.get('url')
            panel['username'] = request.form.get('username')
            panel['password'] = request.form.get('password')
            panel['api_port'] = int(request.form.get('api_port'))
            panel['manual_address'] = request.form.get('manual_address', '')
            break
    
    save_config(config)
    flash('Panel updated successfully!', 'success')
    return redirect(url_for('panels'))


@app.route('/panels/delete/<int:panel_id>', methods=['POST'])
@login_required
def delete_panel(panel_id):
    """Delete panel"""
    config = load_config()
    config['panels'] = [p for p in config['panels'] if p['id'] != panel_id]
    save_config(config)
    flash('Panel deleted successfully!', 'success')
    return redirect(url_for('panels'))


@app.route('/isps')
@login_required
def isps():
    """Manage ISP providers"""
    config = load_config()
    return render_template('isps.html', isps=config.get('isp_providers', []))


@app.route('/isps/add', methods=['POST'])
@login_required
def add_isp():
    """Add new ISP provider"""
    config = load_config()
    
    new_isp = {
        'id': request.form.get('id'),
        'name': request.form.get('name'),
        'description': request.form.get('description'),
        'packages': []
    }
    
    config['isp_providers'].append(new_isp)
    save_config(config)
    flash('ISP provider added successfully!', 'success')
    return redirect(url_for('isps'))


@app.route('/isps/edit/<isp_id>', methods=['POST'])
@login_required
def edit_isp(isp_id):
    """Edit ISP provider"""
    config = load_config()
    
    for isp in config['isp_providers']:
        if isp['id'] == isp_id:
            isp['name'] = request.form.get('name')
            isp['description'] = request.form.get('description')
            break
    
    save_config(config)
    flash('ISP provider updated successfully!', 'success')
    return redirect(url_for('isps'))


@app.route('/isps/delete/<isp_id>', methods=['POST'])
@login_required
def delete_isp(isp_id):
    """Delete ISP provider"""
    config = load_config()
    config['isp_providers'] = [i for i in config['isp_providers'] if i['id'] != isp_id]
    save_config(config)
    flash('ISP provider deleted successfully!', 'success')
    return redirect(url_for('isps'))


@app.route('/isps/<isp_id>/packages')
@login_required
def isp_packages(isp_id):
    """Manage packages for a specific ISP"""
    config = load_config()
    isp = next((i for i in config.get('isp_providers', []) if i['id'] == isp_id), None)
    if not isp:
        flash('ISP not found!', 'error')
        return redirect(url_for('isps'))
    return render_template('isp_packages.html', isp=isp)


@app.route('/isps/<isp_id>/packages/add', methods=['POST'])
@login_required
def add_isp_package(isp_id):
    """Add package to ISP"""
    config = load_config()
    
    for isp in config['isp_providers']:
        if isp['id'] == isp_id:
            if 'packages' not in isp:
                isp['packages'] = []
            
            new_package = {
                'id': request.form.get('id'),
                'name': request.form.get('name'),
                'sni': request.form.get('sni', ''),
                'port': int(request.form.get('port', 443)),
                'use_location_sni': request.form.get('use_location_sni') == 'on'
            }
            isp['packages'].append(new_package)
            break
    
    save_config(config)
    flash('Package added to ISP successfully!', 'success')
    return redirect(url_for('isp_packages', isp_id=isp_id))


@app.route('/isps/<isp_id>/packages/edit/<package_id>', methods=['POST'])
@login_required
def edit_isp_package(isp_id, package_id):
    """Edit ISP package"""
    config = load_config()
    
    for isp in config['isp_providers']:
        if isp['id'] == isp_id:
            for pkg in isp.get('packages', []):
                if pkg['id'] == package_id:
                    pkg['name'] = request.form.get('name')
                    pkg['sni'] = request.form.get('sni', '')
                    pkg['port'] = int(request.form.get('port', 443))
                    pkg['use_location_sni'] = request.form.get('use_location_sni') == 'on'
                    break
            break
    
    save_config(config)
    flash('Package updated successfully!', 'success')
    return redirect(url_for('isp_packages', isp_id=isp_id))


@app.route('/isps/<isp_id>/packages/delete/<package_id>', methods=['POST'])
@login_required
def delete_isp_package(isp_id, package_id):
    """Delete ISP package"""
    config = load_config()
    
    for isp in config['isp_providers']:
        if isp['id'] == isp_id:
            isp['packages'] = [p for p in isp.get('packages', []) if p['id'] != package_id]
            break
    
    save_config(config)
    flash('Package deleted successfully!', 'success')
    return redirect(url_for('isp_packages', isp_id=isp_id))


@app.route('/user-packages')
@login_required
def user_packages():
    """Manage user packages/apps"""
    config = load_config()
    return render_template('user_packages.html', user_packages=config.get('user_packages', []))


@app.route('/user-packages/add', methods=['POST'])
@login_required
def add_user_package():
    """Add new user package"""
    config = load_config()
    
    new_package = {
        'id': request.form.get('id'),
        'name': request.form.get('name')
    }
    
    if 'user_packages' not in config:
        config['user_packages'] = []
    
    config['user_packages'].append(new_package)
    save_config(config)
    flash('User package added successfully!', 'success')
    return redirect(url_for('user_packages'))


@app.route('/user-packages/edit/<package_id>', methods=['POST'])
@login_required
def edit_user_package(package_id):
    """Edit user package"""
    config = load_config()
    
    for pkg in config.get('user_packages', []):
        if pkg['id'] == package_id:
            pkg['name'] = request.form.get('name')
            break
    
    save_config(config)
    flash('User package updated successfully!', 'success')
    return redirect(url_for('user_packages'))


@app.route('/user-packages/delete/<package_id>', methods=['POST'])
@login_required
def delete_user_package(package_id):
    """Delete user package"""
    config = load_config()
    config['user_packages'] = [p for p in config.get('user_packages', []) if p['id'] != package_id]
    save_config(config)
    flash('User package deleted successfully!', 'success')
    return redirect(url_for('user_packages'))


@app.route('/orders')
@login_required
def orders():
    """View and manage orders"""
    config = load_config()
    all_orders = config.get('pending_approvals', [])
    
    # Sort by created_at descending
    all_orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    order_stats = {
        'pending': len([o for o in all_orders if (o.get('status') or '').lower() == 'pending']),
        'approved': len([o for o in all_orders if (o.get('status') or '').lower() == 'approved']),
        'rejected': len([o for o in all_orders if (o.get('status') or '').lower() == 'rejected']),
        'total': len(all_orders)
    }
    return render_template('orders.html', orders=all_orders, order_stats=order_stats)


def _fetch_telegram_file(token: str, file_id: str):
    """Fetch Telegram file bytes and metadata via Bot API using file_id"""
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id}, timeout=15)
        resp.raise_for_status()
        file_path = resp.json().get('result', {}).get('file_path')
        if not file_path:
            return b'', '', ''
        file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        f = requests.get(file_url, timeout=30)
        f.raise_for_status()
        guessed_mime = mimetypes.guess_type(file_path)[0] or ''
        header_mime = f.headers.get('Content-Type', '')
        content_type = guessed_mime or header_mime or 'application/octet-stream'
        filename = file_path.split('/')[-1] if '/' in file_path else file_path
        return f.content, content_type, filename
    except Exception:
        return b'', '', ''


@app.route('/orders/receipt/<order_id>')
@login_required
def order_receipt(order_id):
    """Serve or proxy the receipt for an order (supports url, file_url, base64, telegram file_id)"""
    config = load_config()
    orders = config.get('pending_approvals', [])
    order = next((o for o in orders if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        return ("Order not found", 404)

    # 1) Base64 inline
    b64 = order.get('receipt_base64')
    if b64:
        try:
            data = base64.b64decode(b64)
            return send_file(io.BytesIO(data), mimetype='image/png')
        except Exception:
            return ("Invalid base64 receipt", 400)

    # 2) Direct URL (image or file) -> proxy bytes to avoid CORS/mixed content
    url = order.get('receipt_url') or order.get('receipt_file_url')
    if url:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            # Try to use content-type header; default to application/octet-stream
            ctype = r.headers.get('Content-Type', 'application/octet-stream')
            return send_file(io.BytesIO(r.content), mimetype=ctype)
        except Exception:
            return redirect(url)

    # 3) Telegram file id
    file_id = order.get('receipt_file_id') or order.get('telegram_file_id')
    if file_id:
        token = config.get('telegram_bot_token', '')
        if not token:
            return ("Bot token not configured for Telegram receipt fetch", 500)
        data, detected_type, filename = _fetch_telegram_file(token, file_id)
        if not data:
            return ("Failed to fetch Telegram file", 502)
        saved_type = order.get('receipt_mime_type')
        content_type = detected_type or saved_type or 'application/octet-stream'
        return send_file(
            io.BytesIO(data),
            mimetype=content_type,
            download_name=order.get('receipt_file_name') or filename or 'receipt'
        )

    return ("No receipt attached", 404)


@app.route('/orders/resend/<order_id>', methods=['POST'])
@login_required
def resend_order(order_id):
    """Resend existing V2Ray config to buyer by queueing a resend request"""
    config = load_config()
    orders = config.get('pending_approvals', [])
    order = next((o for o in orders if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))
    if (order.get('status') or '').lower() != 'approved':
        flash('Only approved orders can be resent.', 'warning')
        return redirect(url_for('orders'))
    _enqueue_provision_request(config, order_id=order_id, req_type='resend')
    save_config(config)
    flash(f'Resend queued for order {order_id}.', 'success')
    return redirect(url_for('orders'))


def _enqueue_provision_request(config: dict, order_id: str, req_type: str = 'provision'):
    if 'provision_requests' not in config or not isinstance(config['provision_requests'], list):
        config['provision_requests'] = []
    config['provision_requests'].append({
        'request_id': f"{req_type}_{order_id}_{int(datetime.now().timestamp())}",
        'type': req_type,
        'order_id': order_id,
        'queue_strategy': 'safe_v1',
        'attempts': 0,
        'last_error': None,
        'status': 'queued',
        'created_at': datetime.now().isoformat()
    })


@app.route('/orders/revoke/<order_id>', methods=['POST'])
@login_required
def revoke_order(order_id):
    """Queue account revoke for approved/provisioned order."""
    config = load_config()
    orders = config.get('pending_approvals', [])
    order = next((o for o in orders if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))

    if (order.get('status') or '').lower() != 'approved':
        flash('Only approved orders can be revoked.', 'warning')
        return redirect(url_for('orders'))

    if not order.get('v2ray_config'):
        flash('No provisioned account found to revoke.', 'warning')
        return redirect(url_for('orders'))

    _enqueue_provision_request(config, order_id=order_id, req_type='revoke')
    save_config(config)
    flash(f'Revoke queued for order {order_id}.', 'success')
    return redirect(url_for('orders'))


@app.route('/orders/regenerate/<order_id>', methods=['POST'])
@login_required
def regenerate_order(order_id):
    """Queue account regeneration for approved order."""
    config = load_config()
    orders = config.get('pending_approvals', [])
    order = next((o for o in orders if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))

    if (order.get('status') or '').lower() != 'approved':
        flash('Only approved orders can be regenerated.', 'warning')
        return redirect(url_for('orders'))

    _enqueue_provision_request(config, order_id=order_id, req_type='regenerate')
    save_config(config)
    flash(f'Regeneration queued for order {order_id}.', 'success')
    return redirect(url_for('orders'))


@app.route('/orders/ocr/<order_id>', methods=['POST'])
@login_required
def ocr_order_receipt(order_id):
    """Attempt OCR extraction from uploaded receipt image."""
    config = load_config()
    orders = config.get('pending_approvals', [])
    order = next((o for o in orders if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))

    receipt_bytes, source = _get_order_receipt_bytes(order, config)
    if not receipt_bytes:
        flash(f'Could not fetch receipt bytes for OCR (source: {source}).', 'warning')
        return redirect(url_for('orders'))

    if Image is None or pytesseract is None:
        flash('OCR dependencies missing (Pillow/pytesseract). Install them on server to use OCR assist.', 'warning')
        return redirect(url_for('orders'))

    try:
        image = Image.open(io.BytesIO(receipt_bytes))
        extracted_text = pytesseract.image_to_string(image) or ''
    except Exception as e:
        flash(f'OCR failed: {e}', 'error')
        return redirect(url_for('orders'))

    cleaned_text = extracted_text.strip()
    if not cleaned_text:
        flash('OCR completed but no readable text detected.', 'warning')
        return redirect(url_for('orders'))

    amount_hint = _extract_amount_hint(cleaned_text)
    order['receipt_ocr_text'] = cleaned_text[:4000]
    order['receipt_ocr_amount_hint'] = amount_hint
    order['receipt_ocr_at'] = datetime.now().isoformat()
    save_config(config)

    preview = cleaned_text[:160].replace('\n', ' ')
    amount_part = f" Amount hint: {amount_hint}." if amount_hint else ''
    flash(f"OCR extracted text preview: {preview}{amount_part}", 'success')
    return redirect(url_for('orders'))

@app.route('/orders/verify/<order_id>', methods=['POST'])
@login_required
def verify_order_receipt(order_id):
    """Run automated receipt verification for an order."""
    config = load_config()
    all_orders = config.get('pending_approvals', [])
    order = next((o for o in all_orders if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))

    # Auto-run OCR first if not yet done and deps are available
    if not order.get('receipt_ocr_text') and Image is not None and pytesseract is not None:
        receipt_bytes, _ = _get_order_receipt_bytes(order, config)
        if receipt_bytes:
            try:
                image = Image.open(io.BytesIO(receipt_bytes))
                extracted_text = pytesseract.image_to_string(image) or ''
                if extracted_text.strip():
                    order['receipt_ocr_text'] = extracted_text.strip()[:4000]
                    order['receipt_ocr_amount_hint'] = _extract_amount_hint(extracted_text)
                    order['receipt_ocr_at'] = datetime.now().isoformat()
            except Exception:
                pass

    result = _verify_receipt(order, config, all_orders)
    order['receipt_verification_status'] = result['status']
    order['receipt_tx_ref'] = result['tx_ref']
    order['receipt_verification_at'] = datetime.now().isoformat()
    order['receipt_verification_notes'] = '; '.join(result['notes'])
    if result['amount_hint']:
        order['receipt_ocr_amount_hint'] = result['amount_hint']
    save_config(config)

    badge = {'match': '✓ Match', 'partial': '⚠ Partial', 'mismatch': '✗ Mismatch',
             'duplicate': '⚠ Duplicate', 'unverified': 'Unverified'}
    label = badge.get(result['status'], result['status'])
    detail = '; '.join(result['notes']) if result['notes'] else ''
    flash(f'Verification: {label}. {detail}', 'info' if result['status'] == 'match' else 'warning')
    return redirect(url_for('orders'))


@app.route('/orders/set-verification/<order_id>/<vstatus>', methods=['POST'])
@login_required
def set_verification_status(order_id, vstatus):
    """Manually override receipt verification status."""
    if vstatus not in ('manual_ok', 'manual_flag', 'unverified'):
        flash('Invalid verification status.', 'danger')
        return redirect(url_for('orders'))
    config = load_config()
    order = next((o for o in config.get('pending_approvals', []) if str(o.get('order_id')) == str(order_id)), None)
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))
    order['receipt_verification_status'] = vstatus
    order['receipt_verification_at'] = datetime.now().isoformat()
    order['receipt_verification_notes'] = f'Manually set to {vstatus} by admin.'
    save_config(config)
    flash(f'Verification status updated: {vstatus}', 'success')
    return redirect(url_for('orders'))


@app.route('/buyers')
@login_required
def buyers():
    """List buyers with details: name, telegram ID, package, date/time"""
    config = load_config()

    buyers_list = []
    excluded_packages = {'zoom','whatsapp','facebook','youtube','netflix','gaming','tiktok','instagram'}

    # Preferred source: orders/pending_approvals if present
    for o in config.get('pending_approvals', []):
        if o.get('status') in (None, 'approved', 'paid', 'completed', 'done', 'active'):
            buyer_name = o.get('buyer_name') or o.get('name') or o.get('user_name') or ''
            buyer_username = o.get('buyer_username') or o.get('username') or o.get('user_username') or ''
            telegram_id = o.get('telegram_id') or o.get('user_id') or o.get('buyer_id')
            pkg = o.get('package_id') or o.get('package') or o.get('package_name')
            # Exclude non-plan app entries
            pkg_norm = (str(pkg).strip().lower() if pkg is not None else '')
            if pkg_norm in excluded_packages:
                continue
            created = o.get('approved_at') or o.get('paid_at') or o.get('created_at') or ''
            # Normalize datetime display
            try:
                display_time = datetime.fromisoformat(created.replace('Z','+00:00')).strftime('%Y-%m-%d %H:%M:%S') if created else ''
            except Exception:
                display_time = created

            buyers_list.append({
                'buyer_name': buyer_name,
                'buyer_username': buyer_username,
                'telegram_id': telegram_id,
                'package_name': pkg,
                'purchased_at': display_time
            })

    # Fallback: user_packages entries could contain ownership data
    # Expecting entries like { user_id, user_name, package_id/name, purchased_at }
    for up in config.get('user_packages', []):
        buyer_name = up.get('user_name') or up.get('buyer_name') or ''
        buyer_username = up.get('buyer_username') or up.get('username') or up.get('user_username') or ''
        telegram_id = up.get('user_id') or up.get('telegram_id')
        pkg = up.get('package_id') or up.get('package_name') or up.get('name')
        # Exclude non-plan app entries
        pkg_norm = (str(pkg).strip().lower() if pkg is not None else '')
        if pkg_norm in excluded_packages:
            continue
        created = up.get('purchased_at') or up.get('created_at') or ''
        try:
            display_time = datetime.fromisoformat(created.replace('Z','+00:00')).strftime('%Y-%m-%d %H:%M:%S') if created else ''
        except Exception:
            display_time = created
        # Only add if not already represented from orders (by user+package+time)
        key = (telegram_id, pkg, created)
        if not any((b.get('telegram_id'), b.get('package_name'), b.get('purchased_at')) == key for b in buyers_list):
            buyers_list.append({
                'buyer_name': buyer_name,
                'buyer_username': buyer_username,
                'telegram_id': telegram_id,
                'package_name': pkg,
                'purchased_at': display_time
            })

    # Sort newest first
    buyers_list.sort(key=lambda x: x.get('purchased_at') or '', reverse=True)

    return render_template('buyers.html', buyers=buyers_list)


@app.route('/orders/approve/<order_id>', methods=['POST'])
@login_required
def approve_order(order_id):
    """Approve order with duplicate prevention and notifications"""
    config = load_config()

    if 'pending_approvals' not in config:
        flash('No orders found.', 'danger')
        return redirect(url_for('orders'))

    found = False
    for order in config['pending_approvals']:
        if order.get('order_id') == order_id:
            found = True
            current_status = (order.get('status') or 'pending').lower()
            if current_status != 'pending':
                approved_at = order.get('approved_at', 'unknown time')
                approved_by = order.get('approved_by_admin_id', 'unknown admin')
                flash(f'Order {order_id} already {current_status} (approved_at={approved_at}, by={approved_by}).', 'warning')
                return redirect(url_for('orders'))

            # Approve now
            order['status'] = 'approved'
            order['approved_at'] = datetime.now().isoformat()
            order['approved_by_admin_id'] = session.get('admin_id')
            
            # Generate referral code for user on first approved order
            user_id = order.get('user_id')
            if user_id:
                referral_codes = config.get('referral_codes', {})
                # Check if user already has a code
                has_code = any(code_info.get('user_id') == user_id for code_info in referral_codes.values())
                
                if not has_code:
                    # Generate new referral code
                    import random
                    import string
                    user_code = f"REF{user_id % 10000}{random.choice(string.ascii_uppercase)}{random.choice(string.ascii_uppercase)}"
                    referral_codes[user_code] = {
                        "user_id": user_id,
                        "created_at": datetime.now().isoformat(),
                        "discount_percent": 10,
                        "used_count": 0,
                        "used_by": []
                    }
                    config['referral_codes'] = referral_codes
                
                # If this order was referred (user used someone's code), create reward for referrer
                if order.get('applied_referral_code') and order.get('referrer_id'):
                    referral_rewards = config.get('referral_rewards', {})  # Maps user_id -> list of rewards
                    referrer_id = order.get('referrer_id')
                    
                    # Create pending reward: referrer gets 10% off next purchase
                    reward = {
                        "reward_id": f"rew_{order_id}_{int(datetime.now().timestamp())}",
                        "from_referral_code": order.get('applied_referral_code'),
                        "from_referred_user_id": user_id,
                        "discount_percent": 10,
                        "used": False,
                        "created_at": datetime.now().isoformat(),
                        "used_at": None,
                        "used_on_order_id": None
                    }
                    
                    if str(referrer_id) not in referral_rewards:
                        referral_rewards[str(referrer_id)] = []
                    
                    referral_rewards[str(referrer_id)].append(reward)
                    config['referral_rewards'] = referral_rewards

            # Queue provisioning so the bot can send config to buyer
            if 'provision_requests' not in config or not isinstance(config['provision_requests'], list):
                config['provision_requests'] = []
            config['provision_requests'].append({
                'request_id': f"prov_{order_id}_{int(datetime.now().timestamp())}",
                'order_id': order_id,
                'user_id': order.get('user_id') or order.get('telegram_id'),
                'buyer_username': order.get('buyer_username') or order.get('username'),
                'package_id': order.get('package_id') or order.get('package') or order.get('package_name'),
                'location_id': order.get('location_id'),
                'isp_id': order.get('isp_id'),
                'queue_strategy': 'safe_v1',
                'attempts': 0,
                'last_error': None,
                'created_at': datetime.now().isoformat(),
                'status': 'queued'
            })

            # Append admin notification entry
            if 'notifications' not in config or not isinstance(config['notifications'], list):
                config['notifications'] = []
            config['notifications'].append({
                'id': f"order_approved_{order_id}_{int(datetime.now().timestamp())}",
                'type': 'order_approved',
                'order_id': order_id,
                'approved_at': order['approved_at'],
                'approved_by_admin_id': order['approved_by_admin_id'],
                'delivered': False
            })
            break

    if not found:
        flash(f'Order {order_id} not found.', 'danger')
        return redirect(url_for('orders'))

    save_config(config)
    flash(f'Order {order_id} approved!', 'success')
    return redirect(url_for('orders'))


@app.route('/orders/reject/<order_id>', methods=['POST'])
@login_required
def reject_order(order_id):
    """Reject order"""
    config = load_config()
    
    for order in config['pending_approvals']:
        if order['order_id'] == order_id:
            order['status'] = 'rejected'
            break
    
    save_config(config)
    flash(f'Order {order_id} rejected!', 'error')
    return redirect(url_for('orders'))


@app.route('/settings')
@login_required
def settings():
    """General settings"""
    config = load_config()
    return render_template('settings.html', config=config)


@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    """Update general settings"""
    config = load_config()
    
    # Update bot token
    config['telegram_bot_token'] = request.form.get('telegram_bot_token')
    
    # Update currency
    config['currency'] = request.form.get('currency', 'LKR')
    
    save_config(config)
    flash('Settings updated successfully!', 'success')
    return redirect(url_for('settings'))


@app.route('/messages')
@login_required
def messages():
    """Manage messages"""
    config = load_config()
    # Import all text keys from languages.py
    from languages import TRANSLATIONS
    all_text_keys_en = {k: v for k, v in TRANSLATIONS['en'].items()}
    all_text_keys_si = {k: v for k, v in TRANSLATIONS['si'].items()}
    return render_template(
        'messages.html',
        messages=config.get('messages', {}),
        all_text_keys_en=all_text_keys_en,
        all_text_keys_si=all_text_keys_si
    )


@app.route('/messages/edit', methods=['POST'])
@login_required
def edit_messages():
    """Edit messages"""
    config = load_config()
    
    if 'messages' not in config:
        config['messages'] = {}

    validation_rules = {
        'account_ready_en': {
            'order_id', 'package_name', 'gb_limit', 'location_name', 'port',
            'protocol', 'username', 'expiry_date', 'subscription_link'
        },
        'account_ready_si': {
            'order_id', 'package_name', 'gb_limit', 'location_name', 'port',
            'protocol', 'username', 'expiry_date', 'subscription_link'
        },
        'all_texts_en_enter_custom_gb_desc': {'min_gb', 'max_gb', 'currency', 'price_per_gb'},
        'all_texts_si_enter_custom_gb_desc': {'min_gb', 'max_gb', 'currency', 'price_per_gb'},
        'all_texts_en_enter_custom_days_desc': {'min_days', 'max_days', 'currency', 'price_per_day'},
        'all_texts_si_enter_custom_days_desc': {'min_days', 'max_days', 'currency', 'price_per_day'},
        'all_texts_en_invalid_gb_range': {'min_gb', 'max_gb'},
        'all_texts_si_invalid_gb_range': {'min_gb', 'max_gb'},
        'all_texts_en_invalid_days_range': {'min_days', 'max_days'},
        'all_texts_si_invalid_days_range': {'min_days', 'max_days'},
    }

    validation_errors = []
    for field_name, allowed in validation_rules.items():
        value = request.form.get(field_name, '')
        error = _validate_template_placeholders(field_name, value, allowed)
        if error:
            validation_errors.append(error)

    if validation_errors:
        for error in validation_errors:
            flash(error, 'error')
        return redirect(url_for('messages'))
    
    # Update all message types
    config['messages']['welcome_en'] = request.form.get('welcome_en', '')
    config['messages']['welcome_si'] = request.form.get('welcome_si', '')
    config['messages']['account_ready_en'] = request.form.get('account_ready_en', '')
    config['messages']['account_ready_si'] = request.form.get('account_ready_si', '')
    # Backward compatibility: if old account_ready field is set, use it for English
    old_account_ready = request.form.get('account_ready', '')
    if old_account_ready and not config['messages']['account_ready_en']:
        config['messages']['account_ready_en'] = old_account_ready
    config['messages']['account_ready'] = config['messages']['account_ready_en']  # Keep for backward compatibility
    # Save all custom text keys for both languages
    from languages import TRANSLATIONS
    for key in TRANSLATIONS['en'].keys():
        val = request.form.get(f'all_texts_en_{key}', None)
        if val is not None:
            config['messages'][f'all_texts_en_{key}'] = val
    for key in TRANSLATIONS['si'].keys():
        val = request.form.get(f'all_texts_si_{key}', None)
        if val is not None:
            config['messages'][f'all_texts_si_{key}'] = val
    
    save_config(config)
    flash('Messages updated successfully!', 'success')
    return redirect(url_for('messages'))


@app.route('/system')
@login_required
def system():
    """System settings - backups and admin management"""
    config = load_config()
    admin_ids = config.get('admin_ids', [])
    token_present = bool(config.get('telegram_bot_token'))
    status = get_firebase_status()
    return render_template('system.html', admin_ids=admin_ids, firebase_status=status, token_present=token_present)


@app.route('/system/backup')
@login_required
def backup_config():
    """Download config.json backup"""
    config_path = CONFIG_PATH
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'config_backup_{timestamp}.json'
    
    # Read the config file and send it
    return send_file(
        config_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/json'
    )


@app.route('/system/admin/add', methods=['POST'])
@login_required
def add_admin():
    """Add new admin ID"""
    config = load_config()
    
    try:
        admin_id = int(request.form.get('admin_id', ''))
        
        if admin_id not in config['admin_ids']:
            config['admin_ids'].append(admin_id)
            save_config(config)
            flash(f'Admin ID {admin_id} added successfully!', 'success')
        else:
            flash(f'Admin ID {admin_id} already exists!', 'warning')
    except ValueError:
        flash('Invalid admin ID. Please enter a valid number.', 'danger')
    
    return redirect(url_for('system'))


@app.route('/system/admin/remove/<int:admin_id>', methods=['POST'])
@login_required
def remove_admin(admin_id):
    """Remove admin ID"""
    config = load_config()
    current_admin = session.get('admin_id')
    
    # Prevent removing the last admin (current user)
    if admin_id == current_admin and len(config['admin_ids']) == 1:
        flash('Cannot remove the only admin!', 'danger')
    elif admin_id in config['admin_ids']:
        config['admin_ids'].remove(admin_id)
        save_config(config)
        flash(f'Admin ID {admin_id} removed successfully!', 'success')
    else:
        flash('Admin ID not found!', 'danger')
    
    return redirect(url_for('system'))


@app.route('/payment-methods')
@login_required
def payment_methods():
    """Manage payment methods"""
    config = load_config()
    methods = config.get('payment_details', {}).get('methods', [])
    return render_template('payment_methods.html', methods=methods)


@app.route('/payment-methods/add', methods=['POST'])
@login_required
def add_payment_method():
    """Add new payment method"""
    config = load_config()
    
    method_type = request.form.get('method_id', '').strip()
    method_name = request.form.get('method_name', '').strip()
    
    if not method_type or not method_name:
        flash('Method type and name are required!', 'danger')
        return redirect(url_for('payment_methods'))
    
    # Initialize payment_details if not exists
    if 'payment_details' not in config:
        config['payment_details'] = {}
    if 'methods' not in config['payment_details']:
        config['payment_details']['methods'] = []
    
    methods = config['payment_details']['methods']
    
    # Generate unique ID for multiple accounts of same type (bank_1, bank_2, etc.)
    if method_type == 'bank':
        # Count existing bank methods
        bank_count = len([m for m in methods if m.get('id', '').startswith('bank')])
        method_id = f"bank_{bank_count + 1}" if bank_count > 0 else "bank"
    elif method_type == 'crypto':
        # Count existing crypto methods
        crypto_count = len([m for m in methods if m.get('id', '').startswith('crypto')])
        method_id = f"crypto_{crypto_count + 1}" if crypto_count > 0 else "crypto"
    else:
        method_id = method_type
    
    # Create new method
    new_method = {
        'id': method_id,
        'name': method_name,
        'type': method_type,  # Store the original type
    }
    
    # Add bank-specific fields if bank method
    if method_type == 'bank':
        new_method.update({
            'account_name': request.form.get('account_name', '').strip(),
            'account_number': request.form.get('account_number', '').strip(),
            'bank_name': request.form.get('bank_name', '').strip(),
        })
    
    # Add ezcash-specific fields
    if method_type == 'ezcash':
        new_method.update({
            'mobile_number': request.form.get('mobile_number', '').strip(),
        })
    
    # Add crypto-specific fields
    if method_type == 'crypto':
        new_method.update({
            'crypto_type': request.form.get('crypto_type', '').strip(),
            'crypto_address': request.form.get('crypto_address', '').strip(),
        })
    
    config['payment_details']['methods'].append(new_method)
    save_config(config)
    flash(f'Payment method "{method_name}" added successfully!', 'success')
    
    return redirect(url_for('payment_methods'))


@app.route('/payment-methods/edit/<method_id>', methods=['POST'])
@login_required
def edit_payment_method(method_id):
    """Edit payment method"""
    config = load_config()
    methods = config.get('payment_details', {}).get('methods', [])
    
    method = next((m for m in methods if m.get('id') == method_id), None)
    if not method:
        flash('Payment method not found!', 'danger')
        return redirect(url_for('payment_methods'))
    
    # Update basic fields
    method['name'] = request.form.get('method_name', method.get('name')).strip()
    
    # Update bank-specific fields
    if method_id.startswith('bank') or method.get('type') == 'bank':
        method['account_name'] = request.form.get('account_name', '').strip()
        method['account_number'] = request.form.get('account_number', '').strip()
        method['bank_name'] = request.form.get('bank_name', '').strip()
    
    # Update ezcash-specific fields
    if method_id == 'ezcash' or method.get('type') == 'ezcash':
        method['mobile_number'] = request.form.get('mobile_number', '').strip()
    
    # Update crypto-specific fields
    if method_id.startswith('crypto') or method.get('type') == 'crypto':
        method['crypto_type'] = request.form.get('crypto_type', '').strip()
        method['crypto_address'] = request.form.get('crypto_address', '').strip()
    
    save_config(config)
    flash(f'Payment method "{method.get("name")}" updated successfully!', 'success')
    
    return redirect(url_for('payment_methods'))


@app.route('/payment-methods/delete/<method_id>', methods=['POST'])
@login_required
def delete_payment_method(method_id):
    """Delete payment method"""
    config = load_config()
    methods = config.get('payment_details', {}).get('methods', [])
    
    method = next((m for m in methods if m.get('id') == method_id), None)
    if method:
        methods.remove(method)
        save_config(config)
        flash(f'Payment method "{method.get("name")}" deleted successfully!', 'success')
    else:
        flash('Payment method not found!', 'danger')
    
    return redirect(url_for('payment_methods'))


def _cron_authorized() -> bool:
    """Authorize Vercel cron calls.

    If CRON_SECRET is configured, Vercel sends it as:
    Authorization: Bearer <CRON_SECRET>
    """
    expected = (os.getenv('CRON_SECRET') or '').strip()
    if not expected:
        return True

    auth_header = (request.headers.get('authorization') or '').strip()
    if auth_header.lower().startswith('bearer '):
        provided = auth_header[7:].strip()
        return provided == expected
    return False


@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Telegram webhook endpoint for aiogram dispatcher."""
    expected_secret = (os.getenv('TELEGRAM_WEBHOOK_SECRET') or '').strip()
    if expected_secret:
        provided_secret = (request.headers.get('X-Telegram-Bot-Api-Secret-Token') or '').strip()
        if provided_secret != expected_secret:
            return jsonify({'ok': False, 'error': 'forbidden'}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'ok': True})

    try:
        from aiogram.types import Update
        from bot import dp, bot

        update = Update.model_validate(payload)
        asyncio.run(dp.feed_update(bot, update))
        return jsonify({'ok': True})
    except Exception as e:
        app.logger.exception(f"Webhook processing failed: {e}")
        return jsonify({'ok': False, 'error': 'webhook_processing_failed'}), 500


@app.route('/cron/provision', methods=['GET'])
def cron_provision():
    """Vercel cron endpoint: process provision requests."""
    if not _cron_authorized():
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    try:
        from bot import process_provision_requests
        asyncio.run(process_provision_requests())
        return jsonify({'ok': True, 'job': 'provision'})
    except Exception as e:
        app.logger.exception(f"cron/provision failed: {e}")
        return jsonify({'ok': False, 'error': 'cron_provision_failed'}), 500


@app.route('/cron/notifications', methods=['GET'])
def cron_notifications():
    """Vercel cron endpoint: process admin notifications."""
    if not _cron_authorized():
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    try:
        from bot import process_admin_notifications
        asyncio.run(process_admin_notifications())
        return jsonify({'ok': True, 'job': 'notifications'})
    except Exception as e:
        app.logger.exception(f"cron/notifications failed: {e}")
        return jsonify({'ok': False, 'error': 'cron_notifications_failed'}), 500


@app.route('/cron/remove-expired', methods=['GET'])
def cron_remove_expired():
    """Vercel cron endpoint: remove expired premium-channel members."""
    if not _cron_authorized():
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    try:
        from bot import bot
        from channel_removal import remove_expired_members
        asyncio.run(remove_expired_members(bot))
        return jsonify({'ok': True, 'job': 'remove_expired'})
    except Exception as e:
        app.logger.exception(f"cron/remove-expired failed: {e}")
        return jsonify({'ok': False, 'error': 'cron_remove_expired_failed'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=False)
