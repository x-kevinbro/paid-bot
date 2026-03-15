# --- Invite Link Tracking ---
invite_links_map = {}  # user_id: {"invite_link": str, "invite_code": str, "channel_id": int}

import asyncio
import json
import logging
import os
import random
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse
from html import escape
import io

import aiohttp
import aioschedule
import pytz
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from contextlib import suppress

# Import Firebase database module
from firebase_db import load_config, save_config, get_firebase_status

# Import language module
from languages import get_text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared default account-ready message for both bot and dashboard approvals
DEFAULT_ACCOUNT_READY_TEMPLATE = (
    "🎉 Your V2Ray Account Is Ready!\n\n"
    "✅ Order ID: {order_id}\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📦 Package: {package_name}\n"
    "💾 Data Limit: {gb_limit}\n"
    "🌍 Location: {location_name}\n"
    "🔌 Port: {port}\n"
    "📡 Protocol: {protocol}\n"
    "👤 Username: {username}\n"
    "⏰ Valid Until: {expiry_date}\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "📱 Subscription Link:\n"
    "{subscription_link}\n\n"
    "📋 How to Use:\n"
    "1️⃣ Download V2Ray app (V2RayNG for Android, V2RayN for Windows, Shadowrocket for iOS)\n"
    "2️⃣ Copy the subscription link above\n"
    "3️⃣ Import into your V2Ray app\n"
    "4️⃣ Connect and enjoy!\n\n"
    "⚠️ Important: Keep this configuration private and secure!\n\n"
    "Thank you for your purchase! 🙏"
)

# English template (alias for backward compatibility)
DEFAULT_ACCOUNT_READY_TEMPLATE_EN = DEFAULT_ACCOUNT_READY_TEMPLATE

# Sinhala template
DEFAULT_ACCOUNT_READY_TEMPLATE_SI = (
    "🎉 ඔබගේ V2Ray ගිණුම සූදානම්!\n\n"
    "✅ ඇණවුම් අංකය: {order_id}\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📦 පැකේජය: {package_name}\n"
    "💾 දත්ත සීමාව: {gb_limit}\n"
    "🌍 ස්ථානය: {location_name}\n"
    "🔌 Port: {port}\n"
    "📡 Protocol: {protocol}\n"
    "👤 පරිශීලක නාමය: {username}\n"
    "⏰ වලංගු කාලය: {expiry_date}\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "📱 Subscription Link:\n"
    "{subscription_link}\n\n"
    "📋 භාවිතා කරන්නේ කෙසේද:\n"
    "1️⃣ V2Ray යෙදුම බාගන්න (Android සඳහා V2RayNG, Windows සඳහා V2RayN, iOS සඳහා Shadowrocket)\n"
    "2️⃣ ඉහත subscription link එක copy කරන්න\n"
    "3️⃣ ඔබේ V2Ray යෙදුමට import කරන්න\n"
    "4️⃣ සම්බන්ධ වී විනෝද වන්න!\n\n"
    "⚠️ වැදගත්: මෙම configuration එක රහසිගත ලෙස තබා ගන්න!\n\n"
    "ඔබගේ මිලදී ගැනීමට ස්තූතියි! 🙏"
)


def build_account_message(order: dict, account_info: dict, config_data: dict, language: str = 'en') -> str:
    """Build the account-ready message using language-specific template."""
    messages = config_data.get('messages', {})
    
    # Try to get custom template for the specified language
    template_key = f'account_ready_{language}'
    template = messages.get(template_key, '')
    
    # Fallback to old 'account_ready' key for backward compatibility
    if not template and language == 'en':
        template = messages.get('account_ready', '')
    
    # If no custom template, use default for that language
    if not template:
        if language == 'si':
            template = DEFAULT_ACCOUNT_READY_TEMPLATE_SI
        else:
            template = DEFAULT_ACCOUNT_READY_TEMPLATE_EN
    
    expiry_date = datetime.fromtimestamp(account_info['expiry'] / 1000).strftime('%Y-%m-%d %H:%M')
    return template.format(
        order_id=order.get('order_id'),
        package_name=order.get('package_name'),
        gb_limit=f"{order.get('gb')} GB" if order.get('gb', 0) > 0 else "Unlimited GB",
        location_name=account_info['location'],
        port=account_info['port'],
        protocol=account_info['protocol'].upper(),
        username=account_info['email'],
        expiry_date=expiry_date,
        subscription_link=account_info['subscription_link']
    )

# Set timezone
TZ = pytz.timezone('Asia/Colombo')

# Firebase status
firebase_status = get_firebase_status()
if firebase_status['using_firebase']:
    logger.info("🔥 Using Firebase for data storage")
else:
    logger.info("📁 Using JSON file for data storage")

# Legacy CONFIG_PATH for compatibility
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')


# Load initial config (now using Firebase)
_config = load_config()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or _config.get('telegram_bot_token')

# Dynamic config getters - always reload from file
def get_admin_ids():
    return set(load_config().get('admin_ids', []))

def get_packages():
    return load_config().get('packages', [])

def get_locations():
    return load_config().get('locations', [])

def get_panels():
    return load_config().get('panels', [])

def get_payment_details():
    return load_config().get('payment_details', {})

def get_currency():
    return load_config().get('currency', 'USD')

def get_isp_providers():
    return load_config().get('isp_providers', [])

def get_messages():
    return load_config().get('messages', {})


def is_maintenance_mode() -> bool:
    return bool(load_config().get('maintenance_mode', False))


def get_maintenance_banner_text(config_data: Optional[dict] = None) -> str:
    cfg = config_data or load_config()
    text = str(cfg.get('maintenance_banner_text') or '').strip()
    return text or "Bot is under development."

def get_custom_package_config():
    config = load_config()
    return {
        'enabled': config.get('custom_package_enabled', False),
        'pricing': config.get('custom_package_pricing', {
            'price_per_gb': 2.0,
            'price_per_day': 5.0,
            'min_gb': 10,
            'max_gb': 1000,
            'min_days': 1,
            'max_days': 365
        })
    }

def calculate_custom_package_price(gb: int, days: int) -> float:
    """Calculate price for custom package based on GB and days"""
    pricing = get_custom_package_config()['pricing']
    price_per_gb = pricing.get('price_per_gb', 2.0)
    price_per_day = pricing.get('price_per_day', 5.0)
    # Price formula: (GB * price_per_gb) + (days * price_per_day)
    return (gb * price_per_gb) + (days * price_per_day)


async def resolve_user_language(state: FSMContext, user_id: int, default: str = 'en') -> str:
    """Resolve language from state, with fallback to persisted user preference."""
    data = await state.get_data()
    language = data.get('language')
    if language:
        return language

    config = load_config()
    user_languages = config.get('user_languages', {})
    language = user_languages.get(str(user_id), default)
    await state.update_data(language=language)
    return language


def resolve_target_user_id(order: Optional[dict] = None, req: Optional[dict] = None) -> Optional[int]:
    """Resolve a Telegram user id from order/request payloads."""
    candidate_ids = []
    if order:
        candidate_ids.extend([
            order.get('user_id'),
            order.get('telegram_id')
        ])
    if req:
        candidate_ids.extend([
            req.get('user_id'),
            req.get('telegram_id')
        ])

    for candidate in candidate_ids:
        if candidate is None or candidate == '':
            continue
        try:
            return int(str(candidate).strip())
        except Exception:
            continue
    return None

# Initialize bot
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class MaintenanceModeMiddleware(BaseMiddleware):
    """Block non-admin bot usage while maintenance mode is enabled."""

    async def __call__(self, handler, event, data):
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)

        if is_admin(user.id) or not is_maintenance_mode():
            return await handler(event, data)

        maintenance_text = get_maintenance_banner_text()

        if isinstance(event, types.CallbackQuery):
            await event.answer(maintenance_text, show_alert=True)
            return

        if isinstance(event, types.Message):
            await event.answer(maintenance_text)
            return

        return


dp.message.middleware(MaintenanceModeMiddleware())
dp.callback_query.middleware(MaintenanceModeMiddleware())


async def build_premium_invite_button(user_id: int, config_data: dict) -> Optional[InlineKeyboardMarkup]:
    """Build a premium-channel button for account-ready messages."""
    user_id = resolve_target_user_id(order={'user_id': user_id})
    if user_id is None:
        logger.warning("No valid user_id for premium invite button.")
        return None

    premium_channel_id_raw = os.getenv('PREMIUM_CHANNEL_ID') or (config_data or {}).get('premium_channel_id')
    if not premium_channel_id_raw:
        return None

    premium_channel_id = premium_channel_id_raw
    if isinstance(premium_channel_id_raw, str):
        stripped = premium_channel_id_raw.strip()
        if not stripped:
            return None
        if stripped.startswith("-100") and stripped[1:].isdigit():
            premium_channel_id = int(stripped)
        elif stripped.isdigit():
            premium_channel_id = int(stripped)
        else:
            premium_channel_id = stripped

    try:
        member = await bot.get_chat_member(chat_id=premium_channel_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            logger.info(f"User {user_id} is already a member of the premium channel. No invite link sent.")
            return None
    except Exception as e:
        logger.info(f"Membership check failed for user {user_id}; proceeding with invite creation: {e}")

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=premium_channel_id,
            member_limit=1,
            creates_join_request=False
        )
        invite_link = invite.invite_link
        invite_code = None
        try:
            path = urlparse(invite_link).path
            if path.startswith("/+"):
                invite_code = path[2:]
            elif path.startswith("/joinchat/"):
                invite_code = path.split("/joinchat/")[-1]
            else:
                invite_code = path.strip("/")
        except Exception:
            invite_code = None

        invite_links_map[user_id] = {
            "invite_link": invite_link,
            "invite_code": invite_code,
            "channel_id": premium_channel_id
        }
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔑 Join Premium Channel", url=invite_link)]
            ]
        )
    except Exception as e:
        logger.error(f"Failed to create invite link: {e}")
        return None


async def send_panel_backup_to_channel(order: dict, account_info: dict, config_data: dict) -> None:
    """Send panel backup DB file to configured backup channel after successful provisioning."""
    backup_channel_raw = os.getenv('BACKUP_CHANNEL_ID') or (config_data or {}).get('backup_channel_id')
    if not backup_channel_raw:
        return

    backup_channel_id = backup_channel_raw
    if isinstance(backup_channel_raw, str):
        stripped = backup_channel_raw.strip()
        if stripped.startswith("-100") and stripped[1:].isdigit():
            backup_channel_id = int(stripped)
        elif stripped.isdigit():
            backup_channel_id = int(stripped)

    # Get panel info from account_info
    panel_name = account_info.get('panel_name', '')
    panel_url = account_info.get('panel_url', '')
    
    if not panel_name or not panel_url:
        logger.warning("No panel info in account_info, cannot download backup")
        return
    
    # Find panel config by name
    panels = get_panels()
    panel_config = next((p for p in panels if p['name'] == panel_name), None)
    
    if not panel_config:
        logger.warning(f"Panel config not found for {panel_name}")
        return
    
    # Download backup from panel
    import tempfile
    panel_client = PanelClient(panel_config)
    backup_data = None
    
    try:
        # Login to panel
        if await panel_client.login():
            # Download backup
            backup_data = await panel_client.download_backup()
        else:
            logger.error(f"Failed to login to panel {panel_name} for backup download")
            return
    finally:
        await panel_client.close()
    
    if not backup_data:
        # Fallback to local file if panel download fails
        logger.warning(f"Panel backup download failed, trying local file")
        configured_backup_path = (
            os.getenv('PANEL_BACKUP_DB_PATH')
            or (config_data or {}).get('panel_backup_db_path')
            or ''
        )

        candidate_paths = []
        if configured_backup_path:
            candidate_paths.append(configured_backup_path)

        candidate_paths.extend([
            os.path.join(os.path.dirname(__file__), 'x-ui.db'),
            os.path.join(os.getcwd(), 'x-ui.db'),
        ])

        user_profile = os.getenv('USERPROFILE')
        if user_profile:
            candidate_paths.append(os.path.join(user_profile, 'Downloads', 'x-ui.db'))

        backup_db_path = next((path for path in candidate_paths if path and os.path.isfile(path)), None)
        if not backup_db_path:
            logger.warning(f"Backup DB file not found. Tried: {candidate_paths}")
            return
        
        # Read local file
        try:
            with open(backup_db_path, 'rb') as f:
                backup_data = f.read()
        except Exception as e:
            logger.error(f"Failed to read local backup file: {e}")
            return

    # Send backup to channel
    order_id = order.get('order_id', 'unknown')
    caption = (
        "🗄️ Panel DB Backup\n"
        f"Order: <code>{order_id}</code>\n"
        f"Panel: {panel_name} ({panel_url})\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    try:
        # Create temporary file from backup data
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
            tmp.write(backup_data)
            tmp_path = tmp.name
        
        try:
            backup_file = FSInputFile(tmp_path, filename=f"x-ui-backup-{order_id}-{panel_name}.db")
            await bot.send_document(
                chat_id=backup_channel_id,
                document=backup_file,
                caption=caption,
                parse_mode="HTML"
            )
            logger.info(f"✓ Sent panel backup ({len(backup_data)} bytes) to channel {backup_channel_id}")
        finally:
            import os as os_module
            os_module.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Failed to send backup DB to channel {backup_channel_id}: {e}")


async def send_account_ready_to_channel(order: dict, account_msg: str, config_data: dict) -> None:
    """Send final account-ready message to configured backup channel."""
    backup_channel_raw = os.getenv('BACKUP_CHANNEL_ID') or (config_data or {}).get('backup_channel_id')
    if not backup_channel_raw:
        return

    backup_channel_id = backup_channel_raw
    if isinstance(backup_channel_raw, str):
        stripped = backup_channel_raw.strip()
        if stripped.startswith("-100") and stripped[1:].isdigit():
            backup_channel_id = int(stripped)
        elif stripped.isdigit():
            backup_channel_id = int(stripped)

    order_id = order.get('order_id', 'unknown')
    user_id = order.get('user_id', 'unknown')
    username = order.get('username') or 'No username'
    channel_text = (
        "✅ <b>Account Ready Delivered</b>\n"
        f"Order: <code>{order_id}</code>\n"
        f"User: @{username} (ID: <code>{user_id}</code>)\n\n"
        f"{account_msg}"
    )

    try:
        await bot.send_message(
            chat_id=backup_channel_id,
            text=channel_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send account-ready message to channel {backup_channel_id}: {e}")


async def send_revoke_notice_to_channel(order: dict, account_info: dict, config_data: dict) -> None:
    """Send revoke event summary to configured backup channel."""
    backup_channel_raw = os.getenv('BACKUP_CHANNEL_ID') or (config_data or {}).get('backup_channel_id')
    if not backup_channel_raw:
        return

    backup_channel_id = backup_channel_raw
    if isinstance(backup_channel_raw, str):
        stripped = backup_channel_raw.strip()
        if stripped.startswith("-100") and stripped[1:].isdigit():
            backup_channel_id = int(stripped)
        elif stripped.isdigit():
            backup_channel_id = int(stripped)

    order_id = order.get('order_id', 'unknown')
    user_id = order.get('user_id') or order.get('telegram_id') or 'unknown'
    username = order.get('username') or 'No username'
    location_id = order.get('location_id') or 'unknown'
    package_name = order.get('package_name') or order.get('package_id') or 'unknown'
    panel_name = (account_info or {}).get('panel_name') or 'unknown'
    panel_url = (account_info or {}).get('panel_url') or ''
    revoked_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    text = (
        "🛑 <b>Account Revoked</b>\n"
        f"Order: <code>{order_id}</code>\n"
        f"User: @{username} (ID: <code>{user_id}</code>)\n"
        f"Package: {package_name}\n"
        f"Location: {location_id}\n"
        f"Panel: {panel_name}\n"
        f"Time: {revoked_at}"
    )

    if panel_url:
        text += f"\nPanel URL: <code>{panel_url}</code>"

    try:
        await bot.send_message(
            chat_id=backup_channel_id,
            text=text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send revoke notice to channel {backup_channel_id}: {e}")

# FSM States
class LanguageSelection(StatesGroup):
    waiting_for_language = State()


class PurchaseFlow(StatesGroup):
    waiting_for_isp = State()
    waiting_for_user_package = State()
    waiting_for_package = State()
    waiting_for_package_type = State()  # Choose predefined or custom
    waiting_for_custom_gb = State()  # Custom package: GB input
    waiting_for_custom_days = State()  # Custom package: days input
    waiting_for_gb = State()
    waiting_for_location = State()
    waiting_for_referral_code = State()
    waiting_for_client_name = State()
    waiting_for_payment_receipt = State()
    waiting_for_order_note = State()
    waiting_for_retry_payment_receipt = State()  # Retry after rejection
    waiting_for_retry_order_note = State()  # Retry note
    waiting_for_confirmation = State()


class AdminApprove(StatesGroup):
    waiting_for_password = State()
    waiting_for_selection = State()


class BroadcastMessage(StatesGroup):
    waiting_for_message = State()


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


def format_bytes(bytes_value: int) -> str:
    """Format bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


class PanelClient:
    """Client for interacting with 3x-ui panel API"""
    
    def __init__(self, panel_config: dict):
        self.name = panel_config['name']
        self.url = panel_config['url'].rstrip('/')
        self.username = panel_config['username']
        self.password = panel_config['password']
        self.api_port = panel_config.get('api_port', 54321)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def login(self) -> bool:
        """Login to the panel"""
        try:
            if self.session:
                await self.session.close()
            self.session = aiohttp.ClientSession()

            login_url = f"{self.url}/login"
            payload = {"username": self.username, "password": self.password}

            async with self.session.post(login_url, json=payload, ssl=False) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    if isinstance(data, dict) and data.get('success'):
                        logger.info(f"✓ Logged into {self.name}")
                        return True
                logger.warning(f"✗ Failed to login to {self.name}")
                return False
        except Exception as e:
            logger.error(f"✗ Error logging into {self.name}: {e}")
            return False

    async def get_inbounds(self) -> Optional[List[Dict]]:
        """Get inbounds list from panel"""
        try:
            if not self.session:
                return None

            endpoints = [
                f"{self.url}/panel/api/inbounds/list",
                f"{self.url}/xui/API/inbounds/",
            ]

            for url in endpoints:
                try:
                    async with self.session.get(url, ssl=False) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('success') and data.get('obj') is not None:
                                return data.get('obj', [])
                except Exception:
                    continue
            return None
        except Exception as e:
            logger.error(f"Error getting inbounds from {self.name}: {e}")
            return None
    
    async def get_inbound_by_port(self, port: int) -> Optional[Dict]:
        """Find inbound by port number"""
        try:
            inbounds = await self.get_inbounds()
            if not inbounds:
                return None
            
            for inbound in inbounds:
                inbound_port = inbound.get('port')
                try:
                    if int(inbound_port) == int(port):
                        logger.info(f"✓ Found inbound on port {port}: {inbound.get('remark')}")
                        return inbound
                except (TypeError, ValueError):
                    continue
            
            logger.warning(f"✗ No inbound found on port {port}")
            return None
        except Exception as e:
            logger.error(f"Error finding inbound by port: {e}")
            return None

    async def add_client_to_inbound(self, inbound_id: int, client_data: dict) -> bool:
        """Add a client to an inbound"""
        try:
            if not self.session:
                return False

            import uuid
            duplicate_retry_done = False

            # Try multiple endpoint formats
            endpoints = [
                f"{self.url}/panel/api/inbounds/addClient",
                f"{self.url}/xui/inbound/addClient",
            ]
            
            for add_url in endpoints:
                try:
                    payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_data]})}

                    async with self.session.post(add_url, json=payload, ssl=False) as response:
                        # Get response as text first (3x-ui sometimes returns text/plain)
                        response_text = await response.text()
                        
                        if response.status == 200:
                            # Try to parse as JSON
                            try:
                                data = json.loads(response_text)
                                if data.get('success'):
                                    logger.info(f"✓ Client {client_data.get('email')} added to inbound {inbound_id}")
                                    return True
                            except json.JSONDecodeError:
                                # If response is plain text success message
                                if 'success' in response_text.lower() or response_text.strip() == 'true':
                                    logger.info(f"✓ Client {client_data.get('email')} added to inbound {inbound_id}")
                                    return True

                        response_lower = response_text.lower()
                        if (not duplicate_retry_done) and ('duplicate email' in response_lower):
                            duplicate_retry_done = True
                            original_email = client_data.get('email', 'user')
                            base_email = original_email.rsplit('_', 1)[0] if '_' in original_email else original_email
                            unique_suffix = str(random.randint(1000, 9999))
                            client_data['email'] = f"{base_email}_{unique_suffix}"
                            client_data['id'] = str(uuid.uuid4())
                            logger.warning(
                                f"Duplicate email detected for {original_email}; retrying as {client_data['email']}"
                            )
                            payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_data]})}
                            async with self.session.post(add_url, json=payload, ssl=False) as retry_response:
                                retry_text = await retry_response.text()
                                if retry_response.status == 200:
                                    try:
                                        retry_data = json.loads(retry_text)
                                        if retry_data.get('success'):
                                            logger.info(f"✓ Client {client_data.get('email')} added to inbound {inbound_id}")
                                            return True
                                    except json.JSONDecodeError:
                                        if 'success' in retry_text.lower() or retry_text.strip() == 'true':
                                            logger.info(f"✓ Client {client_data.get('email')} added to inbound {inbound_id}")
                                            return True
                        
                        logger.warning(f"✗ Failed with {add_url}: {response_text[:200]}")
                except Exception as endpoint_error:
                    logger.debug(f"Endpoint {add_url} failed: {endpoint_error}")
                    continue
            
            return False
        except Exception as e:
            logger.error(f"Error adding client: {e}")
            return False

    async def add_client_unlimited_style(self, inbound: dict, email: str, gb: int, days: int, telegram_id: int) -> Optional[dict]:
        """Add client using Unlimited Data style protocol-aware payload construction."""
        try:
            if not self.session:
                return None

            inbound_id = inbound.get('id')
            if inbound_id is None:
                return None

            protocol = str(inbound.get('protocol') or '').lower()
            if not protocol:
                return None

            stream_settings_raw = inbound.get('streamSettings', {})
            stream_settings = json.loads(stream_settings_raw) if isinstance(stream_settings_raw, str) else (stream_settings_raw or {})

            settings_raw = inbound.get('settings', {})
            inbound_settings = json.loads(settings_raw) if isinstance(settings_raw, str) else (settings_raw or {})

            import uuid

            client_id = str(uuid.uuid4())
            total_gb = gb * 1024 * 1024 * 1024 if gb and gb > 0 else 0
            expiry_time = int((datetime.now() + timedelta(days=days)).timestamp() * 1000) if days and days > 0 else 0

            client_data = {
                "id": client_id,
                "email": email,
                "enable": True,
                "totalGB": total_gb,
                "expiryTime": expiry_time,
                "limitIp": 0,
                "tgId": str(telegram_id),
                "subId": "",
                "reset": 0
            }

            if protocol == 'vmess':
                client_data['alterId'] = 0
            elif protocol == 'vless':
                client_data['flow'] = ''
                if stream_settings.get('network') == 'tcp' and ((stream_settings.get('tcpSettings') or {}).get('header') or {}).get('type') == 'http':
                    client_data['flow'] = 'xtls-rprx-vision'
            elif protocol == 'trojan':
                client_data['password'] = client_id
            elif protocol == 'shadowsocks':
                import secrets
                client_data['password'] = secrets.token_urlsafe(16)
                inbound_method = (inbound_settings or {}).get('method')
                client_data['method'] = inbound_method or 'aes-256-gcm'
            else:
                logger.warning(f"Unsupported protocol for unlimited-style creation: {protocol}")
                return None

            existing_clients = (inbound_settings or {}).get('clients', [])
            if isinstance(existing_clients, list) and existing_clients:
                template_client = existing_clients[0] if isinstance(existing_clients[0], dict) else {}
                for key, value in template_client.items():
                    if key in ('id', 'email', 'expiryTime', 'totalGB'):
                        continue
                    if key not in client_data or client_data.get(key) in (None, '', 0):
                        client_data[key] = value

            payload = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }

            endpoints = [
                f"{self.url}/panel/api/inbounds/addClient",
                f"{self.url}/xui/inbound/addClient",
            ]

            for add_url in endpoints:
                try:
                    async with self.session.post(add_url, json=payload, ssl=False) as response:
                        response_text = await response.text()
                        if response.status == 200:
                            success = False
                            try:
                                response_json = json.loads(response_text)
                                success = bool(response_json.get('success'))
                            except json.JSONDecodeError:
                                success = ('success' in response_text.lower()) or (response_text.strip().lower() == 'true')

                            if success:
                                return {
                                    "client_id": client_data.get('id'),
                                    "email": client_data.get('email'),
                                    "client_data": client_data
                                }
                except Exception as endpoint_error:
                    logger.debug(f"Unlimited-style endpoint {add_url} failed: {endpoint_error}")
                    continue

            return None
        except Exception as e:
            logger.error(f"Error in unlimited-style add client: {e}")
            return None
    
    async def update_inbound_client(self, inbound_id: int, new_client: dict) -> bool:
        """Alternative method: Get inbound, add client to settings, update inbound"""
        try:
            if not self.session:
                return False
            
            # Get current inbound settings
            inbounds = await self.get_inbounds()
            if not inbounds:
                return False
            
            inbound = next((ib for ib in inbounds if ib.get('id') == inbound_id), None)
            if not inbound:
                logger.error(f"Inbound {inbound_id} not found")
                return False
            
            # Parse current settings
            settings = json.loads(inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            
            # Add new client
            clients.append(new_client)
            settings['clients'] = clients
            
            # Update inbound
            update_url = f"{self.url}/panel/api/inbounds/update/{inbound_id}"
            payload = {
                "id": inbound_id,
                "settings": json.dumps(settings)
            }
            
            async with self.session.post(update_url, json=payload, ssl=False) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                        if data.get('success'):
                            logger.info(f"✓ Client {new_client.get('email')} added via update method")
                            return True
                    except json.JSONDecodeError:
                        if 'success' in response_text.lower() or response_text.strip() == 'true':
                            logger.info(f"✓ Client {new_client.get('email')} added via update method")
                            return True
                
                logger.warning(f"✗ Update failed: {response_text[:200]}")
            
            return False
        except Exception as e:
            logger.error(f"Error updating inbound: {e}")
            return False

    async def remove_client_from_inbound(self, inbound_id: int, client_id: Optional[str] = None, email: Optional[str] = None) -> bool:
        """Remove a client from an inbound using only safe delete endpoints.

        3x-ui expects different client identifiers depending on protocol:
        UUID for vmess/vless, password for trojan, and email for shadowsocks.
        Do not fall back to updateInbound here; a malformed update payload can
        corrupt the inbound on some panel versions.
        """
        try:
            if not self.session:
                return False
            if not client_id and not email:
                logger.error("remove_client_from_inbound: need at least client_id or email")
                return False

            # --- Step 1: load inbound and resolve the correct protocol-specific client key ---
            inbounds = await self.get_inbounds()
            if not inbounds:
                return False
            inbound = next((ib for ib in inbounds if ib.get('id') == inbound_id), None)
            if not inbound:
                logger.error(f"Inbound {inbound_id} not found for removal")
                return False

            settings_raw = inbound.get('settings', '{}')
            settings = json.loads(settings_raw) if isinstance(settings_raw, str) else (settings_raw or {})
            clients = settings.get('clients', [])
            if not isinstance(clients, list):
                logger.error(f"Inbound {inbound_id} has no clients list")
                return False

            protocol = str(inbound.get('protocol') or '').strip().lower()
            delete_key = 'id'
            if protocol == 'trojan':
                delete_key = 'password'
            elif protocol == 'shadowsocks':
                delete_key = 'email'

            matched_client = None
            resolved_delete_value = None
            for c in clients:
                if not isinstance(c, dict):
                    continue
                cid = str(c.get('id') or '')
                cemail = str(c.get('email') or '')
                if (client_id and cid == str(client_id)) or (email and cemail == str(email)):
                    matched_client = c
                    resolved_delete_value = str(c.get(delete_key) or '').strip() or None
                    break

            if not matched_client:
                logger.warning(f"No client match for revoke in inbound {inbound_id}: client_id={client_id}, email={email}")
                return False

            # --- Step 2: try the proper dedicated delClient endpoint (protocol-specific client key) ---
            if resolved_delete_value:
                del_endpoints = [
                    f"{self.url}/panel/api/inbounds/{inbound_id}/delClient/{resolved_delete_value}",
                    f"{self.url}/xui/inbound/delClient/{resolved_delete_value}",
                ]
                for del_url in del_endpoints:
                    try:
                        async with self.session.post(del_url, ssl=False) as response:
                            response_text = await response.text()
                            if response.status == 200:
                                try:
                                    data = json.loads(response_text)
                                    if bool(data.get('success')):
                                        logger.info(f"✓ Deleted client from inbound {inbound_id} via delClient endpoint")
                                        return True
                                except json.JSONDecodeError:
                                    if 'success' in response_text.lower() or response_text.strip().lower() == 'true':
                                        logger.info(f"✓ Deleted client from inbound {inbound_id} via delClient endpoint")
                                        return True
                    except Exception as del_err:
                        logger.debug(f"delClient endpoint failed {del_url}: {del_err}")
                        continue

            # --- Step 3: safe fallback — delete by email if supported by the panel ---
            if email:
                email_endpoints = [
                    f"{self.url}/panel/api/inbounds/{inbound_id}/delClientByEmail/{email}",
                    f"{self.url}/xui/inbound/{inbound_id}/delClientByEmail/{email}",
                ]
                for delete_by_email_url in email_endpoints:
                    try:
                        async with self.session.post(delete_by_email_url, ssl=False) as response:
                            response_text = await response.text()
                            if response.status == 200:
                                try:
                                    data = json.loads(response_text)
                                    if bool(data.get('success')):
                                        logger.info(f"✓ Deleted client {email} from inbound {inbound_id} via delClientByEmail endpoint")
                                        return True
                                except json.JSONDecodeError:
                                    if 'success' in response_text.lower() or response_text.strip().lower() == 'true':
                                        logger.info(f"✓ Deleted client {email} from inbound {inbound_id} via delClientByEmail endpoint")
                                        return True
                    except Exception as email_err:
                        logger.debug(f"delClientByEmail endpoint failed {delete_by_email_url}: {email_err}")
                        continue

            logger.error(
                f"Failed to safely delete client from inbound {inbound_id} "
                f"(protocol={protocol}, client_id={client_id}, email={email})"
            )
            return False

        except Exception as e:
            logger.error(f"Error removing client from inbound: {e}")
            return False

    async def download_backup(self) -> Optional[bytes]:
        """Download x-ui.db backup file from panel"""
        try:
            if not self.session:
                return None
            
            # Try multiple common backup endpoints
            endpoints = [
                f"{self.url}/panel/api/server/getDb",
                f"{self.url}/xui/API/server/getDb",
                ("GET", f"{self.url}/panel/api/backup/download"),
                ("GET", f"{self.url}/panel/api/server/backup"),
                ("GET", f"{self.url}/api/backup/download"),
                ("POST", f"{self.url}/panel/api/backup/download"),
                ("POST", f"{self.url}/panel/api/server/backup"),
                ("GET", f"{self.url}/panel/backup"),
            ]
            
            for endpoint in endpoints:
                try:
                    if isinstance(endpoint, str):
                        # Default to GET
                        async with self.session.get(endpoint, ssl=False) as response:
                            if response.status == 200:
                                logger.info(f"✓ Downloaded backup from {self.name}")
                                return await response.read()
                    else:
                        method, backup_url = endpoint
                        if method == "GET":
                            async with self.session.get(backup_url, ssl=False) as response:
                                if response.status == 200:
                                    logger.info(f"✓ Downloaded backup from {self.name}")
                                    return await response.read()
                        else:  # POST
                            async with self.session.post(backup_url, ssl=False) as response:
                                if response.status == 200:
                                    logger.info(f"✓ Downloaded backup from {self.name}")
                                    return await response.read()
                except Exception as e:
                    continue
            
            logger.warning(f"Failed to download backup from {self.name}: No working endpoint found")
            return None
        except Exception as e:
            logger.error(f"Error downloading backup from {self.name}: {e}")
            return None

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None


def get_unlimited_creation_flag_state(config_data: Optional[dict] = None) -> Dict[str, Any]:
    """Resolve unlimited creation flag with source diagnostics."""
    env_value = os.getenv('ENABLE_UNLIMITED_CREATION_FLOW')
    if env_value is not None:
        enabled = str(env_value).strip().lower() in ('1', 'true', 'yes', 'on')
        return {
            "enabled": enabled,
            "source": "env",
            "raw": str(env_value)
        }

    cfg = config_data or load_config()
    raw_value = cfg.get('unlimited_style_creation_enabled', False)
    return {
        "enabled": bool(raw_value),
        "source": "config",
        "raw": raw_value
    }


def is_unlimited_creation_enabled(config_data: Optional[dict] = None) -> bool:
    """Feature flag for Unlimited Data style protocol-aware account creation."""
    return bool(get_unlimited_creation_flag_state(config_data).get('enabled'))


def get_provision_max_attempts(config_data: Optional[dict] = None) -> int:
    """Maximum automatic retries for a provision request before marking failed."""
    env_value = os.getenv('PROVISION_MAX_ATTEMPTS')
    if env_value is not None:
        try:
            parsed = int(str(env_value).strip())
            if parsed > 0:
                return parsed
        except Exception:
            pass

    cfg = config_data or load_config()
    configured = cfg.get('provision_max_attempts', 5)
    try:
        configured_int = int(configured)
        return configured_int if configured_int > 0 else 5
    except Exception:
        return 5


def is_auto_panel_failover_enabled(config_data: Optional[dict] = None) -> bool:
    """Feature flag for panel failover when primary panel is unavailable."""
    env_value = os.getenv('ENABLE_AUTO_PANEL_FAILOVER')
    if env_value is not None:
        return str(env_value).strip().lower() in ('1', 'true', 'yes', 'on')

    cfg = config_data or load_config()
    return bool(cfg.get('auto_panel_failover_enabled', False))


def get_revenue_retention_settings(config_data: Optional[dict] = None) -> Dict[str, Any]:
    """Get pricing/claims settings used by referral and coupon logic."""
    cfg = config_data or load_config()

    def _int_setting(key: str, default: int, minimum: int = 0) -> int:
        try:
            value = int(cfg.get(key, default))
            return value if value >= minimum else default
        except Exception:
            return default

    def _float_setting(key: str, default: float, minimum: float = 0.0) -> float:
        try:
            value = float(cfg.get(key, default))
            return value if value >= minimum else default
        except Exception:
            return default

    return {
        "referral_claim_limit": _int_setting("referral_claim_limit", 3, 1),
        "referral_claim_window_minutes": _int_setting("referral_claim_window_minutes", 60, 1),
        "admin_coupon_cooldown_minutes": _int_setting("admin_coupon_cooldown_minutes", 60, 1),
        "default_code_max_redemptions": _int_setting("default_code_max_redemptions", 0, 0),
        "coupon_min_order_amount": _float_setting("coupon_min_order_amount", 0.0, 0.0),
    }


def _location_id_candidates(location_id: Any) -> List[str]:
    raw = str(location_id or '').strip()
    if not raw:
        return []

    candidates: List[str] = [raw]
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


def resolve_location_config(location_id: Any, locations: List[Dict]) -> Optional[Dict]:
    """Resolve location by exact match, case-insensitive match, or tokenized fallback (e.g. sg_sg -> sg)."""
    if not locations:
        return None

    candidates = _location_id_candidates(location_id)
    if not candidates:
        return None

    for candidate in candidates:
        location = next((l for l in locations if str(l.get('id', '')).strip() == candidate), None)
        if location:
            return location

    candidates_lower = [c.lower() for c in candidates]
    for candidate in candidates_lower:
        location = next((l for l in locations if str(l.get('id', '')).strip().lower() == candidate), None)
        if location:
            return location

    return None


def get_location_panel_candidates(location: Dict, panels: List[Dict], config_data: Optional[dict] = None) -> List[Dict]:
    """Return ordered panel candidates for a location: primary, explicit backup, then remaining panels."""
    if not location or not panels:
        return []

    primary_panel_id = location.get('panel_id')
    backup_panel_id = location.get('backup_panel_id')
    failover_enabled = is_auto_panel_failover_enabled(config_data)

    ordered_ids: List[Any] = [primary_panel_id]
    if failover_enabled and backup_panel_id not in (None, '', primary_panel_id):
        ordered_ids.append(backup_panel_id)

    if failover_enabled:
        ordered_ids.extend(
            panel.get('id')
            for panel in panels
            if panel.get('id') not in ordered_ids
        )

    panel_candidates = [panel for panel in panels if panel.get('id') in ordered_ids]
    panel_candidates.sort(key=lambda panel: ordered_ids.index(panel.get('id')))
    return panel_candidates


async def create_v2ray_account(package_id: str, gb: int, location_id: str, telegram_username: str, telegram_id: int, sni: str = '', port: int = 443, use_location_sni: bool = False, address: str = '', client_name: str = None, days: int = 30) -> Optional[Dict]:
    """Create a V2Ray account and add to panel (with optional auto panel failover)."""
    panel = None
    try:
        safe_days = int(days) if days else 30
        if safe_days <= 0:
            safe_days = 30

        locations = get_locations()
        location = resolve_location_config(location_id, locations)
        if not location:
            logger.error(f"Location {location_id} not found")
            return None
        if str(location.get('id')) != str(location_id):
            logger.warning(f"Location fallback applied: requested={location_id}, resolved={location.get('id')}")

        panels = get_panels()
        primary_panel_id = location['panel_id']
        primary_panel = next((p for p in panels if p['id'] == primary_panel_id), None)
        if not primary_panel:
            logger.error(f"Panel {primary_panel_id} not found")
            return None

        cfg = load_config()
        panel_candidates = get_location_panel_candidates(location, panels, cfg)

        flow_flag = get_unlimited_creation_flag_state(cfg)
        use_unlimited_style = bool(flow_flag.get('enabled'))
        logger.info(
            "Creation flow decision: unlimited_enabled=%s source=%s raw=%s",
            use_unlimited_style,
            flow_flag.get('source'),
            flow_flag.get('raw')
        )

        # shared client identity for retries/failover
        if client_name:
            client_email = client_name
        else:
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(4)])
            client_email = f"{telegram_username}{random_digits}"

        for panel_config in panel_candidates:
            try:
                panel = PanelClient(panel_config)
                if not await panel.login():
                    logger.warning(f"Panel login failed: {panel_config.get('name')} ({panel_config.get('id')})")
                    continue

                inbound = await panel.get_inbound_by_port(port)
                if not inbound:
                    logger.warning(f"No inbound found on port {port} for panel {panel_config.get('name')}")
                    continue

                inbound_id = inbound.get('id')
                inbound_port = inbound.get('port')
                inbound_protocol = inbound.get('protocol')

                settings_raw = inbound.get('settings', '{}')
                settings = json.loads(settings_raw) if isinstance(settings_raw, str) else (settings_raw or {})
                stream_settings_raw = inbound.get('streamSettings', '{}')
                stream_settings = json.loads(stream_settings_raw) if isinstance(stream_settings_raw, str) else (stream_settings_raw or {})

                import uuid
                client_id = str(uuid.uuid4())
                total_gb = gb * 1024 * 1024 * 1024
                expiry_time = int((datetime.now() + timedelta(days=safe_days)).timestamp() * 1000)

                client_data = {
                    "id": client_id,
                    "email": client_email,
                    "enable": True,
                    "totalGB": total_gb,
                    "expiryTime": expiry_time,
                    "limitIp": 0,
                    "tgId": str(telegram_id),
                    "subId": ""
                }

                protocol_lower = (inbound_protocol or '').lower()
                if protocol_lower == 'vmess':
                    client_data['alterId'] = 0
                elif protocol_lower == 'vless':
                    client_data['flow'] = ''
                    if stream_settings.get('network') == 'tcp' and ((stream_settings.get('tcpSettings') or {}).get('header') or {}).get('type') == 'http':
                        client_data['flow'] = 'xtls-rprx-vision'
                elif protocol_lower == 'trojan':
                    client_data['password'] = client_id
                elif protocol_lower == 'shadowsocks':
                    import secrets
                    client_data['password'] = secrets.token_urlsafe(16)
                    inbound_method = (settings or {}).get('method')
                    client_data['method'] = inbound_method or 'aes-256-gcm'

                success = False
                creation_flow = "legacy"

                if use_unlimited_style:
                    unlimited_result = await panel.add_client_unlimited_style(
                        inbound=inbound,
                        email=client_email,
                        gb=gb,
                        days=safe_days,
                        telegram_id=telegram_id
                    )
                    if unlimited_result:
                        success = True
                        creation_flow = "unlimited-style"
                        client_id = unlimited_result.get('client_id') or client_id
                        client_email = unlimited_result.get('email') or client_email
                        client_data = unlimited_result.get('client_data') or client_data
                        expiry_time = int(client_data.get('expiryTime') or expiry_time)
                    else:
                        logger.warning("Unlimited-style creation failed, falling back to legacy addClient flow")

                if not success:
                    success = await panel.add_client_to_inbound(inbound_id, client_data)
                    if success:
                        creation_flow = "legacy-addClient"

                if not success:
                    success = await panel.update_inbound_client(inbound_id, client_data)
                    if success:
                        creation_flow = "legacy-updateInbound"

                if not success:
                    logger.warning(f"Provisioning failed on panel {panel_config.get('name')} (id={panel_config.get('id')})")
                    continue

                if use_location_sni:
                    manual_address = (panel_config.get('manual_address') or '').strip() or (address or '')
                    sni_value = manual_address
                    host_override = manual_address
                    server_arg = sni
                else:
                    manual_address = (panel_config.get('manual_address') or '').strip() or (address or '').strip()
                    sni_value = sni
                    host_override = ''
                    server_arg = manual_address

                subscription_link = generate_subscription_link(
                    protocol=inbound_protocol,
                    client_id=client_id,
                    email=client_email,
                    server=server_arg,
                    port=inbound_port,
                    stream_settings=stream_settings,
                    inbound_remark=inbound.get('remark', 'V2Ray'),
                    custom_sni=sni_value,
                    host_override=host_override
                )

                return {
                    "client_id": client_id,
                    "email": client_email,
                    "package": package_id,
                    "gb": gb,
                    "location": location['name'],
                    "expiry": expiry_time,
                    "inbound_tag": inbound.get('remark'),
                    "subscription_link": subscription_link,
                    "panel_url": panel_config['url'],
                    "panel_name": panel_config.get('name', 'Unknown'),
                    "port": inbound_port,
                    "protocol": inbound_protocol,
                    "creation_flow": creation_flow
                }
            finally:
                if panel:
                    with suppress(Exception):
                        await panel.close()
                    panel = None

        logger.error("Failed to create account on all panel candidates")
        return None
    except Exception as e:
        logger.error(f"Error creating V2Ray account: {e}")
        return None


async def revoke_v2ray_account(order: dict) -> bool:
    """Revoke an existing account from panel by removing client from inbound."""
    panel = None
    try:
        account_info = order.get('v2ray_config') or {}
        client_id = (account_info.get('client_id') or '').strip() or None
        email = (account_info.get('email') or '').strip() or None

        if not client_id and not email:
            logger.error("Cannot revoke account: v2ray_config has no client_id or email")
            return False

        location_id = order.get('location_id')
        locations = get_locations()
        location = resolve_location_config(location_id, locations)
        if not location:
            logger.error(f"Cannot revoke account: location not found ({location_id})")
            return False

        panels = get_panels()
        cfg = load_config()
        panel_candidates = get_location_panel_candidates(location, panels, cfg)
        if not panel_candidates:
            logger.error(f"Cannot revoke account: no panel candidates for location {location_id}")
            return False

        # port is used to find the right inbound; fall back gracefully
        raw_port = account_info.get('port') or order.get('user_package_port') or 443
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            logger.warning(f"Invalid port value '{raw_port}' for revoke, defaulting to 443")
            port = 443

        inbound_tag = account_info.get('inbound_tag') or location.get('inbound_tag') or ''

        for panel_config in panel_candidates:
            try:
                panel = PanelClient(panel_config)
                if not await panel.login():
                    continue

                # Try inbound by port first, then fall back to scanning by remark/tag
                inbound = await panel.get_inbound_by_port(port)
                if not inbound and inbound_tag:
                    all_inbounds = await panel.get_inbounds() or []
                    inbound = next(
                        (ib for ib in all_inbounds
                         if (ib.get('remark') or '').strip().lower() == inbound_tag.strip().lower()),
                        None
                    )
                if not inbound:
                    logger.warning(f"Revoke: inbound not found on panel {panel_config.get('name')} (port={port}, tag={inbound_tag})")
                    continue

                inbound_id = inbound.get('id')
                if inbound_id is None:
                    continue

                removed = await panel.remove_client_from_inbound(
                    inbound_id=inbound_id,
                    client_id=client_id,
                    email=email
                )
                if removed:
                    return True
            finally:
                if panel:
                    with suppress(Exception):
                        await panel.close()
                    panel = None

        return False
    except Exception as e:
        logger.error(f"Error revoking V2Ray account: {e}")
        return False


def generate_subscription_link(protocol: str, client_id: str, email: str, server: str, port: int, stream_settings: dict, inbound_remark: str, custom_sni: str = '', host_override: str = '') -> str:
    """Generate protocol-specific subscription link."""
    try:
        protocol_lower = (protocol or '').lower()

        if protocol_lower == 'vless':
            # Get security and flow from stream settings
            security = stream_settings.get('security', 'none')
            network = stream_settings.get('network', 'tcp')

            # Build VLESS link
            link = f"vless://{client_id}@{server}:{port}"
            params = [
                f"encryption=none",
                f"security={security}",
                f"type={network}"
            ]

            # Add TLS settings if present
            if security == 'tls' or security == 'reality':
                tls_settings = stream_settings.get('tlsSettings', {}) or stream_settings.get('realitySettings', {})
                if custom_sni:
                    params.append(f"sni={custom_sni}")
                if 'fingerprint' in tls_settings:
                    params.append(f"fp={tls_settings['fingerprint']}")
            # Add network-specific settings
            if network == 'ws':
                ws_settings = stream_settings.get('wsSettings', {})
                ws_path = ws_settings.get('path')
                if ws_path:
                    params.append(f"path={quote(ws_path)}")
                if host_override:
                    params.append(f"host={quote(host_override)}")
            elif network == 'grpc':
                grpc_settings = stream_settings.get('grpcSettings', {})
                if 'serviceName' in grpc_settings:
                    params.append(f"serviceName={quote(grpc_settings['serviceName'])}")

            link += "?" + "&".join(params)
            link += f"#{quote(email)}"
            return link
            
        elif protocol_lower == 'vmess':
            # Build VMess JSON
            vmess_config = {
                "v": "2",
                "ps": email,
                "add": server,
                "port": str(port),
                "id": client_id,
                "aid": "0",
                "net": stream_settings.get('network', 'tcp'),
                "type": "none",
                "host": "",
                "path": "",
                "tls": "tls" if stream_settings.get('security') == 'tls' else "",
                "scy": "auto",
                "fp": "chrome"
            }

            # Add network-specific settings
            if vmess_config['net'] == 'ws':
                ws_settings = stream_settings.get('wsSettings', {})
                vmess_config['path'] = ws_settings.get('path', '')
                vmess_config['host'] = ws_settings.get('headers', {}).get('Host', '')

            # If host_override is set ("Use Address as SNI"), override 'sni' and 'host'.
            # Keep 'add' as server when provided (so package SNI stays after @).
            if host_override and host_override.strip():
                if not vmess_config['add']:
                    vmess_config['add'] = host_override
                vmess_config['sni'] = host_override
                vmess_config['host'] = host_override
                # Add tlsSettings.serverName for TLS compatibility
                if vmess_config['tls'] == 'tls':
                    vmess_config['tlsSettings'] = {"serverName": host_override}
            # Otherwise, use custom_sni if provided
            elif custom_sni and custom_sni.strip():
                vmess_config['sni'] = custom_sni
                if vmess_config['net'] == 'ws':
                    vmess_config['host'] = custom_sni
                if vmess_config['tls'] == 'tls':
                    vmess_config['tlsSettings'] = {"serverName": custom_sni}

            vmess_json = json.dumps(vmess_config, indent=2)
            vmess_b64 = base64.b64encode(vmess_json.encode()).decode()
            return f"vmess://{vmess_b64}"

        elif protocol_lower == 'trojan':
            security = stream_settings.get('security', 'none')
            network = stream_settings.get('network', 'tcp')
            link = f"trojan://{client_id}@{server}:{port}"

            params = [f"type={network}"]

            if network == 'ws':
                ws_settings = stream_settings.get('wsSettings', {})
                ws_path = ws_settings.get('path') or '/'
                params.append(f"path={quote(ws_path)}")
                ws_host = host_override or ws_settings.get('headers', {}).get('Host', '')
                if ws_host:
                    params.append(f"host={quote(str(ws_host))}")
            elif network == 'grpc':
                grpc_settings = stream_settings.get('grpcSettings', {})
                service_name = grpc_settings.get('serviceName', '')
                if service_name:
                    params.append(f"serviceName={quote(str(service_name))}")

            if security in ('tls', 'reality'):
                params.append(f"security={security}")
                if custom_sni:
                    params.append(f"sni={quote(custom_sni)}")
            else:
                params.append("security=none")

            link += "?" + "&".join(params)
            link += f"#{quote(email)}"
            return link

        elif protocol_lower == 'shadowsocks':
            method = "aes-256-gcm"
            password = client_id

            userinfo = f"{method}:{password}"
            userinfo_b64 = base64.urlsafe_b64encode(userinfo.encode()).decode().rstrip('=')
            return f"ss://{userinfo_b64}@{server}:{port}#{quote(email)}"
        
        return f"# Configuration for {email} - Please configure manually"
    except Exception as e:
        logger.error(f"Error generating subscription link: {e}")
        return f"# Error generating link for {email}"


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Handle /start command - show language selection"""
    user_id = message.from_user.id
    
    # Track user ID in config
    try:
        config = load_config()
        user_ids = config.get('user_ids', [])
        if user_id not in user_ids:
            user_ids.append(user_id)
            config['user_ids'] = user_ids
            save_config(config)
            logger.info(f"New user tracked: {user_id}")
    except Exception as e:
        logger.error(f"Failed to track user {user_id}: {e}")
    
    # Show language selection
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="🇱🇰 සිංහල (Sinhala)", callback_data="lang_si")],
    ])
    
    await state.set_state(LanguageSelection.waiting_for_language)
    
    await message.answer(
        "🌐 <b>Select Your Preferred Language</b>\n\n"
        "Choose your language to continue:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.message(Command("active"))
async def cmd_active(message: types.Message):
    """Verify dashboard login code from admin via Telegram"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("❌ You are not authorized to use this command.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /active YOUR_CODE")
        return

    code = parts[1].strip().upper()
    if not code:
        await message.answer("Please provide a valid code. Example: /active ABC123")
        return

    config = load_config()
    verified_codes = config.get("verified_login_codes", [])

    if code not in verified_codes:
        verified_codes.append(code)
        config["verified_login_codes"] = verified_codes
        save_config(config)

    await message.answer("✅ Code verified. You can now use it to log in to the dashboard.")


@dp.message(Command("referral"))
async def cmd_referral(message: types.Message):
    """Show user their referral code and stats"""
    user_id = message.from_user.id
    config = load_config()
    messages = config.get('messages', {})
    language = 'en'
    from languages import get_custom_text
    
    # Check if user has any approved orders
    pending = config.get('pending_approvals', [])
    has_order = any(order.get('user_id') == user_id and order.get('status') == 'approved' for order in pending)
    
    # Get or create referral code for this user
    referral_codes = config.get('referral_codes', {})
    user_code = None
    
    # Find existing code for this user
    for code, code_info in referral_codes.items():
        if code_info.get('user_id') == user_id:
            user_code = code
            break
    
    # Generate new code if user doesn't have one and has approved order
    if not user_code and has_order:
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
        save_config(config)
    
    if not user_code:
        await message.answer(
            f"{get_custom_text(messages, language, 'referral_program')}\n\n"
            f"{get_custom_text(messages, language, 'referral_need_first_purchase')}",
            parse_mode="HTML"
        )
        return
    
    # Get stats
    code_info = referral_codes.get(user_code, {})
    used_count = code_info.get('used_count', 0)
    discount_percent = code_info.get('discount_percent', 10)
    
    # Check for pending referral rewards
    referral_rewards = config.get('referral_rewards', {})
    unused_rewards = []
    used_rewards = []
    
    if str(user_id) in referral_rewards:
        rewards_list = referral_rewards[str(user_id)]
        if isinstance(rewards_list, list):
            unused_rewards = [r for r in rewards_list if not r.get('used')]
            used_rewards = [r for r in rewards_list if r.get('used')]
        elif isinstance(rewards_list, dict):
            # Handle legacy single-reward format
            if not rewards_list.get('used'):
                unused_rewards = [rewards_list]
            else:
                used_rewards = [rewards_list]
    
    # Count how many people this user has referred
    referrals_count = sum(1 for order in pending if order.get('applied_referral_code') == user_code)
    
    # Build message
    referral_text = (
        f"{get_custom_text(messages, language, 'your_referral_program')}\n\n"
        f"<b>{get_custom_text(messages, language, 'your_referral_code')}:</b> <code>{user_code}</code>\n"
        f"{get_custom_text(messages, language, 'click_to_copy')}\n\n"
        f"{get_custom_text(messages, language, 'code_stats')}\n"
        f"• {get_custom_text(messages, language, 'referrals_count')}: <b>{used_count}</b>\n"
        f"• {get_custom_text(messages, language, 'discount_they_get')}: <b>{discount_percent}%</b>\n\n"
    )
    
    # Add reward status
    if unused_rewards:
        referral_text += (
            f"{get_custom_text(messages, language, 'pending_rewards_title')}\n"
            f"{get_custom_text(messages, language, 'pending_rewards_count', count=len(unused_rewards))}\n"
        )
        for i, reward in enumerate(unused_rewards, 1):
            referred_by_text = reward.get('from_referral_code', 'unknown')
            referral_text += f"   {get_custom_text(messages, language, 'pending_reward_item', index=i, discount_percent=reward.get('discount_percent', 10), code=referred_by_text)}\n"
        referral_text += f"\n{get_custom_text(messages, language, 'use_next_purchase')}\n\n"
    else:
        referral_text += (
            f"{get_custom_text(messages, language, 'no_pending_rewards')}\n"
            f"{get_custom_text(messages, language, 'no_pending_rewards_desc', discount_percent=discount_percent)}\n\n"
        )
    
    if used_rewards:
        referral_text += f"{get_custom_text(messages, language, 'used_rewards', count=len(used_rewards))}\n\n"
    
    referral_text += (
        f"{get_custom_text(messages, language, 'how_it_works')}\n"
        f"{get_custom_text(messages, language, 'how_it_works_steps', discount_percent=discount_percent)}\n\n"
        f"{get_custom_text(messages, language, 'share_this_message')}\n"
        f"{get_custom_text(messages, language, 'share_message_text', code=user_code, discount_percent=discount_percent)}"
    )
    
    await message.answer(referral_text, parse_mode="HTML")


@dp.message(Command("apply"))
async def cmd_apply_code(message: types.Message):
    """Apply referral code quickly - limited to 3 times per hour"""
    user_id = message.from_user.id
    config = load_config()
    messages = config.get('messages', {})
    language = 'en'
    from languages import get_custom_text
    
    # Parse command: /apply <code>
    parts = message.text.split()
    
    if len(parts) < 2:
        await message.answer(
            get_custom_text(messages, language, 'apply_invalid_format'),
            parse_mode="HTML"
        )
        return
    
    referral_code = parts[1].strip().upper()
    revenue_settings = get_revenue_retention_settings(config)
    claim_limit = revenue_settings['referral_claim_limit']
    claim_window_seconds = revenue_settings['referral_claim_window_minutes'] * 60
    admin_cooldown_seconds = revenue_settings['admin_coupon_cooldown_minutes'] * 60
    default_code_max_redemptions = revenue_settings['default_code_max_redemptions']
    
    current_time = datetime.now().timestamp()
    
    # Check active admin cooldown globally (blocks all code types)
    admin_cooldown = config.get('admin_cooldown', {})
    user_cooldowns = admin_cooldown.get(str(user_id), {})
    active_cooldown_until = None
    cooldown_data_updated = False
    
    for admin_id, cooldown_info in user_cooldowns.items():
        cooldown_until = cooldown_info.get('cooldown_until')
        if cooldown_until and current_time >= cooldown_until:
            cooldown_info['claim_count'] = 0
            cooldown_info['cooldown_until'] = None
            cooldown_data_updated = True
        elif cooldown_until and current_time < cooldown_until:
            if active_cooldown_until is None or cooldown_until > active_cooldown_until:
                active_cooldown_until = cooldown_until
    
    if cooldown_data_updated:
        admin_cooldown[str(user_id)] = user_cooldowns
        config['admin_cooldown'] = admin_cooldown
    
    if active_cooldown_until:
        remaining_seconds = int(active_cooldown_until - current_time)
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        await message.answer(
            get_custom_text(messages, language, 'apply_cooldown_active', minutes=minutes, seconds=seconds),
            parse_mode="HTML"
        )
        return
    
    # Check if referral claims are enabled
    if not config.get('referrals_enabled', True):
        await message.answer(
            get_custom_text(messages, language, 'apply_claims_disabled'),
            parse_mode="HTML"
        )
        return
    
    # Check rate limit (configurable attempts per configurable time window)
    apply_rate_limit = config.get('apply_rate_limit', {})
    window_start = current_time - claim_window_seconds
    
    user_attempts = apply_rate_limit.get(str(user_id), [])
    user_attempts = [ts for ts in user_attempts if ts > window_start]
    
    if len(user_attempts) >= claim_limit:
        oldest_attempt = min(user_attempts)
        time_until_reset = int((oldest_attempt + claim_window_seconds) - current_time)
        minutes = time_until_reset // 60
        seconds = time_until_reset % 60
        await message.answer(
            get_custom_text(messages, language, 'apply_rate_limited', attempts=len(user_attempts), minutes=minutes, seconds=seconds),
            parse_mode="HTML"
        )
        return
    
    # Load referral system data
    referral_codes = config.get('referral_codes', {})
    referral_usage = config.get('referral_usage', {})
    
    # Check if code exists
    if referral_code not in referral_codes:
        await message.answer(get_custom_text(messages, language, 'apply_code_not_found', code=referral_code), parse_mode="HTML")
        return
    
    code_info = referral_codes[referral_code]
    used_by_users = code_info.get('used_by', [])
    max_uses = code_info.get('max_uses')
    effective_max_uses = max_uses if max_uses is not None else (default_code_max_redemptions or None)
    
    # Check if code is expired (24 hours)
    created_at_str = code_info.get('created_at')
    if created_at_str:
        try:
            from datetime import datetime as dt_parser
            created_at = dt_parser.fromisoformat(created_at_str).timestamp()
            if current_time - created_at > 86400:  # 86400 seconds = 24 hours
                await message.answer(get_custom_text(messages, language, 'apply_code_expired', code=referral_code), parse_mode="HTML")
                return
        except Exception as e:
            logger.warning(f"Error parsing code creation time: {e}")
    
    # Check if code reached max uses
    if effective_max_uses and len(used_by_users) >= effective_max_uses:
        await message.answer(
            get_custom_text(messages, language, 'apply_code_max_uses', code=referral_code, max_uses=effective_max_uses),
            parse_mode="HTML"
        )
        return
    
    # Check if user already used this specific code (users can use multiple codes, but each code only once)
    if user_id in used_by_users:
        await message.answer(
            get_custom_text(messages, language, 'apply_code_already_used', code=referral_code),
            parse_mode="HTML"
        )
        return
    
    # Check if user is trying to use their own code
    if code_info.get('user_id') == user_id:
        await message.answer(
            get_custom_text(messages, language, 'apply_cannot_use_own'),
            parse_mode="HTML"
        )
        return
    
    # Apply the code
    discount_percent = code_info.get('discount_percent', 10)
    
    # Update code usage
    code_info['used_by'] = used_by_users + [user_id]
    code_info['used_count'] = code_info.get('used_count', 0) + 1
    referral_codes[referral_code] = code_info
    config['referral_codes'] = referral_codes
    
    # Create referral reward for code owner (if not admin coupon)
    if code_info.get('user_id'):  # Only reward user-generated codes, not admin coupons
        referral_rewards = config.get('referral_rewards', {})
        referrer_id = code_info.get('user_id')
        
        reward = {
            "reward_id": f"rew_apply_{user_id}_{int(current_time)}",
            "from_referral_code": referral_code,
            "from_referred_user_id": user_id,
            "discount_percent": discount_percent,
            "used": False,
            "created_at": datetime.now().isoformat(),
            "used_at": None,
            "used_on_order_id": None
        }
        
        if str(referrer_id) not in referral_rewards:
            referral_rewards[str(referrer_id)] = []
        
        referral_rewards[str(referrer_id)].append(reward)
        config['referral_rewards'] = referral_rewards
    
    # Update rate limit
    user_attempts.append(current_time)
    apply_rate_limit[str(user_id)] = user_attempts
    config['apply_rate_limit'] = apply_rate_limit
    
    # Update admin cooldown if this is an admin coupon
    if code_info.get('is_admin_coupon'):
        admin_id = code_info.get('created_by_admin_id')
        admin_cooldown = config.get('admin_cooldown', {})
        
        if str(user_id) not in admin_cooldown:
            admin_cooldown[str(user_id)] = {}
        
        if str(admin_id) not in admin_cooldown[str(user_id)]:
            admin_cooldown[str(user_id)][str(admin_id)] = {'claim_count': 0, 'cooldown_until': None}
        
        admin_cooldown_info = admin_cooldown[str(user_id)][str(admin_id)]
        admin_cooldown_info['claim_count'] += 1
        
        # If reached claim limit, set cooldown for configured minutes
        if admin_cooldown_info['claim_count'] >= claim_limit:
            admin_cooldown_info['cooldown_until'] = current_time + admin_cooldown_seconds
        
        config['admin_cooldown'] = admin_cooldown
        
        # Track claimed admin coupon for auto-apply at checkout
        claimed_admin_coupons = config.get('claimed_admin_coupons', {})
        if str(user_id) not in claimed_admin_coupons:
            claimed_admin_coupons[str(user_id)] = []
        
        claimed_admin_coupons[str(user_id)].append({
            'code': referral_code,
            'discount_percent': discount_percent,
            'claimed_at': current_time
        })
        config['claimed_admin_coupons'] = claimed_admin_coupons
    
    # Save all changes
    save_config(config)
    
    # Show success message
    if code_info.get('is_admin_coupon'):
        admin_id = code_info.get('created_by_admin_id')
        admin_cooldown = config.get('admin_cooldown', {})
        admin_cooldown_info = admin_cooldown.get(str(user_id), {}).get(str(admin_id), {'claim_count': 1})
        remaining_claims = max(0, claim_limit - admin_cooldown_info.get('claim_count', 0))
        
        success_message = (
            get_custom_text(
                messages,
                language,
                'apply_success_admin',
                code=referral_code,
                discount_percent=discount_percent,
                remaining_claims=remaining_claims
            )
        )
    else:
        success_message = (
            get_custom_text(
                messages,
                language,
                'apply_success_user',
                code=referral_code,
                discount_percent=discount_percent,
                remaining_attempts=max(0, claim_limit - len(user_attempts))
            )
        )
    await message.answer(success_message, parse_mode="HTML")


@dp.message(Command("genref"))
async def cmd_generate_referral(message: types.Message):
    """Admin command to generate multiple referral codes"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("❌ Only admins can generate referral codes.")
        return
    
    # Parse command: /genref <count> <discount> <max_uses>
    parts = message.text.split()

    if len(parts) < 4:
        await message.answer(
            "❌ <b>Invalid format!</b>\n\n"
            "<b>Usage:</b> <code>/genref &lt;count&gt; &lt;discount&gt; &lt;max_uses&gt;</code>\n\n"
            "<b>Example:</b> <code>/genref 5 15 10</code>\n\n"
            "This generates 5 codes with 15% discount, usable by max 10 users each.",
            parse_mode="HTML"
        )
        return

    try:
        count = int(parts[1])
        discount = int(parts[2])
        max_uses = int(parts[3])
    except ValueError:
        await message.answer("❌ All parameters must be numbers!")
        return
    
    # Validate parameters
    if count < 1 or count > 100:
        await message.answer("❌ Coupon count must be between 1 and 100")
        return
    
    if discount < 1 or discount > 100:
        await message.answer("❌ Discount must be between 1 and 100%")
        return
    
    if max_uses < 1 or max_uses > 1000:
        await message.answer("❌ Max uses must be between 1 and 1000")
        return
    
    # Load config
    config = load_config()
    referral_codes = config.get('referral_codes', {})
    
    # Generate codes
    generated_codes = []
    import random
    import string
    
    for i in range(count):
        # Generate unique code: ADMIN_XXXXXX (random alphanumeric)
        while True:
            code = f"ADMIN_{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
            if code not in referral_codes:
                break
        
        referral_codes[code] = {
            "user_id": None,  # Admin-generated, not from a user
            "created_at": datetime.now().isoformat(),
            "created_by_admin_id": user_id,
            "discount_percent": discount,
            "is_admin_coupon": True,
            "max_uses": max_uses,
            "used_count": 0,
            "used_by": []
        }
        generated_codes.append(code)
    
    # Save config
    config['referral_codes'] = referral_codes
    save_config(config)
    
    # Build response
    response_text = (
        f"✅ <b>Generated {count} Referral Codes</b>\n\n"
        f"💰 <b>Details:</b>\n"
        f"• Discount: <b>{discount}%</b>\n"
        f"• Max Uses Per Code: <b>{max_uses}</b>\n"
        f"• Total Codes: <b>{count}</b>\n\n"
        f"<b>Generated Codes:</b>\n"
    )
    
    for code in generated_codes:
        response_text += f"<code>{code}</code>\n"
    
    await message.answer(response_text, parse_mode="HTML")


@dp.message(Command("refstats"))
async def cmd_referral_stats(message: types.Message):
    """Admin command to view all referral code statistics"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("❌ Only admins can view referral statistics.")
        return
    
    config = load_config()
    referral_codes = config.get('referral_codes', {})
    
    if not referral_codes:
        await message.answer("❌ No referral codes exist yet.")
        return
    
    # Separate user codes and admin codes
    user_codes = []
    admin_codes = []
    
    for code, info in referral_codes.items():
        if info.get('is_admin_coupon'):
            admin_codes.append((code, info))
        else:
            user_codes.append((code, info))
    
    # Build stats message
    stats_text = f"📊 <b>Referral Code Statistics</b>\n\n"
    stats_text += f"<b>Total Codes:</b> {len(referral_codes)}\n"
    stats_text += f"├─ User Codes: {len(user_codes)}\n"
    stats_text += f"└─ Admin Coupons: {len(admin_codes)}\n\n"
    
    # User codes stats
    if user_codes:
        stats_text += f"<b>User-Generated Codes ({len(user_codes)}):</b>\n"
        total_referrals = 0
        for code, info in user_codes:
            used_by = info.get('used_by', [])
            discount = info.get('discount_percent', 10)
            total_referrals += len(used_by)
            stats_text += f"  <code>{code}</code> → {len(used_by)} uses, {discount}%\n"
        stats_text += f"  <b>Total Referrals:</b> {total_referrals}\n\n"
    
    # Admin codes stats
    if admin_codes:
        stats_text += f"<b>Admin-Generated Coupons ({len(admin_codes)}):</b>\n"
        total_admin_uses = 0
        for code, info in admin_codes:
            used_by = info.get('used_by', [])
            max_uses = info.get('max_uses', 'Unlimited')
            discount = info.get('discount_percent', 10)
            total_admin_uses += len(used_by)
            max_text = f" / {max_uses}" if max_uses != 'Unlimited' else ""
            stats_text += f"  <code>{code}</code> → {len(used_by)}{max_text} uses, {discount}%\n"
        stats_text += f"  <b>Total Admin Uses:</b> {total_admin_uses}\n\n"
    
    # Calculate rewards
    referral_rewards = config.get('referral_rewards', {})
    total_pending_rewards = sum(
        len([r for r in rewards if not r.get('used')]) 
        if isinstance(rewards, list) else (0 if rewards.get('used') else 1)
        for rewards in referral_rewards.values()
    )
    total_used_rewards = sum(
        len([r for r in rewards if r.get('used')]) 
        if isinstance(rewards, list) else (1 if rewards.get('used') else 0)
        for rewards in referral_rewards.values()
    )
    
    stats_text += (
        f"<b>Rewards Status:</b>\n"
        f"  Pending: {total_pending_rewards}\n"
        f"  Used: {total_used_rewards}\n"
    )
    
    await message.answer(stats_text, parse_mode="HTML")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """Start broadcast message process - admin only"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("❌ You are not authorized to use this command.")
        return

    await state.set_state(BroadcastMessage.waiting_for_message)
    await message.answer(
        "📢 <b>Broadcast Message</b>\n\n"
        "Send the message you want to broadcast to all users.\n\n"
        "<i>You can use HTML formatting (bold, italic, links, etc.)</i>",
        parse_mode="HTML"
    )


@dp.message(BroadcastMessage.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    """Send broadcast message to all tracked users"""
    user_id = message.from_user.id
    broadcast_text = message.text
    
    if not broadcast_text:
        await message.answer("❌ Please provide a valid message.")
        return
    
    try:
        config = load_config()
        user_ids = config.get('user_ids', [])
        
        if not user_ids:
            await message.answer("❌ No users in the database to broadcast to.")
            await state.clear()
            return
        
        successful = 0
        failed = 0
        
        # Send message to all tracked users
        for target_user_id in user_ids:
            try:
                await bot.send_message(
                    chat_id=target_user_id,
                    text=broadcast_text,
                    parse_mode="HTML"
                )
                successful += 1
            except Exception as e:
                logger.warning(f"Failed to send message to user {target_user_id}: {e}")
                failed += 1
        
        # Send summary to admin
        summary = (
            f"✅ <b>Broadcast Complete</b>\n\n"
            f"📊 Results:\n"
            f"✔️ Successful: {successful}/{len(user_ids)}\n"
            f"❌ Failed: {failed}/{len(user_ids)}"
        )
        
        await message.answer(summary, parse_mode="HTML")
        logger.info(f"Admin {user_id} broadcast to {successful} users. Failed: {failed}")
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        await message.answer(f"❌ Broadcast error: {str(e)}")
    
    finally:
        await state.clear()


@dp.callback_query(F.data.startswith("lang_"))
async def cb_select_language(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle language selection"""
    await callback_query.answer()
    language = callback_query.data.replace("lang_", "")
    
    # Store language in state
    await state.update_data(language=language)
    
    # Show main menu
    user_id = callback_query.from_user.id

    # Persist user language for command-based flows
    config = load_config()
    user_languages = config.get('user_languages', {})
    user_languages[str(user_id)] = language
    config['user_languages'] = user_languages
    save_config(config)
    
    messages = get_messages()
    from languages import get_custom_text
    keyboard_data = [
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'buy_account'), callback_data="buy_v2ray")],
    ]
    if is_admin(user_id):
        keyboard_data.append([InlineKeyboardButton(text=get_custom_text(messages, language, 'approve_orders'), callback_data="admin_approve")])
        keyboard_data.append([InlineKeyboardButton(text=get_custom_text(messages, language, 'orders_status'), callback_data="admin_orders")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_data)
    # Get welcome message from config (legacy key) or fallback to custom/default
    welcome_key = f'welcome_{language}'
    welcome_message = messages.get(welcome_key)
    if not welcome_message or not str(welcome_message).strip():
        welcome_message = get_custom_text(messages, language, 'welcome') + '\n\n' + get_custom_text(messages, language, 'welcome_desc')
    await callback_query.message.edit_text(
        welcome_message,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "buy_v2ray")
async def cb_buy_v2ray(callback_query: types.CallbackQuery, state: FSMContext):
    """Start purchase flow - show ISP selection"""
    await callback_query.answer()
    await state.set_state(PurchaseFlow.waiting_for_isp)
    
    # Get language from state (use 'en' as default)
    data = await state.get_data()
    language = data.get('language')
    if not language:
        config = load_config()
        user_languages = config.get('user_languages', {})
        language = user_languages.get(str(callback_query.from_user.id), 'en')
        await state.update_data(language=language)
    
    # Load ISP providers from config (always fresh)
    isp_providers = get_isp_providers()
    
    # Show ISP providers
    keyboard_rows = []
    for isp in isp_providers:
        btn_text = f"{isp['name']}"
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"isp_{isp['id']}")])
    
    # Add back button
    back_btn_text = get_text(language, 'back_to_main')
    keyboard_rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="back_to_main")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    messages = get_messages()
    from languages import get_custom_text
    title = get_custom_text(messages, language, 'select_isp')
    desc = get_custom_text(messages, language, 'select_isp_desc')

    await callback_query.message.edit_text(
        f"{title}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# Back button handlers
@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    """Go back to main menu"""
    language = await resolve_user_language(state, callback_query.from_user.id)

    # Clear purchase flow data but preserve language
    await state.clear()
    # Store language in state again to persist user's choice
    await state.set_state(LanguageSelection.waiting_for_language)
    await state.update_data(language=language)
    
    user_id = callback_query.from_user.id
    
    keyboard_data = [
        [InlineKeyboardButton(text=get_text(language, 'buy_account'), callback_data="buy_v2ray")],
    ]
    
    if is_admin(user_id):
        keyboard_data.append([InlineKeyboardButton(text=get_text(language, 'approve_orders'), callback_data="admin_approve")])
        keyboard_data.append([InlineKeyboardButton(text=get_text(language, 'orders_status'), callback_data="admin_orders")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_data)
    
    # Get welcome message from config (legacy key) or fallback to custom/default
    messages = get_messages()
    from languages import get_custom_text
    welcome_key = f'welcome_{language}'
    welcome_message = messages.get(welcome_key)
    if not welcome_message or not str(welcome_message).strip():
        welcome_message = get_custom_text(messages, language, 'welcome') + '\n\n' + get_custom_text(messages, language, 'welcome_desc')
    await callback_query.message.edit_text(
        welcome_message,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "back_to_isp")
async def cb_back_to_isp(callback_query: types.CallbackQuery, state: FSMContext):
    """Go back to ISP selection"""
    await callback_query.answer()
    await state.set_state(PurchaseFlow.waiting_for_isp)
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    # Load ISP providers from config (always fresh)
    isp_providers = get_isp_providers()
    
    # Show ISP providers
    keyboard_rows = []
    for isp in isp_providers:
        btn_text = f"{isp['name']}"
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"isp_{isp['id']}")])
    
    back_btn_text = get_text(language, 'back_to_main')
    keyboard_rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="back_to_main")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    messages = get_messages()
    from languages import get_custom_text
    title = get_custom_text(messages, language, 'select_isp')
    desc = get_custom_text(messages, language, 'select_isp_desc')

    await callback_query.message.edit_text(
        f"{title}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "back_to_user_package")
async def cb_back_to_user_package(callback_query: types.CallbackQuery, state: FSMContext):
    """Go back to user package selection"""
    await callback_query.answer()
    data = await state.get_data()
    isp_id = data.get('isp_id')
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    if not isp_id:
        # If no ISP selected, go to ISP selection
        await cb_back_to_isp(callback_query, state)
        return
    
    await state.set_state(PurchaseFlow.waiting_for_user_package)
    
    # Load ISP providers from config (always fresh)
    isp_providers = get_isp_providers()
    
    isp = next((p for p in isp_providers if p['id'] == isp_id), None)
    
    if not isp:
        await cb_back_to_isp(callback_query, state)
        return
    
    # Get packages specific to this ISP
    user_packages = isp.get('packages', [])
    
    # Show user packages as buttons
    keyboard_rows = []
    for user_pkg in user_packages:
        keyboard_rows.append([InlineKeyboardButton(text=user_pkg['name'], callback_data=f"usrpkg_{user_pkg['id']}")])
    
    back_btn_text = get_text(language, 'back_to_isp')
    keyboard_rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="back_to_isp")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    messages = get_messages()
    from languages import get_custom_text
    title = get_custom_text(messages, language, 'select_package')
    desc = get_custom_text(messages, language, 'select_package_desc', isp_name=isp['name'])

    await callback_query.message.edit_text(
        f"{title}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "back_to_v2ray_package")
async def cb_back_to_v2ray_package(callback_query: types.CallbackQuery, state: FSMContext):
    """Go back to V2Ray package selection"""
    await callback_query.answer()
    data = await state.get_data()
    user_package = data.get('user_package')
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    if not user_package:
        # If no user package selected, go back to user package selection
        await cb_back_to_user_package(callback_query, state)
        return
    
    await state.set_state(PurchaseFlow.waiting_for_package)
    
    messages = get_messages()
    from languages import get_custom_text

    # Show our packages (reload from config)
    packages = get_packages()
    currency = get_currency()
    keyboard_rows = []
    for pkg in packages:
        gb_label = get_custom_text(messages, language, 'gb')
        unlimited_label = get_custom_text(messages, language, 'unlimited')
        per_month_label = get_custom_text(messages, language, 'per_month')
        gb_text = f"{pkg['gb']}{gb_label}" if pkg['gb'] > 0 else unlimited_label
        btn_text = f"📦 {pkg['name']} - {gb_text} - {currency} {pkg['price']:.2f}{per_month_label}"
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"pkg_{pkg['id']}")])
    
    back_btn_text = get_custom_text(messages, language, 'back_to_package')
    keyboard_rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="back_to_user_package")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    title = get_custom_text(messages, language, 'select_v2ray_package')
    desc = get_custom_text(messages, language, 'select_v2ray_desc')
    using_text = get_custom_text(messages, language, 'using', name=user_package)

    await callback_query.message.edit_text(
        f"{using_text}\n\n{title}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("isp_"))
async def cb_select_isp(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle ISP selection"""
    await callback_query.answer()
    isp_id = callback_query.data.replace("isp_", "")
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    # Load ISP providers from config (always fresh)
    isp_providers = get_isp_providers()
    
    isp = next((p for p in isp_providers if p['id'] == isp_id), None)
    
    if not isp:
        error_text = get_text(language, 'isp_not_found')
        await callback_query.message.edit_text(error_text)
        return
    
    await state.update_data(isp_id=isp_id, isp_name=isp['name'])
    await state.set_state(PurchaseFlow.waiting_for_user_package)
    
    # Get packages specific to this ISP
    user_packages = isp.get('packages', [])
    
    if not user_packages:
        error_text = get_text(language, 'no_packages_available', name=isp['name'])
        await callback_query.message.edit_text(error_text)
        return
    
    # Show user packages as buttons
    keyboard_rows = []
    for user_pkg in user_packages:
        keyboard_rows.append([InlineKeyboardButton(text=user_pkg['name'], callback_data=f"usrpkg_{user_pkg['id']}")])
    
    # Add back button
    back_btn_text = get_text(language, 'back_to_isp')
    keyboard_rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="back_to_isp")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    messages = get_messages()
    from languages import get_custom_text
    title = get_custom_text(messages, language, 'select_package')
    desc = get_custom_text(messages, language, 'select_package_desc', isp_name=isp['name'])
    you_selected = get_custom_text(messages, language, 'you_selected', name=isp['name'])

    await callback_query.message.edit_text(
        f"{title}\n\n{you_selected}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("usrpkg_"))
async def cb_select_user_package(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle user package selection"""
    await callback_query.answer()
    user_pkg_id = callback_query.data.replace("usrpkg_", "")
    
    # Get stored ISP data
    data = await state.get_data()
    isp_id = data.get('isp_id')
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    # Load ISP providers from config (always fresh)
    isp_providers = get_isp_providers()
    
    isp = next((p for p in isp_providers if p['id'] == isp_id), None)
    if not isp:
        error_text = get_text(language, 'isp_not_found')
        await callback_query.message.edit_text(error_text)
        return
    
    user_packages = isp.get('packages', [])
    user_pkg = next((p for p in user_packages if p['id'] == user_pkg_id), None)
    
    if not user_pkg:
        error_text = get_text(language, 'package_not_found')
        await callback_query.message.edit_text(error_text)
        return
    
    # Store user package details including SNI, address, port, and use_location_sni flag
    await state.update_data(
        user_package=user_pkg['name'], 
        user_package_id=user_pkg_id,
        user_package_sni=user_pkg.get('sni', ''),
        user_package_address=user_pkg.get('address', ''),
        user_package_port=user_pkg.get('port', 443),
        user_package_use_location_sni=user_pkg.get('use_location_sni', False)
    )
    
    # Check if custom packages are enabled
    custom_config = get_custom_package_config()
    
    messages = get_messages()
    from languages import get_custom_text
    
    if custom_config['enabled']:
        # Show choice between predefined and custom packages
        await state.set_state(PurchaseFlow.waiting_for_package_type)
        
        keyboard_rows = [
            [InlineKeyboardButton(text=get_custom_text(messages, language, 'predefined_packages') or "📦 Predefined Packages", callback_data="pkgtype_predefined")],
            [InlineKeyboardButton(text=get_custom_text(messages, language, 'custom_package') or "✨ Custom Package", callback_data="pkgtype_custom")],
            [InlineKeyboardButton(text=get_custom_text(messages, language, 'back_to_package') or "🔙 Back", callback_data="back_to_user_package")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        
        title = get_custom_text(messages, language, 'select_package_type') or "Choose Package Type"
        desc = get_custom_text(messages, language, 'select_package_type_desc') or "Would you like to choose from our predefined packages or create a custom package?"
        using_text = get_custom_text(messages, language, 'using', name=user_pkg['name'])
        
        await callback_query.message.edit_text(
            f"{using_text}\n\n{title}\n\n{desc}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        # Go directly to predefined packages
        await show_predefined_packages(callback_query, state, user_pkg['name'])


async def show_predefined_packages(callback_query: types.CallbackQuery, state: FSMContext, user_package_name: str):
    """Show predefined V2Ray packages"""
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    await state.set_state(PurchaseFlow.waiting_for_package)
    
    messages = get_messages()
    from languages import get_custom_text

    # Show our packages (reload from config)
    packages = get_packages()
    currency = get_currency()
    keyboard_rows = []
    for pkg in packages:
        gb_label = get_custom_text(messages, language, 'gb')
        unlimited_label = get_custom_text(messages, language, 'unlimited')
        per_month_label = get_custom_text(messages, language, 'per_month')
        gb_text = f"{pkg['gb']}{gb_label}" if pkg['gb'] > 0 else unlimited_label
        btn_text = f"{pkg['name']} - {gb_text} - {currency} {pkg['price']:.2f}{per_month_label}"
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"pkg_{pkg['id']}")])
    
    # Add back button
    back_btn_text = get_custom_text(messages, language, 'back_to_package')
    keyboard_rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="back_to_user_package")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    title = get_custom_text(messages, language, 'select_v2ray_package')
    desc = get_custom_text(messages, language, 'select_v2ray_desc')
    using_text = get_custom_text(messages, language, 'using', name=user_package_name)

    await callback_query.message.edit_text(
        f"{using_text}\n\n{title}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "pkgtype_predefined")
async def cb_select_predefined_package_type(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle selection of predefined package type"""
    await callback_query.answer()
    data = await state.get_data()
    user_package_name = data.get('user_package', '')
    await show_predefined_packages(callback_query, state, user_package_name)


@dp.callback_query(F.data == "pkgtype_custom")
async def cb_select_custom_package_type(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle selection of custom package type"""
    await callback_query.answer()
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    await state.set_state(PurchaseFlow.waiting_for_custom_gb)
    
    messages = get_messages()
    from languages import get_custom_text
    
    custom_config = get_custom_package_config()
    pricing = custom_config['pricing']
    
    min_gb = pricing.get('min_gb', 10)
    max_gb = pricing.get('max_gb', 1000)
    price_per_gb = pricing.get('price_per_gb', 2.0)
    currency = get_currency()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'back') or "🔙 Back", callback_data="back_to_user_package")]
    ])
    
    title = get_custom_text(messages, language, 'enter_custom_gb') or "Enter Data Amount (GB)"
    desc = get_custom_text(
        messages,
        language,
        'enter_custom_gb_desc',
        min_gb=min_gb,
        max_gb=max_gb,
        price_per_gb=f"{price_per_gb:.2f}",
        currency=currency,
    ) or f"Please enter how many GB you need (between {min_gb} and {max_gb} GB).\n\nPrice: {currency} {price_per_gb:.2f} per GB"
    
    await callback_query.message.edit_text(
        f"{title}\n\n{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.message(PurchaseFlow.waiting_for_custom_gb)
async def process_custom_gb(message: types.Message, state: FSMContext):
    """Process custom GB input"""
    data = await state.get_data()
    language = await resolve_user_language(state, message.from_user.id)
    
    try:
        gb = int(message.text.strip())
        
        custom_config = get_custom_package_config()
        pricing = custom_config['pricing']
        min_gb = pricing.get('min_gb', 10)
        max_gb = pricing.get('max_gb', 1000)
        
        if gb < min_gb or gb > max_gb:
            messages = get_messages()
            from languages import get_custom_text
            error_msg = get_custom_text(
                messages,
                language,
                'invalid_gb_range',
                min_gb=min_gb,
                max_gb=max_gb,
            ) or f"❌ Please enter a value between {min_gb} and {max_gb} GB."
            await message.answer(error_msg)
            return
        
        await state.update_data(custom_gb=gb)
        await state.set_state(PurchaseFlow.waiting_for_custom_days)
        
        messages = get_messages()
        from languages import get_custom_text
        
        min_days = pricing.get('min_days', 1)
        max_days = pricing.get('max_days', 365)
        price_per_day = pricing.get('price_per_day', 5.0)
        currency = get_currency()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_custom_text(messages, language, 'back') or "🔙 Back", callback_data="back_to_user_package")]
        ])
        
        title = get_custom_text(messages, language, 'enter_custom_days') or "Enter Duration (Days)"
        desc = get_custom_text(
            messages,
            language,
            'enter_custom_days_desc',
            min_days=min_days,
            max_days=max_days,
            price_per_day=f"{price_per_day:.2f}",
            currency=currency,
        ) or f"Please enter how many days you need (between {min_days} and {max_days} days).\n\nPrice: {currency} {price_per_day:.2f} per day"
        
        await message.answer(
            f"{title}\n\n{desc}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    except ValueError:
        messages = get_messages()
        from languages import get_custom_text
        error_msg = get_custom_text(messages, language, 'invalid_number') or "❌ Please enter a valid number."
        await message.answer(error_msg)


@dp.message(PurchaseFlow.waiting_for_custom_days)
async def process_custom_days(message: types.Message, state: FSMContext):
    """Process custom days input and show location selection"""
    data = await state.get_data()
    language = await resolve_user_language(state, message.from_user.id)
    
    try:
        days = int(message.text.strip())
        
        custom_config = get_custom_package_config()
        pricing = custom_config['pricing']
        min_days = pricing.get('min_days', 1)
        max_days = pricing.get('max_days', 365)
        
        if days < min_days or days > max_days:
            messages = get_messages()
            from languages import get_custom_text
            error_msg = get_custom_text(
                messages,
                language,
                'invalid_days_range',
                min_days=min_days,
                max_days=max_days,
            ) or f"❌ Please enter a value between {min_days} and {max_days} days."
            await message.answer(error_msg)
            return
        
        custom_gb = data.get('custom_gb', 0)
        price = calculate_custom_package_price(custom_gb, days)
        
        await state.update_data(
            custom_days=days,
            package_id='custom',
            package_name=f'Custom {custom_gb}GB / {days} days',
            gb=custom_gb,
            days=days,
            total_price=price,
            is_custom_package=True
        )
        await state.set_state(PurchaseFlow.waiting_for_location)
        
        # Show locations (reload from config)
        locations = get_locations()
        currency = get_currency()
        keyboard_rows = []
        for location in locations:
            btn_text = f"{location['name']} - {location['description']}"
            keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"loc_{location['id']}")])
        
        messages = get_messages()
        from languages import get_custom_text
        
        back_to_v2ray_text = get_custom_text(messages, language, 'back_to_v2ray_package') or "🔙 Back to V2Ray Packages"
        keyboard_rows.append([InlineKeyboardButton(text=back_to_v2ray_text, callback_data="back_to_user_package")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        
        title = get_custom_text(messages, language, 'select_location')
        desc = get_custom_text(messages, language, 'select_location_desc')
        
        await message.answer(
            f"{title}\n\n"
            f"{get_custom_text(messages, language, 'package_info') or 'Package'}: {custom_gb}GB / {days} days (Custom)\n"
            f"{get_custom_text(messages, language, 'data') or 'Data'}: {custom_gb}GB\n"
            f"{get_custom_text(messages, language, 'duration') or 'Duration'}: {days} days\n"
            f"{get_custom_text(messages, language, 'price') or 'Price'}: {currency} {price:.2f}\n\n"
            f"{desc}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    except ValueError:
        messages = get_messages()
        from languages import get_custom_text
        error_msg = get_custom_text(messages, language, 'invalid_number') or "❌ Please enter a valid number."
        await message.answer(error_msg)


@dp.callback_query(F.data.startswith("pkg_"))
async def cb_select_package(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle package selection"""
    await callback_query.answer()
    package_id = callback_query.data.replace("pkg_", "")

    data = await state.get_data()
    language = await resolve_user_language(state, callback_query.from_user.id)

    packages = get_packages()
    package = next((p for p in packages if p['id'] == package_id), None)

    if not package:
        await callback_query.message.edit_text(get_text(language, 'package_not_found'))
        return

    gb = package['gb']
    price = package['price']

    await state.update_data(
        package_id=package_id,
        package_name=package['name'],
        gb=gb,
        total_price=price
    )
    await state.set_state(PurchaseFlow.waiting_for_location)

    # Show locations (reload from config)
    locations = get_locations()
    currency = get_currency()
    keyboard_rows = []
    for location in locations:
        btn_text = f"{location['name']} - {location['description']}"
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"loc_{location['id']}")])

    messages = get_messages()
    from languages import get_custom_text
    # Add back button
    back_to_v2ray_text = get_custom_text(messages, language, 'back_to_v2ray_package') or "🔙 Back to V2Ray Packages"
    keyboard_rows.append([InlineKeyboardButton(text=back_to_v2ray_text, callback_data="back_to_v2ray_package")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    title = get_custom_text(messages, language, 'select_location')
    desc = get_custom_text(messages, language, 'select_location_desc')
    gb_label = get_custom_text(messages, language, 'gb')
    unlimited_label = get_custom_text(messages, language, 'unlimited')
    gb_text = f"{gb}{gb_label}" if gb > 0 else unlimited_label
    await callback_query.message.edit_text(
        f"{title}\n\n"
        f"{get_custom_text(messages, language, 'package_info') or 'Package'}: {package['name']}\n"
        f"{get_custom_text(messages, language, 'data') or 'Data'}: {gb_text}\n"
        f"{get_custom_text(messages, language, 'price') or 'Price'}: {currency} {price:.2f}\n\n"
        f"{desc}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("loc_"))
async def cb_select_location(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle location selection and ask for referral code"""
    await callback_query.answer()
    location_id = callback_query.data.replace("loc_", "")
    language = await resolve_user_language(state, callback_query.from_user.id)
    locations = get_locations()
    location = next((l for l in locations if l['id'] == location_id), None)
    
    if not location:
        await callback_query.message.edit_text(get_text(language, 'location_not_found'))
        return
    
    await state.update_data(location_id=location_id)

    if is_admin(callback_query.from_user.id):
        await state.update_data(admin_direct_create=True)
        await callback_query.message.edit_text(
            "👤 <b>Enter Client Name</b>\n\n"
            "Admin direct-create mode is enabled.\n"
            "Payment and receipt are skipped for this flow.\n\n"
            "Send client name now:",
            parse_mode="HTML"
        )
        await state.set_state(PurchaseFlow.waiting_for_client_name)
        return

    await state.update_data(admin_direct_create=False)
    
    # Automatically proceed to payment method with auto-applied rewards
    await show_payment_methods(callback_query, state)


async def create_admin_direct_account(message: types.Message, state: FSMContext):
    """Admin-only direct account creation without payment/receipt."""
    data = await state.get_data()
    user_id = message.from_user.id
    language = await resolve_user_language(state, user_id)

    location_id = data.get('location_id')
    locations = get_locations()
    location = next((l for l in locations if l.get('id') == location_id), None)
    if not location:
        await message.answer(get_text(language, 'location_not_found'))
        return

    telegram_username = (message.from_user.username or f"user{user_id}").replace('@', '')
    account_info = await create_v2ray_account(
        data.get('package_id'),
        data.get('gb', 0),
        location_id,
        telegram_username,
        user_id,
        data.get('user_package_sni', ''),
        data.get('user_package_port', 443),
        data.get('user_package_use_location_sni', False),
        data.get('user_package_address', ''),
        data.get('client_name'),
        data.get('days') or 30,
    )

    if not account_info:
        await message.answer("❌ Failed to create account. Please check panel connectivity and try again.")
        return

    direct_order = {
        "order_id": f"ADMIN_DIRECT_{user_id}_{int(datetime.now().timestamp())}",
        "user_id": user_id,
        "username": message.from_user.username or "No username",
        "package_name": data.get('package_name'),
        "gb": data.get('gb', 0),
        "location_id": location_id,
        "status": "approved",
        "approved_at": datetime.now().isoformat(),
        "approved_by": user_id,
        "is_admin_direct_create": True,
        "total_price": 0,
    }

    cfg = load_config()
    if 'admin_created_accounts' not in cfg or not isinstance(cfg.get('admin_created_accounts'), list):
        cfg['admin_created_accounts'] = []
    cfg['admin_created_accounts'].append({
        **direct_order,
        "v2ray_config": account_info,
        "created_at": datetime.now().isoformat(),
    })
    save_config(cfg)

    account_msg = build_account_message(direct_order, account_info, cfg, language)
    invite_button = await build_premium_invite_button(user_id, cfg)
    if invite_button:
        await message.answer(account_msg, parse_mode="HTML", reply_markup=invite_button)
    else:
        await message.answer(account_msg, parse_mode="HTML")

    await send_account_ready_to_channel(direct_order, account_msg, cfg)
    await send_panel_backup_to_channel(direct_order, account_info, cfg)

    await state.clear()
    await state.update_data(language=language)


@dp.callback_query(F.data == "ref_skip")
async def cb_skip_referral(callback_query: types.CallbackQuery, state: FSMContext):
    """Skip referral code and proceed to payment method"""
    await callback_query.answer()
    await show_payment_methods(callback_query, state)


@dp.message(PurchaseFlow.waiting_for_referral_code)
async def handle_referral_code(message: types.Message, state: FSMContext):
    """Handle referral code input"""
    await message.delete()
    
    referral_code = message.text.strip().upper()
    data = await state.get_data()
    language = 'en'
    messages = get_messages()
    from languages import get_custom_text
    
    # Load referral codes from config
    config = load_config()
    referral_codes = config.get('referral_codes', {})
    user_id = message.from_user.id
    current_time = datetime.now().timestamp()
    revenue_settings = get_revenue_retention_settings(config)
    claim_limit = revenue_settings['referral_claim_limit']
    admin_cooldown_seconds = revenue_settings['admin_coupon_cooldown_minutes'] * 60
    default_code_max_redemptions = revenue_settings['default_code_max_redemptions']
    coupon_min_order_amount = revenue_settings['coupon_min_order_amount']

    order_amount = float(data.get('total_price') or 0)
    if coupon_min_order_amount > 0 and order_amount < coupon_min_order_amount:
        await message.answer(
            f"❌ Coupon/referral discount is available only for orders from {coupon_min_order_amount:.2f} {get_currency()}.")
        await show_payment_methods(message, state)
        return
    
    # Check active admin cooldown globally (blocks all code types)
    admin_cooldown = config.get('admin_cooldown', {})
    user_cooldowns = admin_cooldown.get(str(user_id), {})
    active_cooldown_until = None
    cooldown_data_updated = False
    
    for admin_id, cooldown_info in user_cooldowns.items():
        cooldown_until = cooldown_info.get('cooldown_until')
        if cooldown_until and current_time >= cooldown_until:
            cooldown_info['claim_count'] = 0
            cooldown_info['cooldown_until'] = None
            cooldown_data_updated = True
        elif cooldown_until and current_time < cooldown_until:
            if active_cooldown_until is None or cooldown_until > active_cooldown_until:
                active_cooldown_until = cooldown_until
    
    if cooldown_data_updated:
        admin_cooldown[str(user_id)] = user_cooldowns
        config['admin_cooldown'] = admin_cooldown
        save_config(config)
    
    if active_cooldown_until:
        remaining_seconds = int(active_cooldown_until - current_time)
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        await message.answer(
            f"⏰ <b>Cooldown Active</b>\n\n"
            f"You cannot claim any code right now.\n\n"
            f"<b>Cool Down Time:</b> {minutes}m {seconds}s\n"
            f"<i>During this cool down time, you cannot claim admin or referral codes.</i>",
            parse_mode="HTML"
        )
        await show_payment_methods(message, state)
        return
    
    # Referral usage map (for normal referral codes only)
    referral_usage = config.get('referral_usage', {})  # Maps user_id -> used_code
    
    # Check if code is valid
    valid_code = False
    discount_percent = 0
    referrer_id = None
    
    if referral_code in referral_codes:
        code_info = referral_codes[referral_code]
        referrer_id = code_info.get('user_id')
        used_by_users = code_info.get('used_by', [])  # List of user_ids who have used this code
        max_uses = code_info.get('max_uses')  # Max uses for this code (if admin-generated)
        effective_max_uses = max_uses if max_uses is not None else (default_code_max_redemptions or None)
        
        # Check if code is expired (24 hours)
        created_at_str = code_info.get('created_at')
        if created_at_str:
            try:
                from datetime import datetime as dt_parser
                created_at = dt_parser.fromisoformat(created_at_str).timestamp()
                if current_time - created_at > 86400:  # 86400 seconds = 24 hours
                    error_text = f"❌ This referral code has expired (valid for 24 hours only). Please try another code."
                    await message.answer(error_text)
                    await show_payment_methods(message, state)
                    return
            except Exception as e:
                logger.warning(f"Error parsing code creation time: {e}")
        
        # Check if code has exceeded max uses (for admin-generated coupons)
        if effective_max_uses and len(used_by_users) >= effective_max_uses:
            error_text = f"❌ This referral code has reached its maximum uses ({effective_max_uses}). Please try another code."
            await message.answer(error_text)
            await show_payment_methods(message, state)
            return
        
        # Check if user is trying to use their own code
        if referrer_id == user_id:
            error_text = get_custom_text(messages, language, 'cannot_use_own_code') or '❌ You cannot use your own referral code'
            await message.answer(error_text)
            await show_payment_methods(message, state)
            return
        
        # Check if this user has already used this specific code (users can use multiple codes, but each code only once)
        if user_id in used_by_users:
            error_text = "❌ You've already used this referral code once."
            await message.answer(error_text)
            await show_payment_methods(message, state)
            return
        
        # Code is valid if it exists and has discount
        valid_code = True
        discount_percent = code_info.get('discount_percent', 10)
    else:
        # Invalid code
        error_text = get_custom_text(messages, language, 'invalid_referral_code') or '❌ Invalid or expired referral code'
        await message.answer(error_text)
        await show_payment_methods(message, state)
        return
    
    # Apply referral code and discount if valid
    if valid_code:
        base_price = data.get('total_price', 0)
        discount_amount = int(base_price * discount_percent / 100)
        final_price = base_price - discount_amount
        
        await state.update_data(
            applied_referral_code=referral_code,
            original_price=base_price,
            discount_amount=discount_amount,
            total_price=final_price,
            referrer_id=referrer_id,
            was_referred_as_new_user=True
        )
        
        # Track that this code was used by this user
        referral_codes[referral_code]['used_by'] = used_by_users + [user_id]
        referral_codes[referral_code]['used_count'] = referral_codes[referral_code].get('used_count', 0) + 1
        config['referral_codes'] = referral_codes
        
        # Update admin cooldown counter for admin-generated coupons
        if code_info.get('is_admin_coupon'):
            admin_id = code_info.get('created_by_admin_id')
            admin_cooldown = config.get('admin_cooldown', {})
            
            if str(user_id) not in admin_cooldown:
                admin_cooldown[str(user_id)] = {}
            
            if str(admin_id) not in admin_cooldown[str(user_id)]:
                admin_cooldown[str(user_id)][str(admin_id)] = {'claim_count': 0, 'cooldown_until': None}
            
            admin_cooldown_info = admin_cooldown[str(user_id)][str(admin_id)]
            admin_cooldown_info['claim_count'] += 1
            
            if admin_cooldown_info['claim_count'] >= claim_limit:
                admin_cooldown_info['cooldown_until'] = current_time + admin_cooldown_seconds
            
            config['admin_cooldown'] = admin_cooldown

        save_config(config)
        
        # Show confirmation
        applied_text = get_custom_text(messages, language, 'referral_code_applied') or '✅ Referral code applied!'
        applied_text = applied_text.replace('{discount_percent}', str(discount_percent))
        await message.answer(applied_text)
    
    await show_payment_methods(message, state)


async def show_payment_methods(msg: types.Message | types.CallbackQuery, state: FSMContext):
    """Show payment method selection"""
    if isinstance(msg, types.CallbackQuery):
        message = msg.message
    else:
        message = msg
    
    data = await state.get_data()
    user_id = msg.from_user.id if hasattr(msg, 'from_user') else msg.message.from_user.id
    language = await resolve_user_language(state, user_id)
    location_id = data.get('location_id')
    
    if not location_id:
        await message.answer(get_text(language, 'location_not_found'))
        return
    
    locations = get_locations()
    location = next((l for l in locations if l['id'] == location_id), None)
    
    if not location:
        await message.answer(get_text(language, 'location_not_found'))
        return
    
    gb = data.get('gb', 0)
    
    # Get payment methods
    payment_details = get_payment_details()
    methods = payment_details.get('methods', [])
    messages = get_messages()
    from languages import get_custom_text
    gb_label = get_custom_text(messages, language, 'gb')
    unlimited_label = get_custom_text(messages, language, 'unlimited')
    gb_text = f"{gb}{gb_label}" if gb > 0 else unlimited_label
    
    # Check for pending referral rewards and AUTO-APPLY ALL
    config = load_config()
    revenue_settings = get_revenue_retention_settings(config)
    coupon_min_order_amount = revenue_settings['coupon_min_order_amount']
    referral_rewards = config.get('referral_rewards', {})
    
    # Build price display with discount if applicable
    base_price = data.get('original_price') or data.get('total_price', 0)
    final_price = data.get('total_price', base_price)
    
    # AUTO-APPLY best eligible discount (single best reward/coupon)
    used_reward_ids = []
    total_reward_discount = 0
    applied_rewards_count = 0
    
    reward_candidates: List[Dict[str, Any]] = []
    if str(user_id) in referral_rewards and isinstance(referral_rewards[str(user_id)], list):
        for reward in referral_rewards[str(user_id)]:
            if reward.get('used'):
                continue
            discount_percent = int(reward.get('discount_percent', 10) or 10)
            discount_amount = int(final_price * discount_percent / 100)
            if discount_amount > 0:
                reward_candidates.append({
                    'kind': 'reward',
                    'reward_id': reward.get('reward_id'),
                    'discount_percent': discount_percent,
                    'discount_amount': discount_amount,
                })
    elif str(user_id) in referral_rewards and isinstance(referral_rewards[str(user_id)], dict):
        reward_info = referral_rewards[str(user_id)]
        if not reward_info.get('used'):
            discount_percent = int(reward_info.get('discount_percent', 10) or 10)
            discount_amount = int(final_price * discount_percent / 100)
            if discount_amount > 0:
                reward_candidates.append({
                    'kind': 'reward',
                    'reward_id': reward_info.get('reward_id'),
                    'discount_percent': discount_percent,
                    'discount_amount': discount_amount,
                })
    
    # AUTO-APPLY valid claimed admin coupons
    claimed_admin_coupons = config.get('claimed_admin_coupons', {})
    referral_codes = config.get('referral_codes', {})
    applied_coupon_codes = []
    total_coupon_discount = 0
    applied_coupons_count = 0

    # Build unique coupon list from both tracking sources:
    # 1) claimed_admin_coupons (new tracking)
    # 2) referral_codes[*].used_by (fallback for older claims)
    coupons_to_apply = {}

    if str(user_id) in claimed_admin_coupons:
        for coupon in claimed_admin_coupons[str(user_id)]:
            code = coupon.get('code')
            if code:
                coupons_to_apply[code] = coupon.get('discount_percent', 10)

    for code, code_info in referral_codes.items():
        if code_info.get('is_admin_coupon') and user_id in code_info.get('used_by', []):
            if code not in coupons_to_apply:
                coupons_to_apply[code] = code_info.get('discount_percent', 10)

    coupon_candidates: List[Dict[str, Any]] = []
    for code, discount_percent in coupons_to_apply.items():
        discount_amount = int(final_price * int(discount_percent) / 100)
        if discount_amount > 0:
            coupon_candidates.append({
                'kind': 'coupon',
                'code': code,
                'discount_percent': int(discount_percent),
                'discount_amount': discount_amount,
            })

    if coupon_min_order_amount > 0 and base_price < coupon_min_order_amount:
        await state.update_data(
            referral_reward_discount=False,
            used_reward_ids=[],
            discount_amount_reward=0,
            applied_rewards_count=0,
            applied_admin_coupons=False,
            applied_coupon_codes=[],
            discount_amount_coupon=0,
            applied_coupons_count=0,
            total_price=base_price
        )
        final_price = base_price
    else:
        all_candidates = reward_candidates + coupon_candidates
        if all_candidates:
            selected = max(
                all_candidates,
                key=lambda item: (item.get('discount_amount', 0), item.get('discount_percent', 0), 1 if item.get('kind') == 'reward' else 0)
            )
            final_price = final_price - int(selected.get('discount_amount', 0))

            if selected.get('kind') == 'reward':
                used_reward_ids = [selected.get('reward_id')] if selected.get('reward_id') else []
                total_reward_discount = int(selected.get('discount_amount', 0))
                applied_rewards_count = 1
                await state.update_data(
                    referral_reward_discount=True,
                    used_reward_ids=used_reward_ids,
                    original_price=base_price,
                    original_price_reward=data.get('total_price', base_price),
                    discount_amount_reward=total_reward_discount,
                    applied_rewards_count=applied_rewards_count,
                    applied_admin_coupons=False,
                    applied_coupon_codes=[],
                    discount_amount_coupon=0,
                    applied_coupons_count=0,
                    total_price=final_price
                )
            else:
                applied_coupon_codes = [selected.get('code')] if selected.get('code') else []
                total_coupon_discount = int(selected.get('discount_amount', 0))
                applied_coupons_count = 1
                await state.update_data(
                    applied_admin_coupons=True,
                    applied_coupon_codes=applied_coupon_codes,
                    original_price=base_price,
                    discount_amount_coupon=total_coupon_discount,
                    applied_coupons_count=applied_coupons_count,
                    referral_reward_discount=False,
                    used_reward_ids=[],
                    discount_amount_reward=0,
                    applied_rewards_count=0,
                    total_price=final_price
                )
        else:
            await state.update_data(
                referral_reward_discount=False,
                used_reward_ids=[],
                discount_amount_reward=0,
                applied_rewards_count=0,
                applied_admin_coupons=False,
                applied_coupon_codes=[],
                discount_amount_coupon=0,
                applied_coupons_count=0,
                total_price=final_price
            )

    data = await state.get_data()
    
    price_display = f"{final_price} LKR"
    if data.get('original_price') or data.get('referral_reward_discount') or data.get('applied_admin_coupons'):
        discount_amount = data.get('discount_amount', 0) + data.get('discount_amount_reward', 0) + data.get('discount_amount_coupon', 0)
        orig_price = data.get('original_price') or data.get('original_price_reward') or data.get('total_price', 0)
        rewards_count = data.get('applied_rewards_count', 0)
        coupons_count = data.get('applied_coupons_count', 0)
        if discount_amount > 0:
            discount_info = f"-{discount_amount} LKR"
            if rewards_count > 0 or coupons_count > 0:
                parts = []
                if rewards_count > 0:
                    parts.append(f"{rewards_count} reward{'s' if rewards_count > 1 else ''}")
                if coupons_count > 0:
                    parts.append(f"{coupons_count} coupon{'s' if coupons_count > 1 else ''}")
                discount_info += f" ({' + '.join(parts)})"
            price_display = f"~{orig_price} LKR~ → <b>{final_price} LKR</b> ✅ ({discount_info})"
    
    # Use get_custom_text for all texts
    order_summary = (
        f"<b>{get_custom_text(messages, language, 'order_details') or 'Order Summary:'}</b>\n"
        f"• {get_custom_text(messages, language, 'package_info') or 'Package'}: {data.get('package_name')}\n"
        f"• {get_custom_text(messages, language, 'data') or 'Data'}: {gb_text}\n"
        f"• {get_custom_text(messages, language, 'location') or 'Location'}: {location['name']}\n"
        f"• {get_custom_text(messages, language, 'total_price') or 'Total Price'}: {price_display}\n\n"
    )
    payment_text = (
        f"{get_custom_text(messages, language, 'payment_choose_method') or '💳 <b>Choose Payment Method</b>'}\n\n"
        f"{order_summary}"
        f"<b>{get_custom_text(messages, language, 'payment_available_methods') or 'Available Payment Methods:'}</b>"
    )
    # Create payment method buttons
    keyboard_rows = []
    for method in methods:
        btn_text = method.get('name', get_custom_text(messages, language, 'payment_method') or 'Payment Method')
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"pay_method_{method.get('id')}")])
    # Add cancel button
    keyboard_rows.append([InlineKeyboardButton(text=get_custom_text(messages, language, 'order_cancelled') or "❌ Cancel", callback_data="cancel_order")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    await message.edit_text(payment_text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("pay_method_"))
async def cb_payment_method_selected(callback_query: types.CallbackQuery, state: FSMContext):
    """Show payment details for selected method"""
    await callback_query.answer()
    method_id = callback_query.data.replace("pay_method_", "")
    
    payment_details = get_payment_details()
    methods = payment_details.get('methods', [])
    selected_method = next((m for m in methods if m.get('id') == method_id), None)
    
    if not selected_method:
        language = await resolve_user_language(state, callback_query.from_user.id)
        await callback_query.message.edit_text(get_text(language, 'payment_method_not_found'))
        return
    
    await state.update_data(payment_method=method_id)
    
    data = await state.get_data()
    
    # Handle price calculation with referral discount consideration
    # If referral was applied, original_price is set; otherwise use current total_price as base
    if 'original_price' in data:
        base_price_for_fee = data.get('total_price', 0)  # Current price (already discounted)
    else:
        base_price_for_fee = data.get('total_price', 0)
    
    if method_id == 'ezcash':
        # Add 40 LKR fee for eZcash to the current price (whether discounted or not)
        final_price = base_price_for_fee + 40
        await state.update_data(total_price=final_price)
    else:
        # For other methods, price stays as is (no fee)
        # Don't reset to package price if any discount was applied
        has_any_discount = (
            'original_price' in data or
            data.get('applied_referral_code') or
            data.get('referral_reward_discount') or
            data.get('applied_admin_coupons') or
            data.get('discount_amount', 0) > 0 or
            data.get('discount_amount_reward', 0) > 0 or
            data.get('discount_amount_coupon', 0) > 0
        )
        if not has_any_discount:
            # No referral discount, set to package price
            package_id = data.get('package_id')
            packages = get_packages()
            package = next((p for p in packages if p['id'] == package_id), None)
            if package:
                await state.update_data(total_price=package['price'])
    
    # Reload data after price update
    data = await state.get_data()
    language = await resolve_user_language(state, callback_query.from_user.id)
    locations = get_locations()
    location = next((l for l in locations if l['id'] == data.get('location_id')), None)
    gb = data.get('gb', 0)
    currency = get_currency()
    messages = get_messages()
    from languages import get_custom_text
    gb_label = get_custom_text(messages, language, 'gb')
    unlimited_label = get_custom_text(messages, language, 'unlimited')
    gb_text = f"{gb}{gb_label}" if gb > 0 else unlimited_label
    # Build payment details text using get_custom_text
    payment_text = (
        f"{get_custom_text(messages, language, 'payment_details') or '💳 <b>Payment Details</b>'}\n\n"
        f"<b>{get_custom_text(messages, language, 'order_details') or 'Order Summary:'}</b>\n"
        f"• {get_custom_text(messages, language, 'package_info') or 'Package'}: {data.get('package_name')}\n"
        f"• {get_custom_text(messages, language, 'data') or 'Data'}: {gb_text}\n"
        f"• {get_custom_text(messages, language, 'location') or 'Location'}: {location['name'] if location else 'Unknown'}\n"
        f"• {get_custom_text(messages, language, 'total_price') or 'Total Price'}: <b>{currency} {data.get('total_price'):.2f}</b>\n\n"
        f"<b>{get_custom_text(messages, language, 'payment_method') or 'Payment Method'}: {selected_method.get('name')}</b>\n"
    )
    # Add method-specific details
    method_type = selected_method.get('type', selected_method.get('id', '')).split('_')[0]
    if method_type == 'bank' or selected_method.get('id', '').startswith('bank'):
        if selected_method.get('account_name'):
            payment_text += f"{get_custom_text(messages, language, 'account_name') or 'Account Name'}: <b>{selected_method.get('account_name')}</b>\n"
        if selected_method.get('bank_name'):
            payment_text += f"{get_custom_text(messages, language, 'bank_name') or 'Bank'}: <b>{selected_method.get('bank_name')}</b>\n"
        if selected_method.get('account_number'):
            payment_text += f"{get_custom_text(messages, language, 'account_number') or 'Account Number'}: <code>{selected_method.get('account_number')}</code>\n"
    elif method_type == 'ezcash' or selected_method.get('id') == 'ezcash':
        if selected_method.get('mobile_number'):
            payment_text += f"{get_custom_text(messages, language, 'mobile_number') or 'Mobile Number'}: <code>{selected_method.get('mobile_number')}</code>\n"
        payment_text += f"\n<i>{get_custom_text(messages, language, 'ezcash_fee_note') or 'ℹ️ Note: eZcash transactions include a 40 LKR processing fee'}</i>\n"
    elif method_type == 'crypto' or selected_method.get('id', '').startswith('crypto'):
        if selected_method.get('crypto_type'):
            payment_text += f"{get_custom_text(messages, language, 'crypto_type') or 'Crypto Type'}: <b>{selected_method.get('crypto_type')}</b>\n"
        if selected_method.get('crypto_address'):
            payment_text += f"{get_custom_text(messages, language, 'crypto_address') or 'Wallet Address'}: <code>{selected_method.get('crypto_address')}</code>\n"
    payment_text += f"\n{get_custom_text(messages, language, 'upload_receipt_desc') or '⬇️ Upload your payment receipt below 👇'}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'upload_receipt') or "📸 Upload Receipt", callback_data="upload_receipt")],
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'order_cancelled') or "❌ Cancel", callback_data="cancel_order")]
    ])
    await callback_query.message.edit_text(payment_text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(PurchaseFlow.waiting_for_payment_receipt)


@dp.callback_query(F.data == "upload_receipt")
async def cb_upload_receipt(callback_query: types.CallbackQuery, state: FSMContext):
    """Prompt user to upload receipt"""
    await callback_query.answer()
    language = await resolve_user_language(state, callback_query.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    await callback_query.message.edit_text(
        get_custom_text(messages, language, 'enter_client_name_prompt') or
        "👤 <b>Please enter your name</b>\n\n"
        "We will use this name (plus 4 random digits) to create your client in the panel.\n\n"
        "Send your name now:",
        parse_mode="HTML"
    )
    await state.set_state(PurchaseFlow.waiting_for_client_name)


# New state for client name
@dp.message(PurchaseFlow.waiting_for_client_name)
async def process_client_name(message: types.Message, state: FSMContext):
    """Ask for name, then prompt for receipt upload"""
    if not message.text or not message.text.strip():
        language = await resolve_user_language(state, message.from_user.id)
        await message.answer(get_text(language, 'valid_name_required'))
        return
    name = message.text.strip()
    await state.update_data(client_name=name)

    data = await state.get_data()
    if data.get('admin_direct_create'):
        await create_admin_direct_account(message, state)
        return

    language = await resolve_user_language(state, message.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    await message.answer(
        get_custom_text(messages, language, 'upload_receipt_full_prompt') or
        "📸 <b>Upload Payment Receipt</b>\n\n"
        "Please send a screenshot or photo of your payment receipt.\n"
        "Make sure it clearly shows:\n"
        "• Transaction ID or confirmation number\n"
        "• Amount paid\n"
        "• Date and time\n\n"
        "You can send as photo or PDF/image document.",
        parse_mode="HTML"
    )
    await state.set_state(PurchaseFlow.waiting_for_payment_receipt)


@dp.message(PurchaseFlow.waiting_for_payment_receipt)
async def process_payment_receipt(message: types.Message, state: FSMContext):
    """Process uploaded payment receipt and show Add Note / Send Now buttons"""
    if not message.photo and not message.document:
        language = await resolve_user_language(state, message.from_user.id)
        await message.answer(get_text(language, 'receipt_photo_or_document_required'))
        return
    if message.document:
        allowed_mime_types = {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/heic",
            "image/heif"
        }
        mime_type = (message.document.mime_type or '').lower()
        if mime_type not in allowed_mime_types:
            language = await resolve_user_language(state, message.from_user.id)
            await message.answer(get_text(language, 'receipt_unsupported_format'))
            return
    
    # Save receipt info to state
    receipt_file_id = None
    receipt_type = None
    receipt_mime_type = None
    receipt_file_name = None
    if message.photo:
        receipt_file_id = message.photo[-1].file_id
        receipt_type = "photo"
        receipt_mime_type = "image/jpeg"
    elif message.document:
        receipt_file_id = message.document.file_id
        receipt_type = "document"
        receipt_mime_type = message.document.mime_type
        receipt_file_name = message.document.file_name
    
    await state.update_data(
        receipt_file_id=receipt_file_id,
        receipt_type=receipt_type,
        receipt_mime_type=receipt_mime_type,
        receipt_file_name=receipt_file_name
    )
    
    # Get language and messages
    language = await resolve_user_language(state, message.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    # Show buttons for Add Note or Send Now
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'add_note'), callback_data="add_order_note")],
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'send_now'), callback_data="send_order_now")]
    ])
    
    receipt_msg = (
        f"{get_custom_text(messages, language, 'receipt_received')}\n\n"
        f"{get_custom_text(messages, language, 'receipt_note_question')}"
    )
    
    await message.answer(
        receipt_msg,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "add_order_note")
async def cb_add_order_note(callback_query: types.CallbackQuery, state: FSMContext):
    """User wants to add a note - ask for it"""
    await callback_query.answer()
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    note_prompt = (
        f"<b>{get_custom_text(messages, language, 'add_note_prompt')}</b>\n\n"
        f"{get_custom_text(messages, language, 'add_note_desc')}"
    )
    
    await callback_query.message.edit_text(
        note_prompt,
        parse_mode="HTML"
    )
    await state.set_state(PurchaseFlow.waiting_for_order_note)


@dp.message(PurchaseFlow.waiting_for_order_note)
async def process_order_note_text(message: types.Message, state: FSMContext):
    """Receive note text and finalize order"""
    note_text = (message.text or '').strip()
    await state.update_data(user_note=note_text)
    
    language = await resolve_user_language(state, message.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    await message.answer(get_custom_text(messages, language, 'note_added'))
    await finalize_order(message, state)


@dp.callback_query(F.data == "send_order_now")
async def cb_send_order_now(callback_query: types.CallbackQuery, state: FSMContext):
    """User chose to send order without note"""
    await callback_query.answer()
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    await callback_query.message.edit_text(get_custom_text(messages, language, 'sending_order'))
    # Use callback message's chat as message context
    await finalize_order(callback_query.message, state, from_callback=True)


async def finalize_order(message: types.Message, state: FSMContext, from_callback: bool = False):
    """Create and submit the order to admin"""
    data = await state.get_data()
    user_id = message.chat.id if from_callback else message.from_user.id
    username = message.chat.username if from_callback else message.from_user.username
    language = await resolve_user_language(state, user_id)
    order_id = f"ORD_{user_id}_{int(datetime.now().timestamp())}"
    
    # Generate client name for panel
    import random
    rand_digits = str(random.randint(1000, 9999))
    panel_client_name = f"{data.get('client_name', 'User')}_{rand_digits}"
    user_note = (data.get('user_note') or '').strip()
    
    # Create order entry
    order = {
        "order_id": order_id,
        "user_id": user_id,
        "username": username or "No username",
        "language": language,  # Store user's language preference
        "client_name": panel_client_name,
        "isp_id": data.get('isp_id'),
        "isp_name": data.get('isp_name'),
        "user_package": data.get('user_package'),
        "user_package_id": data.get('user_package_id', ''),
        "user_package_sni": data.get('user_package_sni', ''),
        "user_package_address": data.get('user_package_address', ''),
        "user_package_port": data.get('user_package_port', 443),
        "user_package_use_location_sni": data.get('user_package_use_location_sni', False),
        "package_id": data.get('package_id'),
        "package_name": data.get('package_name'),
        "gb": data.get('gb'),
        "days": data.get('days') or 30,
        "is_custom_package": data.get('is_custom_package', False),
        "location_id": data.get('location_id'),
        "total_price": data.get('total_price'),
        "user_note": user_note,
        "receipt_file_id": data.get('receipt_file_id'),
        "receipt_type": data.get('receipt_type'),
        "receipt_mime_type": data.get('receipt_mime_type'),
        "receipt_file_name": data.get('receipt_file_name'),
        "applied_referral_code": data.get('applied_referral_code'),
        "original_price": data.get('original_price'),
        "discount_amount": data.get('discount_amount'),
        "referrer_id": data.get('referrer_id'),
        "was_referred_as_new_user": data.get('was_referred_as_new_user', False),
        "referral_reward_applied": data.get('referral_reward_discount', False),
        "reward_discount_amount": data.get('discount_amount_reward', 0),
        "used_reward_ids": data.get('used_reward_ids', []),
        "applied_rewards_count": data.get('applied_rewards_count', 0),
        "applied_admin_coupons": data.get('applied_admin_coupons', False),
        "applied_coupon_codes": data.get('applied_coupon_codes', []),
        "coupon_discount_amount": data.get('discount_amount_coupon', 0),
        "receipt_verification_status": "unverified",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "approved_at": None,
        "approved_by": None
    }
    # Save to config
    config = load_config()
    config['pending_approvals'].append(order)
    
    # Mark ALL used rewards as used if applicable
    if data.get('used_reward_ids'):
        referral_rewards = config.get('referral_rewards', {})
        if str(user_id) in referral_rewards and isinstance(referral_rewards[str(user_id)], list):
            for reward in referral_rewards[str(user_id)]:
                if reward.get('reward_id') in data.get('used_reward_ids'):
                    reward['used'] = True
                    reward['used_at'] = datetime.now().isoformat()
                    reward['used_on_order_id'] = order_id
            config['referral_rewards'] = referral_rewards

    # Consume auto-applied admin coupons so they are one-time
    used_coupon_codes = data.get('applied_coupon_codes', [])
    if used_coupon_codes:
        claimed_admin_coupons = config.get('claimed_admin_coupons', {})
        if str(user_id) in claimed_admin_coupons and isinstance(claimed_admin_coupons[str(user_id)], list):
            claimed_admin_coupons[str(user_id)] = [
                coupon for coupon in claimed_admin_coupons[str(user_id)]
                if coupon.get('code') not in used_coupon_codes
            ]
            config['claimed_admin_coupons'] = claimed_admin_coupons
    
    save_config(config)
    
    # Confirmation message
    locations = get_locations()
    currency = get_currency()
    location = next((l for l in locations if l['id'] == data.get('location_id')), None)
    gb = data.get('gb', 0)
    messages = get_messages()
    from languages import get_custom_text
    gb_label = get_custom_text(messages, language, 'gb')
    unlimited_label = get_custom_text(messages, language, 'unlimited')
    gb_text = f"{gb}{gb_label}" if gb > 0 else unlimited_label
    
    confirmation_text = (
        f"✅ <b>Order Received!</b>\n\n"
        f"Order ID: <code>{order_id}</code>\n"
        f"ISP: {data.get('isp_name')}\n"
        f"Using: {data.get('user_package')}\n"
        f"Package: {data.get('package_name')}\n"
        f"Data: {gb_text}\n"
        f"Location: {location['name']}\n"
        f"Total: {currency} {data.get('total_price'):.2f}\n\n"
        f"💬 Your payment receipt has been received and is now awaiting admin approval.\n"
        f"Once approved, your V2Ray account will be created and sent to you automatically.\n\n"
        f"Thank you for your purchase! ❤️"
    )
    
    if from_callback:
        await message.answer(confirmation_text, parse_mode="HTML")
    else:
        await message.answer(confirmation_text, parse_mode="HTML")
    await state.clear()
    
    # Notify admins
    for admin_id in get_admin_ids():
        try:
            safe_note = escape(user_note) if user_note else ""
            note_section = ""
            if user_note:
                note_section = f"\n\n💬 <b>USER NOTE:</b>\n<i>{safe_note}</i>\n"
            
            # Add referral information if applicable
            referral_section = ""
            if data.get('applied_referral_code'):
                discount_amt = data.get('discount_amount', 0)
                original_price = data.get('original_price', 0)
                referral_section = (
                    f"\n\n🎁 <b>REFERRAL DISCOUNT APPLIED:</b>\n"
                    f"Code: <code>{data.get('applied_referral_code')}</code>\n"
                    f"Original: {currency} {original_price:.2f}\n"
                    f"Discount: -{currency} {discount_amt:.2f}\n"
                )
            
            # Add referral reward if used
            if data.get('referral_reward_discount'):
                reward_amt = data.get('discount_amount_reward', 0)
                rewards_count = data.get('applied_rewards_count', 1)
                referral_section += (
                    f"\n\n🏆 <b>REFERRAL REWARDS AUTO-APPLIED:</b>\n"
                    f"Number of rewards: {rewards_count}\n"
                    f"Total discount: -{currency} {reward_amt:.2f}\n"
                )
            
            admin_msg = (
                f"🔔 <b>New Order Pending Approval</b>\n\n"
                f"Order ID: <code>{order_id}</code>\n"
                f"User: @{username or user_id}\n"
                f"ISP: {data.get('isp_name')}\n"
                f"Using: {data.get('user_package')}\n"
                f"Package: {data.get('package_name')}\n"
                f"GB: {data.get('gb')}\n"
                f"Total: {currency} {data.get('total_price'):.2f}"
                f"{referral_section}"
                f"{note_section}"
                f"\nClick button below to review:"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ View Order", callback_data=f"view_order_{order_id}")]
            ])
            await bot.send_message(admin_id, admin_msg, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


@dp.callback_query(F.data == "cancel_order")
async def cb_cancel_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Cancel purchase"""
    await callback_query.answer()
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    
    # Clear purchase flow data but preserve language
    await state.clear()
    await state.update_data(language=language)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(language, 'buy_account'), callback_data="buy_v2ray")],
    ])
    
    cancel_text = get_text(language, 'order_cancelled')
    start_over_text = get_text(language, 'start_over')
    
    await callback_query.message.edit_text(
        f"{cancel_text}\n\n{start_over_text}",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("view_order_"))
async def cb_view_order(callback_query: types.CallbackQuery, state: FSMContext):
    """View pending order for admin"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    order_id = callback_query.data.replace("view_order_", "")
    config = load_config()
    order = next((o for o in config['pending_approvals'] if o['order_id'] == order_id), None)
    
    if not order:
        await callback_query.answer("❌ Order not found", show_alert=True)
        return
    
    currency = get_currency()
    user_note = (order.get('user_note') or '').strip()
    safe_note = escape(user_note) if user_note else ""
    note_section = ""
    if user_note:
        note_section = f"\n\n💬 <b>USER NOTE:</b>\n<i>{safe_note}</i>\n"
    
    order_text = (
        f"📋 <b>Order Details</b>\n\n"
        f"Order ID: <code>{order['order_id']}</code>\n"
        f"Status: {order['status']}\n"
        f"User: @{order['username']}\n"
        f"ISP: {order.get('isp_name', 'N/A')}\n"
        f"Using: {order.get('user_package', 'N/A')}\n"
        f"Package: {order['package_name']}\n"
        f"GB: {order['gb']}\n"
        f"Location: {order['location_id']}\n"
        f"Total: {currency} {order['total_price']:.2f}\n"
        f"Created: {order['created_at']}"
        f"{note_section}"
    )
    
    # If order is already approved or rejected, show info and disable buttons
    if order['status'] == 'approved':
        approver = order.get('approved_by', None)
        approved_at = order.get('approved_at', None)
        approved_msg = f"✅ <b>This order has already been approved.</b>"
        if approver:
            approved_msg += f"\nApproved by admin ID: <code>{approver}</code>"
        if approved_at:
            approved_msg += f"\nAt: {approved_at}"
        await callback_query.message.edit_text(
            order_text + '\n\n' + approved_msg,
            parse_mode="HTML"
        )
    elif order['status'] == 'rejected':
        await callback_query.message.edit_text(
            order_text + '\n\n❌ <b>This order has already been rejected.</b>',
            parse_mode="HTML"
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{order_id}")],
            [InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order_id}")]
        ])
        await callback_query.message.edit_text(order_text, parse_mode="HTML", reply_markup=keyboard)
    # Send receipt based on original media type
    receipt_file_id = order.get('receipt_file_id')
    if receipt_file_id:
        try:
            receipt_type = order.get('receipt_type')
            if receipt_type == 'document':
                await callback_query.message.answer_document(
                    receipt_file_id,
                    caption="💳 Payment Receipt"
                )
            elif receipt_type == 'photo':
                await callback_query.message.answer_photo(
                    receipt_file_id,
                    caption="💳 Payment Receipt"
                )
            else:
                try:
                    await callback_query.message.answer_photo(
                        receipt_file_id,
                        caption="💳 Payment Receipt"
                    )
                except Exception:
                    await callback_query.message.answer_document(
                        receipt_file_id,
                        caption="💳 Payment Receipt"
                    )
        except Exception as e:
            logger.error(f"Failed to send receipt: {e}")


@dp.callback_query(F.data.startswith("approve_"))
async def cb_approve_order(callback_query: types.CallbackQuery):
    """Approve order and create V2Ray account"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    order_id = callback_query.data.replace("approve_", "")
    config = load_config()
    order = next((o for o in config['pending_approvals'] if o['order_id'] == order_id), None)
    
    if not order:
        await callback_query.answer("❌ Order not found", show_alert=True)
        return
    # Prevent duplicate approval and V2Ray account creation
    if order['status'] == 'approved':
        await callback_query.answer("✅ This order has already been approved.", show_alert=True)
        return
    if order['status'] == 'rejected':
        await callback_query.answer("❌ This order has already been rejected.", show_alert=True)
        return
    await callback_query.message.edit_text("⏳ Creating V2Ray account...")
    
    # Read fresh package data from config to get latest SNI and address
    isp_providers = get_isp_providers()
    isp = next((p for p in isp_providers if p['id'] == order['isp_id']), None)
    package_data = None
    if isp and 'user_package_id' in order:
        user_pkg_id = order.get('user_package_id', '')
        package_data = next((p for p in isp.get('packages', []) if p['id'] == user_pkg_id), None)
        logger.info(f"Fresh config lookup - ISP: {order['isp_id']}, Package ID: {user_pkg_id}, Found: {package_data is not None}")
    
    # Use fresh package data if available, otherwise fall back to order data
    if package_data:
        user_sni = package_data.get('sni', '')
        user_address = package_data.get('address', '')
        user_port = package_data.get('port', order.get('user_package_port', 443))
        use_location_sni = package_data.get('use_location_sni', False)
        logger.info(f"Using fresh config - SNI: {user_sni}, Address: {user_address}, Port: {user_port}, use_location_sni: {use_location_sni}")
    else:
        user_sni = order.get('user_package_sni', '')
        user_address = order.get('user_package_address', '')
        user_port = order.get('user_package_port', 443)
        use_location_sni = order.get('user_package_use_location_sni', False)
        logger.info(f"Using order data - SNI: {user_sni}, Address: {user_address}, Port: {user_port}, use_location_sni: {use_location_sni}")
    
    # Create V2Ray account with telegram username, SNI, address, and port
    telegram_username = order['username'].replace('@', '')
    account_info = await create_v2ray_account(
        order['package_id'],
        order['gb'],
        order['location_id'],
        telegram_username,
        order['user_id'],
        user_sni,
        user_port,
        use_location_sni,
        user_address,
        order.get('client_name'),
        order.get('days', 30)
    )
    
    if account_info:
        # Update order status
        order['status'] = 'approved'
        order['approved_at'] = datetime.now().isoformat()
        order['approved_by'] = callback_query.from_user.id
        order['v2ray_config'] = account_info
        # Reload and save to avoid overwriting changes
        config = load_config()
        for o in config['pending_approvals']:
            if o['order_id'] == order_id:
                o['status'] = 'approved'
                o['approved_at'] = order['approved_at']
                o['approved_by'] = order['approved_by']
                o['v2ray_config'] = account_info
                break
        save_config(config)
        
        # Build account-ready message using user's language
        config_data = load_config()
        user_language = order.get('language', 'en')
        account_msg = build_account_message(order, account_info, config_data, user_language)
        
        try:
            target_user_id = resolve_target_user_id(order=order)
            if target_user_id is None:
                logger.error(f"Cannot approve order {order_id}: missing user_id/telegram_id")
                await callback_query.message.edit_text(
                    f"❌ Cannot send account: order {order_id} has no valid Telegram user id."
                )
                return

            # --- Premium Channel Invite Link Logic ---
            invite_button = await build_premium_invite_button(target_user_id, config_data)
            # --- Handler to revoke invite link when user joins premium channel ---
            @dp.chat_member()
            async def on_chat_member_update(event: types.ChatMemberUpdated):
                # Only care about joins to the premium channel
                user_id = event.new_chat_member.user.id if event.new_chat_member and event.new_chat_member.user else None
                channel_id = event.chat.id
                if not user_id or user_id not in invite_links_map:
                    return
                invite_info = invite_links_map[user_id]
                if channel_id != invite_info["channel_id"]:
                    return
                # Only act if user just became a member
                if event.old_chat_member.status in ("left", "kicked") and event.new_chat_member.status == "member":
                    try:
                        # Revoke the invite link
                        await bot.revoke_chat_invite_link(chat_id=channel_id, invite_link=invite_info["invite_link"])
                        logger.info(f"Revoked invite link for user {user_id} in channel {channel_id}")
                        # Optionally notify user
                        try:
                            await bot.send_message(user_id, "✅ You have joined the premium channel. Your invite link is now revoked for security.")
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Failed to revoke invite link for user {user_id}: {e}")
                    # Remove from tracking
                    invite_links_map.pop(user_id, None)
            # Send config message. Only include invite button if user is NOT already a member
            if invite_button:
                await bot.send_message(
                    target_user_id,
                    account_msg,
                    parse_mode="HTML",
                    reply_markup=invite_button
                )
            else:
                await bot.send_message(
                    target_user_id,
                    account_msg,
                    parse_mode="HTML"
                )
            await send_account_ready_to_channel(order, account_msg, config_data)
            await send_panel_backup_to_channel(order, account_info, config_data)
            await callback_query.message.edit_text(
                f"✅ Order {order_id} approved!\n\n"
                f"📧 Username: {account_info['email']}\n"
                f"🔌 Port: {account_info['port']}\n"
                f"📡 Protocol: {account_info['protocol']}\n\n"
                f"Account details sent to user @{order['username']}"
            )
        except Exception as e:
            logger.error(f"Failed to send account to user {order['user_id']}: {e}")
            await callback_query.message.edit_text(f"⚠️ Account created but failed to send to user: {e}")
    else:
        # Show error message with retry button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Retry", callback_data=f"retry_{order_id}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_{order_id}")]
        ])
        logger.error(f"Failed to create V2Ray account for order {order_id}")
        await callback_query.message.edit_text(
            f"❌ Failed to create V2Ray account. Please check:\n"
            f"• Panel login credentials\n"
            f"• Inbound on port 443 exists\n"
            f"• Network connectivity to panel\n"
            f"• Data limits and expiry settings\n\n"
            f"You can retry or cancel this order.",
            reply_markup=keyboard
        )


@dp.callback_query(F.data.startswith("retry_"))
async def cb_retry_order(callback_query: types.CallbackQuery):
    """Retry creating V2Ray account"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    await callback_query.answer()
    order_id = callback_query.data.replace("retry_", "")
    
    # Find the order
    config = load_config()
    order = next((o for o in config['pending_approvals'] if o['order_id'] == order_id), None)
    
    if not order:
        await callback_query.message.edit_text("❌ Order not found")
        return
    
    # Retry creating the account (same logic as approve)
    await callback_query.message.edit_text("⏳ Retrying to create V2Ray account...")
    
    # Read fresh package data from config to get latest SNI and address
    isp_providers = get_isp_providers()
    isp = next((p for p in isp_providers if p['id'] == order['isp_id']), None)
    package_data = None
    if isp and 'user_package_id' in order:
        user_pkg_id = order.get('user_package_id', '')
        package_data = next((p for p in isp.get('packages', []) if p['id'] == user_pkg_id), None)
        logger.info(f"Retry fresh config lookup - ISP: {order['isp_id']}, Package ID: {user_pkg_id}, Found: {package_data is not None}")
    
    # Use fresh package data if available, otherwise fall back to order data
    if package_data:
        user_sni = package_data.get('sni', '')
        user_address = package_data.get('address', '')
        user_port = package_data.get('port', order.get('user_package_port', 443))
        use_location_sni = package_data.get('use_location_sni', False)
        logger.info(f"Retry using fresh config - SNI: {user_sni}, Address: {user_address}, Port: {user_port}, use_location_sni: {use_location_sni}")
    else:
        user_sni = order.get('user_package_sni', '')
        user_address = order.get('user_package_address', '')
        user_port = order.get('user_package_port', 443)
        use_location_sni = order.get('user_package_use_location_sni', False)
        logger.info(f"Retry using order data - SNI: {user_sni}, Address: {user_address}, Port: {user_port}, use_location_sni: {use_location_sni}")
    
    # Create V2Ray account with telegram username, SNI, address, and port
    telegram_username = order['username'].replace('@', '')
    account_info = await create_v2ray_account(
        order['package_id'],
        order['gb'],
        order['location_id'],
        telegram_username,
        order['user_id'],
        user_sni,
        user_port,
        use_location_sni,
        user_address,
        order.get('client_name'),
        order.get('days') or 30
    )
    
    if account_info:
        # Update order status
        order['status'] = 'approved'
        order['approved_at'] = datetime.now().isoformat()
        order['approved_by'] = callback_query.from_user.id
        order['v2ray_config'] = account_info
        # Reload and save to avoid overwriting changes
        config = load_config()
        for o in config['pending_approvals']:
            if o['order_id'] == order_id:
                o['status'] = order['status']
                o['approved_at'] = order['approved_at']
                o['approved_by'] = order['approved_by']
                o['v2ray_config'] = account_info
                break
        save_config(config)
        
        # Build account-ready message using user's language
        config_data = load_config()
        user_language = order.get('language', 'en')
        account_msg = build_account_message(order, account_info, config_data, user_language)
        
        try:
            target_user_id = resolve_target_user_id(order=order)
            if target_user_id is None:
                logger.error(f"Cannot retry order {order_id}: missing user_id/telegram_id")
                await callback_query.message.edit_text(
                    f"❌ Cannot send account: order {order_id} has no valid Telegram user id."
                )
                return

            invite_button = await build_premium_invite_button(target_user_id, config_data)
            if invite_button:
                await bot.send_message(target_user_id, account_msg, parse_mode="HTML", reply_markup=invite_button)
            else:
                await bot.send_message(target_user_id, account_msg, parse_mode="HTML")
            await send_account_ready_to_channel(order, account_msg, config_data)
            await send_panel_backup_to_channel(order, account_info, config_data)
            await callback_query.message.edit_text(
                f"✅ Order {order_id} approved!\n\n"
                f"📧 Username: {account_info['email']}\n"
                f"🔌 Port: {account_info['port']}\n"
                f"📡 Protocol: {account_info['protocol']}\n\n"
                f"Account details sent to user @{order['username']}"
            )
        except Exception as e:
            logger.error(f"Failed to send account to user {order['user_id']}: {e}")
            await callback_query.message.edit_text(f"⚠️ Account created but failed to send to user: {e}")
    else:
        # Show error message with retry button again
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Retry", callback_data=f"retry_{order_id}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_{order_id}")]
        ])
        logger.error(f"Retry failed for order {order_id}")
        await callback_query.message.edit_text(
            f"❌ Still failing to create V2Ray account. Please check:\n"
            f"• Panel login credentials\n"
            f"• Inbound on port 443 exists\n"
            f"• Network connectivity to panel\n"
            f"• Data limits and expiry settings\n\n"
            f"Try again or cancel this order.",
            reply_markup=keyboard
        )


@dp.callback_query(F.data.startswith("cancel_"))
async def cb_cancel_order(callback_query: types.CallbackQuery):
    """Cancel order after failed retry"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    await callback_query.answer()
    order_id = callback_query.data.replace("cancel_", "")
    
    # Find and remove the order
    config = load_config()
    order = next((o for o in config['pending_approvals'] if o['order_id'] == order_id), None)
    
    if order:
        config['pending_approvals'].remove(order)
        save_config(config)
        await callback_query.message.edit_text(f"❌ Order {order_id} has been cancelled and removed from pending approvals.")
    else:
        await callback_query.message.edit_text("❌ Order not found")


@dp.callback_query(F.data.startswith("reject_"))
async def cb_reject_order(callback_query: types.CallbackQuery):
    """Reject order"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    order_id = callback_query.data.replace("reject_", "")
    config = load_config()
    order = next((o for o in config['pending_approvals'] if o['order_id'] == order_id), None)
    
    if not order:
        await callback_query.answer("❌ Order not found", show_alert=True)
        return
    
    # Update order status
    order['status'] = 'rejected'
    save_config(config)
    
    # Notify user with retry button
    try:
        user_language = order.get('language', 'en')
        messages = get_messages()
        from languages import get_custom_text
        
        # Build retry keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_custom_text(messages, user_language, 'retry') or "🔄 Retry", callback_data=f"retry_order_{order_id}")],
            [InlineKeyboardButton(text=get_custom_text(messages, user_language, 'contact_support') or "📞 Contact Support", url="https://t.me/support")]
        ])
        
        rejection_message = (
            f"❌ Your order {order['order_id']} has been rejected.\n\n"
            f"<b>{get_custom_text(messages, user_language, 'rejection_reason') or 'Possible reasons'}</b>:\n"
            f"• {get_custom_text(messages, user_language, 'invalid_receipt') or 'Invalid or unclear payment receipt'}\n"
            f"• {get_custom_text(messages, user_language, 'insufficient_payment') or 'Insufficient payment amount'}\n"
            f"• {get_custom_text(messages, user_language, 'unclear_details') or 'Unclear transaction details'}\n\n"
            f"{get_custom_text(messages, user_language, 'retry_instructions') or 'Please review and try again with a clearer receipt or additional details.'}"
        )
        
        await bot.send_message(
            order['user_id'],
            rejection_message,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")
    
    await callback_query.message.edit_text(
        f"✅ Order {order_id} rejected and user notified with retry option."
    )


@dp.callback_query(F.data.startswith("retry_order_"))
async def cb_retry_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle retry button - restore order data and ask for new receipt"""
    await callback_query.answer()
    
    order_id = callback_query.data.replace("retry_order_", "")
    config = load_config()
    order = next((o for o in config['pending_approvals'] if o['order_id'] == order_id), None)
    
    if not order:
        await callback_query.message.edit_text("❌ Original order not found.")
        return
    
    user_language = order.get('language', 'en')
    messages = get_messages()
    from languages import get_custom_text
    
    # Restore all order data to state for retry
    await state.update_data(
        language=user_language,
        isp_id=order.get('isp_id'),
        isp_name=order.get('isp_name'),
        user_package=order.get('user_package'),
        user_package_id=order.get('user_package_id'),
        user_package_sni=order.get('user_package_sni', ''),
        user_package_address=order.get('user_package_address', ''),
        user_package_port=order.get('user_package_port', 443),
        user_package_use_location_sni=order.get('user_package_use_location_sni', False),
        package_id=order.get('package_id'),
        package_name=order.get('package_name'),
        gb=order.get('gb'),
        days=order.get('days') or 30,
        location_id=order.get('location_id'),
        total_price=order.get('total_price'),
        client_name=order.get('client_name'),
        original_order_id=order_id,  # Store to track retry
        is_retry=True
    )
    
    await state.set_state(PurchaseFlow.waiting_for_retry_payment_receipt)
    
    retry_message = (
        f"<b>{get_custom_text(messages, user_language, 'retry_new_receipt') or 'Upload New Payment Receipt'}</b>\n\n"
        f"{get_custom_text(messages, user_language, 'retry_instructions_detail') or 'Please upload a clear photo or document of your payment receipt. Make sure all details are visible.'}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, user_language, 'cancel') or "❌ Cancel", callback_data="back_to_main")]
    ])
    
    await callback_query.message.edit_text(
        retry_message,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.message(PurchaseFlow.waiting_for_retry_payment_receipt)
async def process_retry_payment_receipt(message: types.Message, state: FSMContext):
    """Process retry payment receipt"""
    if not message.photo and not message.document:
        language = await resolve_user_language(state, message.from_user.id)
        await message.answer(get_text(language, 'receipt_photo_or_document_required'))
        return
    
    if message.document:
        allowed_mime_types = {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/heic",
            "image/heif"
        }
        mime_type = (message.document.mime_type or '').lower()
        if mime_type not in allowed_mime_types:
            language = await resolve_user_language(state, message.from_user.id)
            await message.answer(get_text(language, 'receipt_unsupported_format'))
            return
    
    # Save receipt info to state
    receipt_file_id = None
    receipt_type = None
    receipt_mime_type = None
    receipt_file_name = None
    
    if message.photo:
        receipt_file_id = message.photo[-1].file_id
        receipt_type = "photo"
        receipt_mime_type = "image/jpeg"
    elif message.document:
        receipt_file_id = message.document.file_id
        receipt_type = "document"
        receipt_mime_type = message.document.mime_type
        receipt_file_name = message.document.file_name
    
    await state.update_data(
        receipt_file_id=receipt_file_id,
        receipt_type=receipt_type,
        receipt_mime_type=receipt_mime_type,
        receipt_file_name=receipt_file_name
    )
    
    # Get language and messages
    language = await resolve_user_language(state, message.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    # Show buttons for Add Note or Send Now
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'add_note'), callback_data="add_retry_note")],
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'send_now'), callback_data="send_retry_order_now")]
    ])
    
    receipt_msg = (
        f"{get_custom_text(messages, language, 'receipt_received')}\n\n"
        f"{get_custom_text(messages, language, 'receipt_note_question') or 'Would you like to add a note? (Optional)'}"
    )
    
    await message.answer(
        receipt_msg,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "add_retry_note")
async def cb_add_retry_note(callback_query: types.CallbackQuery, state: FSMContext):
    """User wants to add a note for retry"""
    await callback_query.answer()
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    note_prompt = (
        f"<b>{get_custom_text(messages, language, 'add_note_prompt') or 'Add a Note'}</b>\n\n"
        f"{get_custom_text(messages, language, 'add_note_desc') or 'You can provide additional information here (e.g., transaction ID, payment method details, etc.)'}"
    )
    
    await state.set_state(PurchaseFlow.waiting_for_retry_order_note)
    await callback_query.message.edit_text(note_prompt, parse_mode="HTML")


@dp.message(PurchaseFlow.waiting_for_retry_order_note)
async def process_retry_order_note(message: types.Message, state: FSMContext):
    """Receive retry note and finalize retry order"""
    note_text = (message.text or '').strip()
    await state.update_data(user_note=note_text)
    
    language = await resolve_user_language(state, message.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    # Show confirm and send buttons
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, language, 'send_now'), callback_data="send_retry_order_now")]
    ])
    
    confirm_msg = (
        f"{get_custom_text(messages, language, 'note_saved')}\n\n"
        f"<b>{get_custom_text(messages, language, 'your_note') or 'Your note'}</b>:\n"
        f"<i>{note_text if note_text else '(No note provided)'}</i>"
    )
    
    await message.answer(confirm_msg, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "send_retry_order_now")
async def cb_send_retry_order_now(callback_query: types.CallbackQuery, state: FSMContext):
    """User chose to send retry order"""
    await callback_query.answer()
    
    language = await resolve_user_language(state, callback_query.from_user.id)
    messages = get_messages()
    from languages import get_custom_text
    
    await callback_query.message.edit_text(get_custom_text(messages, language, 'sending_order'))
    await finalize_retry_order(callback_query.message, state, from_callback=True)


async def finalize_retry_order(message: types.Message, state: FSMContext, from_callback: bool = False):
    """Create and submit retry order to admin"""
    data = await state.get_data()
    user_id = message.chat.id if from_callback else message.from_user.id
    username = message.chat.username if from_callback else message.from_user.username
    original_order_id = data.get('original_order_id')
    language = await resolve_user_language(state, user_id)
    messages = get_messages()
    from languages import get_custom_text
    
    # Create new order for retry (with reference to original)
    import random
    rand_digits = str(random.randint(1000, 9999))
    panel_client_name = f"{data.get('client_name', 'User')}_{rand_digits}"
    user_note = (data.get('user_note') or '').strip()
    
    # Create new order entry (retry)
    order = {
        "order_id": f"ORD_{user_id}_{int(datetime.now().timestamp())}",
        "retry_of_order": original_order_id,  # Reference to original rejected order
        "user_id": user_id,
        "username": username or "No username",
        "language": language,
        "client_name": panel_client_name,
        "isp_id": data.get('isp_id'),
        "isp_name": data.get('isp_name'),
        "user_package": data.get('user_package'),
        "user_package_id": data.get('user_package_id', ''),
        "user_package_sni": data.get('user_package_sni', ''),
        "user_package_address": data.get('user_package_address', ''),
        "user_package_port": data.get('user_package_port', 443),
        "user_package_use_location_sni": data.get('user_package_use_location_sni', False),
        "package_id": data.get('package_id'),
        "package_name": data.get('package_name'),
        "gb": data.get('gb'),
        "days": data.get('days') or 30,
        "location_id": data.get('location_id'),
        "total_price": data.get('total_price'),
        "user_note": user_note,
        "receipt_file_id": data.get('receipt_file_id'),
        "receipt_type": data.get('receipt_type'),
        "receipt_mime_type": data.get('receipt_mime_type'),
        "receipt_file_name": data.get('receipt_file_name'),
        "receipt_verification_status": "unverified",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "approved_at": None,
        "approved_by": None
    }
    
    # Get admin IDs for notification
    admin_ids = get_admin_ids()
    
    # Save order to config
    config = load_config()
    if 'pending_approvals' not in config:
        config['pending_approvals'] = []
    
    config['pending_approvals'].append(order)
    save_config(config)
    
    # Get location name
    location_id = data.get('location_id')
    locations = get_locations()
    location_name = next((loc['name'] for loc in locations if loc['id'] == location_id), "Unknown")
    
    # Notify admins of new retry order
    admin_msg = (
        f"🔄 <b>RETRY ORDER FROM USER</b>\n"
        f"🔗 Retrying order: {original_order_id}\n\n"
        f"<b>Order Details:</b>\n"
        f"Order ID: <code>{order['order_id']}</code>\n"
        f"User: @{order['username']} (ID: {user_id})\n"
        f"ISP: {order['isp_name']}\n"
        f"Package: {order['package_name']}\n"
        f"Data: {order['gb']} GB\n"
        f"Location: {location_name}\n"
        f"Price: ${order['total_price']:.2f}\n\n"
    )
    
    if user_note:
        admin_msg += f"<b>User Note:</b>\n{user_note}\n\n"
    
    admin_msg += f"<b>Instructions:</b>\nPlease review the new receipt and details carefully.\n\n"
    
    from languages import get_custom_text
    
    # Add approval/rejection buttons
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_custom_text(messages, 'en', 'approve') or "✅ Approve", callback_data=f"approve_{order['order_id']}")],
        [InlineKeyboardButton(text=get_custom_text(messages, 'en', 'reject') or "❌ Reject", callback_data=f"reject_{order['order_id']}")]
    ])
    
    for admin_id in admin_ids:
        try:
            # Attempt to send receipt as media if available
            receipt_file_id = data.get('receipt_file_id')
            receipt_type = data.get('receipt_type')
            
            if receipt_file_id and receipt_type:
                if receipt_type == 'photo':
                    await bot.send_photo(
                        admin_id,
                        receipt_file_id,
                        caption=admin_msg,
                        parse_mode="HTML",
                        reply_markup=admin_keyboard
                    )
                elif receipt_type == 'document':
                    await bot.send_document(
                        admin_id,
                        receipt_file_id,
                        caption=admin_msg,
                        parse_mode="HTML",
                        reply_markup=admin_keyboard
                    )
            else:
                await bot.send_message(
                    admin_id,
                    admin_msg,
                    parse_mode="HTML",
                    reply_markup=admin_keyboard
                )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    # Clear state and show success message
    await state.clear()
    
    success_msg = (
        f"{get_custom_text(messages, language, 'order_submitted')}\n\n"
        f"<b>{get_custom_text(messages, language, 'order_id') or 'Order ID'}</b>: <code>{order['order_id']}</code>\n\n"
        f"{get_custom_text(messages, language, 'thank_you_retry') or 'Thank you for resubmitting your order. The admin will review it shortly.'}"
    )
    
    await message.edit_text(success_msg, parse_mode="HTML")


@dp.callback_query(F.data == "admin_approve")
async def cb_admin_approve(callback_query: types.CallbackQuery):
    """Show pending orders for approval"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    await callback_query.answer()
    config = load_config()
    pending = [o for o in config['pending_approvals'] if o['status'] == 'pending']
    
    if not pending:
        await callback_query.message.edit_text("✅ No pending orders")
        return
    
    currency = get_currency()
    keyboard_rows = []
    for order in pending:
        btn_text = f"{order['order_id']} - {currency} {order['total_price']:.2f}"
        keyboard_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_order_{order['order_id']}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    await callback_query.message.edit_text(
        f"⏳ Pending Orders: {len(pending)}\n\nSelect an order to review:",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "admin_orders")
async def cb_admin_orders(callback_query: types.CallbackQuery):
    """Show all orders status"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ Not authorized", show_alert=True)
        return
    
    await callback_query.answer()
    config = load_config()
    
    total_orders = len(config['pending_approvals'])
    pending = len([o for o in config['pending_approvals'] if o['status'] == 'pending'])
    approved = len([o for o in config['pending_approvals'] if o['status'] == 'approved'])
    rejected = len([o for o in config['pending_approvals'] if o['status'] == 'rejected'])
    
    stats_text = (
        f"📊 <b>Orders Statistics</b>\n\n"
        f"Total Orders: {total_orders}\n"
        f"⏳ Pending: {pending}\n"
        f"✅ Approved: {approved}\n"
        f"❌ Rejected: {rejected}\n"
    )
    
    await callback_query.message.edit_text(stats_text, parse_mode="HTML")


# ===== Dashboard handoff workers =====
_processing_requests: set[str] = set()
_processed_notifications: set[str] = set()
_provision_queue_busy: bool = False


def is_safe_provision_queue_enabled(config_data: Optional[dict] = None) -> bool:
    """Feature flag for safe single-worker provisioning queue mode."""
    env_value = os.getenv('ENABLE_SAFE_PROVISION_QUEUE')
    if env_value is not None:
        return str(env_value).strip().lower() in ('1', 'true', 'yes', 'on')

    cfg = config_data or load_config()
    return bool(cfg.get('safe_provision_queue_enabled', False))


def provision_request_sort_key(req: dict):
    """Sort queued requests deterministically (created_at, request_id)."""
    created_at = req.get('created_at') or ''
    request_id = req.get('request_id') or ''
    return (str(created_at), str(request_id))

async def process_provision_requests():
    """Consume provision_requests created by the dashboard and deliver configs to buyers."""
    global _provision_queue_busy

    config = load_config()
    reqs = config.get('provision_requests', []) or []
    if not reqs:
        return

    safe_queue_mode = is_safe_provision_queue_enabled(config)
    if safe_queue_mode and _provision_queue_busy:
        return

    queued_requests = [r for r in reqs if r.get('status') == 'queued']
    if not queued_requests:
        return

    if safe_queue_mode:
        queued_requests = sorted(queued_requests, key=provision_request_sort_key)[:1]

    max_attempts = get_provision_max_attempts(config)

    for req in queued_requests:
        if safe_queue_mode:
            _provision_queue_busy = True

        rid = req.get('request_id')
        req_type = req.get('type', 'provision')
        if not rid or rid in _processing_requests:
            if safe_queue_mode:
                _provision_queue_busy = False
            continue
        _processing_requests.add(rid)
        try:
            order_id = req.get('order_id')
            cfg = load_config()
            orders = cfg.get('pending_approvals', [])
            order = next((o for o in orders if o.get('order_id') == order_id), None)
            if not order:
                for r in cfg.get('provision_requests', []):
                    if r.get('request_id') == rid:
                        r['status'] = 'cancelled'
                        r['sent_at'] = datetime.now().isoformat()
                        break
                save_config(cfg)
                continue
            if req_type == 'revoke':
                previous_account_info = dict(order.get('v2ray_config') or {})
                revoke_ok = await revoke_v2ray_account(order)
                cfg_revoke = load_config()
                revoked_order_snapshot = None

                orders_revoke = cfg_revoke.get('pending_approvals', [])
                for idx, o in enumerate(orders_revoke):
                    if o.get('order_id') == order_id:
                        if revoke_ok:
                            revoked_order_snapshot = dict(o)
                            revoked_order_snapshot['status'] = 'revoked'
                            revoked_order_snapshot['revoked_at'] = datetime.now().isoformat()
                            revoked_order_snapshot['revoke_request_id'] = rid

                            if 'revoked_orders' not in cfg_revoke or not isinstance(cfg_revoke.get('revoked_orders'), list):
                                cfg_revoke['revoked_orders'] = []
                            cfg_revoke['revoked_orders'].append(revoked_order_snapshot)

                            orders_revoke.pop(idx)
                        break

                for r in cfg_revoke.get('provision_requests', []):
                    if r.get('request_id') == rid:
                        r['status'] = 'done' if revoke_ok else 'failed'
                        r['last_error'] = None if revoke_ok else 'revoke_failed'
                        r['sent_at'] = datetime.now().isoformat()
                        break
                save_config(cfg_revoke)

                if revoke_ok:
                    cfg_notify = load_config()
                    notify_order = revoked_order_snapshot or order
                    with suppress(Exception):
                        await send_revoke_notice_to_channel(notify_order, previous_account_info, cfg_notify)
                    with suppress(Exception):
                        if previous_account_info:
                            await send_panel_backup_to_channel(notify_order, previous_account_info, cfg_notify)

                _processing_requests.discard(rid)
                continue

            force_regenerate = req_type == 'regenerate'
            if force_regenerate:
                with suppress(Exception):
                    if order.get('v2ray_config'):
                        await revoke_v2ray_account(order)
                order['v2ray_config'] = None
                order['provisioned'] = False

            # If this is a resend request and we already have a config, just resend it
            if req_type == 'resend' and order.get('v2ray_config'):
                account_info = order.get('v2ray_config')
                cfg2 = load_config()
                user_language = order.get('language', 'en')
                account_msg = build_account_message(order, account_info, cfg2, user_language)
                target_user_id = resolve_target_user_id(order=order, req=req)
                if target_user_id is None:
                    logger.error(f"Cannot resend order {order_id}: missing user_id/telegram_id")
                    cfg3 = load_config()
                    for r in cfg3.get('provision_requests', []):
                        if r.get('request_id') == rid:
                            r['status'] = 'failed'
                            r['sent_at'] = datetime.now().isoformat()
                            break
                    save_config(cfg3)
                    _processing_requests.discard(rid)
                    continue

                invite_button = await build_premium_invite_button(target_user_id, cfg2)
                with suppress(Exception):
                    if invite_button:
                        await bot.send_message(target_user_id, account_msg, parse_mode="HTML", reply_markup=invite_button)
                    else:
                        await bot.send_message(target_user_id, account_msg, parse_mode="HTML")
                # Mark request done and continue
                cfg3 = load_config()
                for r in cfg3.get('provision_requests', []):
                    if r.get('request_id') == rid:
                        r['status'] = 'done'
                        r['sent_at'] = datetime.now().isoformat()
                        break
                save_config(cfg3)
                _processing_requests.discard(rid)
                continue
            # If already provisioned/has v2ray_config, mark done
            if (not force_regenerate) and (order.get('v2ray_config') or order.get('provisioned')):
                now_iso = datetime.now().isoformat()
                for r in cfg.get('provision_requests', []):
                    if r.get('order_id') == order_id and r.get('status') == 'queued':
                        r['status'] = 'done'
                        r['sent_at'] = now_iso
                save_config(cfg)
                continue
            # Build panel details using same logic as approve in bot
            isp_providers = get_isp_providers()
            isp = next((p for p in isp_providers if p['id'] == order.get('isp_id')), None)
            package_data = None
            if isp and order.get('user_package_id'):
                package_data = next((p for p in isp.get('packages', []) if p['id'] == order.get('user_package_id')), None)
            if package_data:
                user_sni = package_data.get('sni', '')
                user_address = package_data.get('address', '')
                user_port = package_data.get('port', order.get('user_package_port', 443))
                use_location_sni = package_data.get('use_location_sni', False)
            else:
                user_sni = order.get('user_package_sni', '')
                user_address = order.get('user_package_address', '')
                user_port = order.get('user_package_port', 443)
                use_location_sni = order.get('user_package_use_location_sni', False)
            telegram_username = (order.get('username') or '').replace('@', '') or 'user'
            target_user_id = resolve_target_user_id(order=order, req=req)
            if target_user_id is None:
                logger.error(f"Cannot provision order {order_id}: missing user_id/telegram_id")
                cfg_missing_user = load_config()
                for r in cfg_missing_user.get('provision_requests', []):
                    if r.get('request_id') == rid:
                        attempts = int(r.get('attempts', 0) or 0) + 1
                        r['attempts'] = attempts
                        r['last_error'] = 'missing_user_id_or_telegram_id'
                        r['status'] = 'failed' if attempts >= max_attempts else 'queued'
                        if r['status'] == 'failed':
                            r['sent_at'] = datetime.now().isoformat()
                        break
                save_config(cfg_missing_user)
                _processing_requests.discard(rid)
                continue

            account_info = await create_v2ray_account(
                order.get('package_id'),
                order.get('gb', 0),
                order.get('location_id'),
                telegram_username,
                target_user_id,
                user_sni,
                user_port,
                use_location_sni,
                user_address,
                order.get('client_name'),
                order.get('days') or 30
            )
            if not account_info:
                # Backoff with attempt limits to avoid infinite retries/spam
                cfg_retry = load_config()
                for r in cfg_retry.get('provision_requests', []):
                    if r.get('request_id') == rid:
                        attempts = int(r.get('attempts', 0) or 0) + 1
                        r['attempts'] = attempts
                        r['last_error'] = 'account_creation_failed'
                        if attempts >= max_attempts:
                            r['status'] = 'failed'
                            r['sent_at'] = datetime.now().isoformat()
                        break
                save_config(cfg_retry)
                _processing_requests.discard(rid)
                continue
            # Persist results FIRST to avoid duplicate provisioning on later notification errors
            cfg = load_config()
            for o in cfg.get('pending_approvals', []):
                if o.get('order_id') == order_id:
                    o['v2ray_config'] = account_info
                    o['provisioned'] = True
                    o['sent_at'] = datetime.now().isoformat()
                    # Ensure approved (dashboard already set it, but be safe)
                    o['status'] = 'approved'
                    o.setdefault('approved_at', datetime.now().isoformat())
                    o.setdefault('approved_by', 'dashboard')
                    if force_regenerate:
                        o['regenerated_at'] = datetime.now().isoformat()
                    break
            # Mark request done before optional side-effects
            now_iso = datetime.now().isoformat()
            for r in cfg.get('provision_requests', []):
                if r.get('order_id') == order_id and r.get('status') == 'queued':
                    r['status'] = 'done'
                    r['sent_at'] = now_iso
            save_config(cfg)

            # Send message to user
            cfg2 = load_config()
            user_language = order.get('language', 'en')
            account_msg = build_account_message(order, account_info, cfg2, user_language)
            invite_button = await build_premium_invite_button(target_user_id, cfg2)
            with suppress(Exception):
                if invite_button:
                    await bot.send_message(target_user_id, account_msg, parse_mode="HTML", reply_markup=invite_button)
                else:
                    await bot.send_message(target_user_id, account_msg, parse_mode="HTML")
            await send_account_ready_to_channel(order, account_msg, cfg2)
            await send_panel_backup_to_channel(order, account_info, cfg2)
        except Exception as e:
            logger.error(f"Provision request {rid} failed: {e}")
            with suppress(Exception):
                cfg_fail = load_config()
                for r in cfg_fail.get('provision_requests', []):
                    if r.get('request_id') == rid:
                        attempts = int(r.get('attempts', 0) or 0) + 1
                        r['attempts'] = attempts
                        r['last_error'] = str(e)
                        if attempts >= max_attempts:
                            r['status'] = 'failed'
                            r['sent_at'] = datetime.now().isoformat()
                        break
                save_config(cfg_fail)
        finally:
            _processing_requests.discard(rid)
            if safe_queue_mode:
                _provision_queue_busy = False

async def process_admin_notifications():
    """Broadcast dashboard approval notifications to all admins."""
    cfg = load_config()
    notes = cfg.get('notifications', []) or []
    admin_ids = list(get_admin_ids())
    changed = False
    for n in notes:
        if n.get('type') != 'order_approved' or n.get('delivered'):
            continue
        nid = n.get('id')
        if nid in _processed_notifications:
            continue
        _processed_notifications.add(nid)
        text = (
            f"🔔 Order Approved\n"
            f"ID: {n.get('order_id')}\n"
            f"At: {n.get('approved_at')}\n"
            f"By: {n.get('approved_by_admin_id')}"
        )
        for aid in admin_ids:
            with suppress(Exception):
                await bot.send_message(aid, text)
        n['delivered'] = True
        changed = True
    if changed:
        save_config(cfg)


async def main():
    """Start the bot"""
    logger.info("🤖 V2Ray Sales Bot starting...")
    logger.info(f"📦 Packages: {len(get_packages())}")
    logger.info(f"🌍 Locations: {len(get_locations())}")
    logger.info(f"📋 Panels: {len(get_panels())}")
    
    import aioschedule
    from channel_removal import remove_expired_members
    aioschedule.every().day.at("00:10").do(lambda: asyncio.create_task(remove_expired_members(bot)))
    async def schedule_loop():
        while True:
            await aioschedule.run_pending()
            await asyncio.sleep(60)

    async def provision_loop():
        while True:
            with suppress(Exception):
                await process_provision_requests()
            await asyncio.sleep(5)

    async def notifications_loop():
        while True:
            with suppress(Exception):
                await process_admin_notifications()
            await asyncio.sleep(10)

    try:
        asyncio.create_task(schedule_loop())
        asyncio.create_task(provision_loop())
        asyncio.create_task(notifications_loop())
        await dp.start_polling(bot)
    finally:
        with suppress(Exception):
            await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
