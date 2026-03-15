"""
Firebase Migration Utility
Migrates data from config.json to Firebase Firestore
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from firebase_db import migrate_to_firebase, get_firebase_status, load_config

def main():
    print("=" * 60)
    print("Firebase Migration Utility")
    print("=" * 60)
    
    # Check Firebase status
    print("\n1. Checking Firebase status...")
    status = get_firebase_status()
    
    print(f"   ✓ Firebase initialized: {status['initialized']}")
    print(f"   ✓ Using Firebase: {status['using_firebase']}")
    print(f"   ✓ Has credentials: {status['has_credentials']}")
    print(f"   ✓ JSON fallback available: {status['fallback_available']}")
    
    if not status['has_credentials']:
        print("\n❌ ERROR: Firebase credentials not found!")
        print("\nPlease follow these steps:")
        print("1. Go to Firebase Console: https://console.firebase.google.com/")
        print("2. Select your project (or create a new one)")
        print("3. Go to Project Settings > Service Accounts")
        print("4. Click 'Generate New Private Key'")
        print("5. Save the downloaded file as 'firebase-credentials.json'")
        print("6. Place it in the same directory as this script")
        return
    
    if not status['using_firebase']:
        print("\n❌ ERROR: Firebase initialization failed!")
        print("Check the error logs above.")
        return
    
    # Load current config to show stats
    print("\n2. Loading current configuration...")
    config = load_config()
    
    print(f"\n   Configuration statistics:")
    print(f"   • Packages: {len(config.get('packages', []))}")
    print(f"   • ISP Providers: {len(config.get('isp_providers', []))}")
    print(f"   • Locations: {len(config.get('locations', []))}")
    print(f"   • Panels: {len(config.get('panels', []))}")
    print(f"   • Pending Orders: {len(config.get('pending_approvals', []))}")
    print(f"   • Admin IDs: {len(config.get('admin_ids', []))}")
    print(f"   • Payment Methods: {len(config.get('payment_details', {}).get('methods', []))}")
    
    # Confirm migration
    print("\n3. Ready to migrate to Firebase")
    response = input("\n   Proceed with migration? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\n❌ Migration cancelled by user.")
        return
    
    # Perform migration
    print("\n4. Migrating data to Firebase...")
    success, message = migrate_to_firebase()
    
    if success:
        print(f"\n✅ SUCCESS: {message}")
        print("\nYour data is now stored in Firebase!")
        print("The local config.json file is kept as a backup.")
        print("\nNext steps:")
        print("• The bot will now use Firebase automatically")
        print("• Admin dashboard will sync in real-time")
        print("• JSON file serves as local backup")
    else:
        print(f"\n❌ MIGRATION FAILED: {message}")
        print("The bot will continue using config.json")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
