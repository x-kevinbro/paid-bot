import asyncio
from datetime import datetime, timedelta
from aiogram import Bot
import logging
import os
from firebase_db import load_config, save_config

logger = logging.getLogger(__name__)

def _parse_iso_datetime(value):
    if not value or not isinstance(value, str):
        return None
    try:
        # Supports both plain ISO and UTC Z suffix.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _order_reference_time(order):
    # Prefer approval timestamp, then creation timestamp.
    return (
        _parse_iso_datetime(order.get("approved_at"))
        or _parse_iso_datetime(order.get("created_at"))
        or datetime.min
    )


async def remove_expired_members(bot: Bot):
    config = load_config()
    premium_channel_id = os.getenv('PREMIUM_CHANNEL_ID') or config.get('premium_channel_id')
    if not premium_channel_id:
        logger.warning("No premium channel ID set.")
        return

    channel_id = premium_channel_id
    if isinstance(premium_channel_id, str):
        stripped = premium_channel_id.strip()
        if stripped.lstrip("-").isdigit():
            channel_id = int(stripped)

    now = datetime.now()
    changed = False

    # Evaluate only the latest approved order per user.
    latest_order_by_user = {}
    for order in config.get("pending_approvals", []):
        if order.get("status") != "approved":
            continue
        user_id = order.get("user_id")
        if not user_id:
            continue
        current = latest_order_by_user.get(user_id)
        if current is None or _order_reference_time(order) > _order_reference_time(current):
            latest_order_by_user[user_id] = order

    for user_id, order in latest_order_by_user.items():
        expiry_ts = order.get("expiry") or order.get("v2ray_config", {}).get("expiry")
        purchased_at = _order_reference_time(order)
        if not expiry_ts or purchased_at == datetime.min:
            continue

        expiry_dt = datetime.fromtimestamp(expiry_ts / 1000)
        remove_after = purchased_at + timedelta(days=33)

        # Remove only when BOTH conditions are true:
        # 1) current account is expired
        # 2) at least 33 days passed since purchase/approval
        should_remove = now >= expiry_dt and now >= remove_after
        if not should_remove:
            continue
        if order.get("channel_removed_at"):
            continue

        try:
            await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
            # Unban immediately so user can rejoin after renewal.
            await bot.unban_chat_member(chat_id=channel_id, user_id=user_id)
            order["channel_removed_at"] = now.isoformat()
            order["channel_removed_reason"] = "expired_and_33_days_after_purchase"
            changed = True
            logger.info(
                f"Removed user {user_id} from premium channel. "
                f"expiry={expiry_dt.isoformat()} purchased_at={purchased_at.isoformat()} remove_after={remove_after.isoformat()}"
            )
        except Exception as e:
            logger.error(f"Failed to remove user {user_id} from channel: {e}")

    if changed:
        save_config(config)
    else:
        logger.info("Channel removal check complete: no users matched removal criteria.")

# To schedule this, add to your main loop:
# import aioschedule
# aioschedule.every().day.at("00:10").do(lambda: asyncio.create_task(remove_expired_members(bot)))
# And in your polling loop: await aioschedule.run_pending()
