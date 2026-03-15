"""
Firebase Database Module for V2Ray Bot
Handles all Firebase Firestore operations with JSON file fallback
"""

import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
from typing import Dict, Any, Optional
import asyncio
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Firebase initialization
_firebase_initialized = False
_db = None
_use_firebase = False

CONFIG_PATH = (
    os.getenv('BOT_CONFIG_PATH')
    or os.getenv('CONFIG_PATH')
    or os.path.join(os.path.dirname(__file__), 'config.json')
)
FIREBASE_CRED_PATH = (
    os.getenv('BOT_FIREBASE_CRED_PATH')
    or os.getenv('FIREBASE_CRED_PATH')
    or os.path.join(os.path.dirname(__file__), 'firebase-credentials.json')
)


def _get_firebase_credentials_source() -> Optional[Dict[str, Any]]:
    """Return Firebase credentials from env JSON or file path."""
    cred_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
    if cred_json:
        try:
            return {'type': 'json', 'value': json.loads(cred_json)}
        except Exception as e:
            logger.error(f"Invalid FIREBASE_CREDENTIALS_JSON: {e}")
            return None

    if os.path.exists(FIREBASE_CRED_PATH):
        return {'type': 'file', 'value': FIREBASE_CRED_PATH}

    return None


def init_firebase():
    """Initialize Firebase if credentials are available"""
    global _firebase_initialized, _db, _use_firebase
    
    if _firebase_initialized:
        return _use_firebase
    
    try:
        cred_source = _get_firebase_credentials_source()
        if cred_source:
            if cred_source['type'] == 'json':
                cred = credentials.Certificate(cred_source['value'])
            else:
                cred = credentials.Certificate(cred_source['value'])
            firebase_admin.initialize_app(cred)
            _db = firestore.client()
            _use_firebase = True
            logger.info("✅ Firebase initialized successfully")
        else:
            logger.warning("⚠️ Firebase credentials not found (file/env). Using JSON file fallback.")
            _use_firebase = False
    except Exception as e:
        logger.error(f"❌ Failed to initialize Firebase: {e}")
        _use_firebase = False
    
    _firebase_initialized = True
    return _use_firebase


def load_from_json() -> Dict[str, Any]:
    """Load configuration from JSON file"""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)

        config_env = os.getenv('BOT_CONFIG_JSON')
        if config_env:
            return json.loads(config_env)

        logger.warning("No config.json found and BOT_CONFIG_JSON is not set.")
        return {}
    except Exception as e:
        logger.error(f"Error loading from JSON: {e}")
        return {}


def save_to_json(config: Dict[str, Any]):
    """Save configuration to JSON file with important keys at the top"""
    try:
        # Create ordered dict with important keys first
        ordered_config = {}
        
        # Priority keys that should appear at the top
        priority_keys = [
            'telegram_bot_token',
            'admin_ids',
            'admin_password',
            'currency',
            'subscription_duration'
        ]
        
        # Add priority keys first (if they exist)
        for key in priority_keys:
            if key in config:
                ordered_config[key] = config[key]
        
        # Add remaining keys
        for key, value in config.items():
            if key not in priority_keys:
                ordered_config[key] = value
        
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(ordered_config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving to JSON: {e}")


def load_config() -> Dict[str, Any]:
    """
    Load configuration from Firebase or JSON file
    Returns: Configuration dictionary
    """
    init_firebase()
    
    if _use_firebase and _db:
        try:
            # Load from Firebase
            doc_ref = _db.collection('bot_config').document('main')
            doc = doc_ref.get()
            
            if doc.exists:
                config = doc.to_dict()
                # Also save to JSON as backup
                save_to_json(config)
                return config
            else:
                # If Firebase doc doesn't exist, load from JSON and upload
                logger.info("Firebase document not found. Loading from JSON...")
                config = load_from_json()
                if config:
                    doc_ref.set(config)
                    logger.info("✅ Uploaded config to Firebase")
                return config
        except Exception as e:
            logger.error(f"Error loading from Firebase: {e}. Falling back to JSON.")
            return load_from_json()
    else:
        # Use JSON file
        return load_from_json()


def save_config(config: Dict[str, Any]):
    """
    Save configuration to Firebase and JSON file
    Args:
        config: Configuration dictionary to save
    """
    # Always save to JSON as backup
    save_to_json(config)
    
    init_firebase()
    
    if _use_firebase and _db:
        try:
            # Save to Firebase
            doc_ref = _db.collection('bot_config').document('main')
            doc_ref.set(config)
            logger.debug("✅ Saved to Firebase")
        except Exception as e:
            logger.error(f"Error saving to Firebase: {e}")


# Async wrappers for use in bot
async def async_load_config() -> Dict[str, Any]:
    """Async wrapper for load_config"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, load_config)


async def async_save_config(config: Dict[str, Any]):
    """Async wrapper for save_config"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_config, config)


def get_firebase_status() -> Dict[str, Any]:
    """Get Firebase connection status"""
    init_firebase()
    return {
        'initialized': _firebase_initialized,
        'using_firebase': _use_firebase,
        'has_credentials': _get_firebase_credentials_source() is not None,
        'fallback_available': os.path.exists(CONFIG_PATH)
    }


def migrate_to_firebase():
    """
    Migrate existing JSON data to Firebase
    Returns: Success status and message
    """
    try:
        if _get_firebase_credentials_source() is None:
            return False, "Firebase credentials not found"
        
        init_firebase()
        
        if not _use_firebase:
            return False, "Firebase initialization failed"
        
        # Load from JSON
        config = load_from_json()
        
        if not config:
            return False, "No data in config.json"
        
        # Upload to Firebase
        doc_ref = _db.collection('bot_config').document('main')
        doc_ref.set(config)
        
        return True, f"Successfully migrated {len(config)} config keys to Firebase"
    
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return False, str(e)


# Collection-specific helpers for better organization (optional advanced usage)

def get_pending_approvals() -> list:
    """Get pending approvals from config"""
    config = load_config()
    return config.get('pending_approvals', [])


def save_pending_approvals(approvals: list):
    """Save pending approvals to config"""
    config = load_config()
    config['pending_approvals'] = approvals
    save_config(config)


def get_packages() -> list:
    """Get packages from config"""
    config = load_config()
    return config.get('packages', [])


def get_locations() -> list:
    """Get locations from config"""
    config = load_config()
    return config.get('locations', [])


def get_panels() -> list:
    """Get panels from config"""
    config = load_config()
    return config.get('panels', [])


def get_isp_providers() -> list:
    """Get ISP providers from config"""
    config = load_config()
    return config.get('isp_providers', [])


def get_payment_details() -> Dict[str, Any]:
    """Get payment details from config"""
    config = load_config()
    return config.get('payment_details', {})


def get_admin_ids() -> list:
    """Get admin IDs from config"""
    config = load_config()
    return config.get('admin_ids', [])


if __name__ == '__main__':
    # Test Firebase connection
    print("Testing Firebase connection...")
    status = get_firebase_status()
    print(f"Status: {status}")
    
    if status['using_firebase']:
        print("\n✅ Firebase is active!")
        print("Testing data load...")
        config = load_config()
        print(f"Loaded {len(config)} config keys")
    else:
        print("\n⚠️ Using JSON file mode")
        print("To enable Firebase:")
        print("1. Create a Firebase project")
        print("2. Download service account credentials")
        print("3. Save as 'firebase-credentials.json'")
