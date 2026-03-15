import re


class _SafeFormatDict(dict):
    """Keep unknown placeholders unchanged instead of raising KeyError."""

    def __missing__(self, key):
        return '{' + key + '}'


def _safe_format_text(text: str, **kwargs) -> str:
    """Format text with provided kwargs, tolerating minor placeholder issues.

    - Normalizes placeholders like '{ min_gb }' -> '{min_gb}'
    - Leaves unknown placeholders untouched instead of returning raw text
    """
    normalized = re.sub(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}", r"{\1}", text)
    try:
        return normalized.format_map(_SafeFormatDict(**kwargs))
    except Exception:
        return text


def get_custom_text(messages: dict, language: str, key: str, **kwargs) -> str:
    """
    Get custom text from config messages if set and not empty, otherwise fallback to default translation.
    """
    # Try config override
    config_key = f'all_texts_{language}_{key}'
    value = messages.get(config_key)
    if value is not None and str(value).strip():
        return _safe_format_text(str(value), **kwargs)
    # Fallback to default
    return get_text(language, key, **kwargs)
"""
Language Management Module for V2Ray Bot
Supports English and Sinhala
"""

# Language translations dictionary
TRANSLATIONS = {
    'en': {
        # Start command
        'welcome': '👋 Welcome to V2Ray Sales Bot!',
        'welcome_desc': '🌍 Fast, reliable, and affordable V2Ray accounts\n📱 Easy purchase process\n⚡ Instant activation after payment approval\n\nClick below to get started:',
        'select_language': '🌐 <b>Select Your Preferred Language</b>\n\nChoose your language to continue:',
        
        # Buttons
        'buy_account': '🛒 Buy V2Ray Account',
        'approve_orders': '✅ Approve Orders',
        'orders_status': '📊 Orders Status',
        'english': '🇬🇧 English',
        'sinhala': '🇱🇰 සිංහල (Sinhala)',
        'back_to_main': '🔙 Back to Main Menu',
        'back_to_isp': '🔙 Back to ISP Selection',
        'back_to_package': '🔙 Back to Package Selection',
        'back_to_location': '🔙 Back to Location Selection',
        'skip': '⏭️ Skip',
        
        # ISP Selection
        'select_isp': '🌐 <b>Select Your ISP Provider</b>',
        'select_isp_desc': 'Which Internet Service Provider do you use in Sri Lanka?',
        
        # Package Selection
        'select_package': '📦 <b>Which Package/App Do You Use?</b>',
        'select_package_desc': 'Select the package or app you\'re using with {isp_name}:',
        'you_selected': 'You selected: {name}',
        
        # V2Ray Package
        'select_v2ray_package': '📦 <b>Now Select Your V2Ray Package</b>',
        'select_v2ray_desc': 'Choose the package that suits your needs:',
        'using': 'You\'re using: <b>{name}</b>',
        'unlimited': 'Unlimited',
        'gb': 'GB',
        'per_month': '/month',
        
        # Custom Package
        'predefined_packages': '📦 Predefined Packages',
        'custom_package': '✨ Custom Package',
        'select_package_type': 'Choose Package Type',
        'select_package_type_desc': 'Would you like to choose from our predefined packages or create a custom package?',
        'enter_custom_gb': 'Enter Data Amount (GB)',
        'enter_custom_gb_desc': 'Please enter how many GB you need.\n\nMinimum: {min_gb} GB\nMaximum: {max_gb} GB\nPrice: {currency} {price_per_gb} per GB',
        'enter_custom_days': 'Enter Duration (Days)',
        'enter_custom_days_desc': 'Please enter how many days you need.\n\nMinimum: {min_days} days\nMaximum: {max_days} days\nPrice: {currency} {price_per_day} per day',
        'invalid_gb_range': '❌ Please enter a value between {min_gb} and {max_gb} GB.',
        'invalid_days_range': '❌ Please enter a value between {min_days} and {max_days} days.',
        'invalid_number': '❌ Please enter a valid number.',
        'duration': 'Duration',
        'data': 'Data',
        'back': '🔙 Back',
        
        # Location
        'select_location': '🌍 <b>Select Server Location</b>',
        'select_location_desc': 'Where would you like your V2Ray account to be hosted?',
        
        # Payment
        'payment_details': '💳 <b>Payment Details</b>',
        'payment_method': 'Payment Method',
        'account_name': 'Account Name',
        'account_number': 'Account Number',
        'bank_name': 'Bank Name',
        'mobile_number': 'Mobile Number',
        'ezcash_fee_note': 'ℹ️ Note: eZcash transactions include a 40 LKR processing fee',
        'crypto_type': 'Crypto Type',
        'crypto_address': 'Crypto Address',
        'upload_receipt': '📸 Upload Receipt',
        'upload_receipt_desc': 'Please upload a screenshot or photo of your payment receipt:',
        'enter_client_name_prompt': '👤 <b>Please enter your name</b>\n\nWe will use this name (plus 4 random digits) to create your client in the panel.\n\nSend your name now:',
        'upload_receipt_full_prompt': '📸 <b>Upload Payment Receipt</b>\n\nPlease send a screenshot or photo of your payment receipt.\nMake sure it clearly shows:\n• Transaction ID or confirmation number\n• Amount paid\n• Date and time\n\nYou can send as photo or PDF/image document.',
        'payment_choose_method': '💳 <b>Choose Payment Method</b>',
        'payment_available_methods': 'Available Payment Methods:',
        'apply_invalid_format': '❌ <b>Invalid format!</b>\n\n<b>Usage:</b> <code>/apply YOUR_CODE_HERE</code>\n\n<b>Example:</b> <code>/apply REF1234AB</code>',
        'apply_cooldown_active': '⏰ <b>Cooldown Active</b>\n\nYou cannot claim any code right now.\n\n<b>Cool Down Time:</b> {minutes}m {seconds}s\n<i>During this cool down time, you cannot claim admin or referral codes.</i>',
        'apply_claims_disabled': '❌ <b>Referral Claims Disabled</b>\n\nThe admin has temporarily disabled referral and coupon claims.\nPlease try again later.',
        'apply_rate_limited': '⏰ <b>Rate Limited</b>\n\nYou can apply {attempts}/3 codes per hour.\nTry again in {minutes}m {seconds}s',
        'apply_code_not_found': '❌ Code <code>{code}</code> not found.',
        'apply_code_expired': '❌ Code <code>{code}</code> has expired (valid for 24 hours only).',
        'apply_code_max_uses': '❌ Code <code>{code}</code> has reached max uses ({max_uses}).',
        'apply_code_already_used': '❌ You\'ve already used code <code>{code}</code>.',
        'apply_cannot_use_own': '❌ You cannot use your own referral code.',
        'apply_success_admin': '✅ <b>Code Applied!</b>\n\nCode: <code>{code}</code>\nDiscount: <b>{discount_percent}%</b>\n\n💡 <b>Next Steps:</b>\n1. Go buy a V2Ray account using /buy or the /start menu\n2. Your discount will be applied at checkout\n\n<i>Remaining claims from this admin: {remaining_claims}/3</i>',
        'apply_success_user': '✅ <b>Code Applied!</b>\n\nCode: <code>{code}</code>\nDiscount: <b>{discount_percent}%</b>\n\n💡 <b>Next Steps:</b>\n1. Go buy a V2Ray account using /buy or the /start menu\n2. Your discount will be applied at checkout\n\n<i>Remaining attempts: {remaining_attempts}/3 per hour</i>',
        'receipt_uploaded': '✅ Receipt uploaded successfully!',
        'receipt_received': '✅ Receipt received!',
        'add_note': '📝 Add a Note for Admin',
        'send_now': '✅ Send Now',
        'add_note_prompt': '📝 Add Your Note',
        'add_note_desc': 'Send any additional information you\'d like the admin to see (e.g., payment reference, special requests, etc.):',
        'note_added': '✅ Note added! Sending your order to admin...',
        'sending_order': '✅ Sending your order to admin...',
        'receipt_note_question': 'Would you like to add a note for the admin, or send your order now?',
        'order_creating': '⏳ Creating your order...',
        'order_created': '✅ <b>Order Created Successfully!</b>',
        'order_details': 'Your order is now pending admin approval. You will be notified once your account is ready.',
        'order_id': 'Order ID',
        'data': 'Data',
        'back_to_v2ray_package': '🔙 Back to V2Ray Packages',
        'location_not_found': '❌ Location not found',
        'payment_method_not_found': '❌ Payment method not found',
        'valid_name_required': '❌ Please enter a valid name.',
        'receipt_photo_or_document_required': '❌ Please send a photo or document as your payment receipt',
        'receipt_unsupported_format': '❌ Unsupported receipt format. Please send a photo, or a document in PDF/JPG/PNG format.',
        'total_price': 'Total Price',
        'waiting_approval': 'Status: ⏳ Waiting for approval',
        'order_cancelled': '❌ Order cancelled.',
        'start_over': 'Would you like to start over?',
        
        # Referral Program
        'referral_program': '🎁 Referral Program',
        'your_referral_code': 'Your Referral Code',
        'share_code': 'Share this code with friends and both get discount!',
        'referral_discount': 'Referral Discount',
        'referrals_count': 'People Referred',
        'you_have_earned': 'You have earned',
        'referral_credit': 'in referral credit',
        'copy_code': 'Copy Code',
        'enter_referral_code': 'Have a referral code?',
        'referral_code_applied': '✅ Referral code applied! You got {discount_percent}% off!',
        'invalid_referral_code': '❌ Invalid or expired referral code',
        'cannot_use_own_code': '❌ You cannot use your own referral code',
        'referral_need_first_purchase': '⚠️ You need to complete your first purchase to get a referral code.\n\nOnce your order is approved, you\'ll receive a unique referral code to share!',
        'your_referral_program': '🎁 <b>Your Referral Program</b>',
        'click_to_copy': '<i>Click to copy</i> ☝️',
        'code_stats': '📊 <b>Code Stats:</b>',
        'discount_they_get': 'Discount They Get',
        'pending_rewards_title': '🏆 <b>Your Pending Rewards:</b>',
        'pending_rewards_count': 'You have <b>{count}</b> unused discount(s) waiting!',
        'pending_reward_item': '{index}. {discount_percent}% off (from code {code})',
        'use_next_purchase': '✨ Use one on your next purchase!',
        'no_pending_rewards': '⏳ <b>No Pending Rewards Yet</b>',
        'no_pending_rewards_desc': 'Share your code to get referral rewards! Once someone uses it and orders are approved, you\'ll get {discount_percent}% off your next purchase.',
        'used_rewards': '✅ <b>Used Rewards:</b> {count}',
        'how_it_works': '💡 <b>How It Works:</b>',
        'how_it_works_steps': '1️⃣ Share your code with friends\n2️⃣ They use it during their first purchase\n3️⃣ They get {discount_percent}% discount\n4️⃣ Once their order is approved, YOU get {discount_percent}% off your next purchase!',
        'share_this_message': '🔗 <b>Share this message:</b>',
        'share_message_text': '"Use my referral code <code>{code}</code> to get {discount_percent}% off your V2Ray account!"',
        
        # Admin
        'admin_auth': '🔐 Admin Authentication',
        'enter_password': 'Please enter admin password:',
        'invalid_password': '❌ Invalid password!',
        'pending_orders': '📋 Pending Orders',
        'no_pending_orders': '✅ No pending orders',
        'approve': '✅ Approve',
        'reject': '❌ Reject',
        'order_number': 'Order #{order_id}',
        'from': 'From',
        'package_info': 'Package',
        'location': 'Location',
        'price': 'Price',
        'status': 'Status',
        'pending': '⏳ Pending',
        'approved': '✅ Approved',
        'rejected': '❌ Rejected',
        'processing': '🔄 Processing',
        'account_created': '✅ Account Created',
        'orders_statistics': '📊 Orders Statistics',
        'total_orders': 'Total Orders',
        'approved_count': 'Approved',
        'pending_count': 'Pending',
        'rejected_count': 'Rejected',
        
        # Retry after rejection
        'retry': '🔄 Retry',
        'contact_support': '📞 Contact Support',
        'rejection_reason': 'Possible reasons for rejection',
        'invalid_receipt': 'Invalid or unclear payment receipt',
        'insufficient_payment': 'Insufficient payment amount',
        'unclear_details': 'Unclear transaction details',
        'retry_instructions': 'Please review and try again with a clearer receipt or additional details.',
        'retry_new_receipt': 'Upload New Payment Receipt',
        'retry_instructions_detail': 'Please upload a clear photo or document of your payment receipt. Make sure all details are visible.',
        'cancel': '❌ Cancel',
        'note_saved': '✅ Note saved!',
        'your_note': 'Your note',
        'order_submitted': '✅ Order submitted for review!',
        'thank_you_retry': 'Thank you for resubmitting your order. The admin will review it shortly.',
        'approve': '✅ Approve',
        'reject': '❌ Reject',
        'package_info': 'Package',
        'price': 'Price',
        
        # Errors
        'not_authorized': '❌ You are not authorized to use this command.',
        'isp_not_found': '❌ ISP not found',
        'package_not_found': '❌ Package not found',
        'no_packages_available': '❌ No packages available for {name}.\nPlease contact admin.',
        'error_occurred': '❌ An error occurred. Please try again.',
        'not_admin': '❌ This command is only for admins.',
        
        # Success
        'success': '✅ Success',
        'saved': '✅ Saved successfully',
    },
    'si': {
        # Start command
        'welcome': '👋 V2Ray විකිණුම් බොට් වෙත සාදරයි!',
        'welcome_desc': '🌍 වේගවත්, විශ්වාසනීය සහ සාশ්‍රිත V2Ray ගිණුම්\n📱 පහසු ගනුදෙනු ක්‍රියාවලිය\n⚡ ගෙවීම අනුමোදනයෙන් පසු වහාම සක්‍රිය කිරීම\n\nආරම්භ කිරීමට පහත ක්ලික් කරන්න:',
        'select_language': '🌐 <b>ඔබගේ අපේක්ෂිත භාෂාව තෝරන්න</b>\n\nඉදිරියට යාමට ඔබගේ භාෂාව තෝරන්න:',
        
        # Buttons
        'buy_account': '🛒 V2Ray මිලදී ගන්න',
        'approve_orders': '✅ ඇණවුම් අනුමත කරන්න',
        'orders_status': '📊 ඇණවුම් තත්ත්වය',
        'english': '🇬🇧 English',
        'sinhala': '🇱🇰 සිංහල (Sinhala)',
        'back_to_main': '🔙 ප්‍රධාන මෙනුවට',
        'back_to_isp': '🔙 ISP තෝරාගැනීමට',
        'back_to_package': '🔙 පැකේජ තෝරාගැනීමට',
        'back_to_location': '🔙 ස්ථානය තෝරාගැනීමට',
        'skip': '⏭️ මඟ හරින්න',
        
        # ISP Selection
        'select_isp': '🌐 <b>ඔබගේ ISP සපයා ගන්නා slovenia තෝරන්න</b>',
        'select_isp_desc': 'ශ්‍රී ලංකාවේ ඔබ භාවිතා කරන ඉන්ටර්නෙට් සේවා සපයා ගන්නා inator?',
        
        # Package Selection
        'select_package': '📦 <b>ඔබ භාවිතා කරන පැකේජ/යෙදුම කුමක්ද?</b>',
        'select_package_desc': '{isp_name} සමඟ ඔබ භාවිතා කරන පැකේජ හෝ යෙදුම තෝරන්න:',
        'you_selected': 'ඔබ තෝරා ගත්තේ: {name}',
        
        # V2Ray Package
        'select_v2ray_package': '📦 <b>ඔබගේ V2Ray පැකේජ තෝරන්න</b>',
        'select_v2ray_desc': 'ඔබගේ අවශ්‍යතා සපුරාලන පැකේජ තෝරන්න:',
        'using': 'ඔබ භාවිතා කරන්නේ: <b>{name}</b>',
        'unlimited': 'සීමාතරහා',
        'gb': 'GB',
        'per_month': '/මාසයට',
        
        # Custom Package
        'predefined_packages': '📦 සාමාන්‍ය පැකේජ',
        'custom_package': '✨ අභිරුචි පැකේජය',
        'select_package_type': 'පැකේජ වර්ගය තෝරන්න',
        'select_package_type_desc': 'ඔබට අපගේ සාමාන්‍ය පැකේජයන්ගෙන් එකක් තෝරන්නද නැතහොත් අභිරුචි පැකේජයක් සෑදන්නද?',
        'enter_custom_gb': 'දත්ත ප්‍රමාණය ඇතුල් කරන්න (GB)',
        'enter_custom_gb_desc': 'කරුණාකර ඔබට අවශ්‍ය GB ප්‍රමාණය ඇතුලත් කරන්න.\n\nඅවම: {min_gb} GB\nඅධික: {max_gb} GB\nමිල: {currency} {price_per_gb} GB එකකට',
        'enter_custom_days': 'කාල සීමාව ඇතුල් කරන්න (දින)',
        'enter_custom_days_desc': 'කරුණාකර ඔබට අවශ්‍ය දින සංඛ්‍යාව ඇතුලත් කරන්න.\n\nඅවම: {min_days} දින\nඅධික: {max_days} දින\nමිල: {currency} {price_per_day} දිනයකට',
        'invalid_gb_range': '❌ කරුණාකර {min_gb} සහ {max_gb} GB අතර අගයක් ඇතුලත් කරන්න.',
        'invalid_days_range': '❌ කරුණාකර {min_days} සහ {max_days} දින අතර අගයක් ඇතුලත් කරන්න.',
        'invalid_number': '❌ කරුණාකර වලංගු අංකයක් ඇතුලත් කරන්න.',
        'duration': 'කාල සීමාව',
        'data': 'දත්ත',
        'back': '🔙 ආපසු',
        
        # Location
        'select_location': '🌍 <b>සර්වර් ස්ථානය තෝරන්න</b>',
        'select_location_desc': 'ඔබගේ V2Ray ගිණුම කොතැනින් සත්කාරය කිරීමට ඔබ අවශ්‍ය ද?',
        
        # Payment
        'payment_details': '💳 <b>ගෙවීමේ විස්තර</b>',
        'payment_method': 'ගෙවීමේ ක්‍රමය',
        'account_name': 'ගිණුම් නම',
        'account_number': 'ගිණුම් අංකය',
        'bank_name': 'බැංකු නම',
        'mobile_number': 'ජංගම අංකය',
        'ezcash_fee_note': 'ℹ️ සටහන: eZcash ගනුදෙනු සඳහා රු. 40 ක සැකසුම් ගාස්තුවක් ඇතුළත් වේ',
        'crypto_type': 'ගුප්තකේතන ස්වරූපය',
        'crypto_address': 'ගුප්තකේතන ලිපිනය',
        'upload_receipt': '📸 රසිද උඩුවන්න',
        'upload_receipt_desc': 'කරුණාකර ඔබගේ ගෙවීම් රසිදේ ස්ක්‍රීන්ශොට් හෝ පින්තුරදැන්වුවන්න:',
        'enter_client_name_prompt': '👤 <b>කරුණාකර ඔබගේ නම ඇතුළත් කරන්න</b>\n\nමෙම නම (අහඹු ඉලක්කම් 4ක් සමඟ) panel එකේ ඔබගේ client නම සෑදීමට භාවිතා කරයි.\n\nදැන් ඔබගේ නම යවන්න:',
        'upload_receipt_full_prompt': '📸 <b>ගෙවීම් රිසිට් පත්‍රය උඩුගත කරන්න</b>\n\nකරුණාකර ඔබගේ ගෙවීම් රිසිට් පත්‍රයේ screenshot එකක් හෝ ඡායාරූපයක් යවන්න.\nපහත තොරතුරු පැහැදිලිව පෙනෙන බව තහවුරු කරන්න:\n• ගනුදෙනු අංකය හෝ තහවුරු කිරීමේ අංකය\n• ගෙවූ මුදල\n• දිනය සහ වේලාව\n\nඔබට මෙය photo එකක් ලෙස හෝ PDF/image document එකක් ලෙස යවිය හැක.',
        'payment_choose_method': '💳 <b>ගෙවීම් ක්‍රමය තෝරන්න</b>',
        'payment_available_methods': 'ලබාගත හැකි ගෙවීම් ක්‍රම:',
        'receipt_uploaded': '✅ රසිද සफලව උඩුවී ඇත!',
        'receipt_received': '✅ රසිද ලැබී ඇත!',
        'add_note': '📝 පරිපාලකයා සඳහා සටහනක් එක් කරන්න',
        'send_now': '✅ දැන් යවන්න',
        'add_note_prompt': '📝 ඔබේ සටහන එක් කරන්න',
        'add_note_desc': 'පරිපාලකයාට පෙන්විය යුතු අතිරේක තොරතුරු යවන්න (උදා: ගෙවීම් යොමුව, විශේෂ ඉල්ලීම් යනාදිය):',
        'note_added': '✅ සටහන එක් කරන ලදී! පරිපාලකයාට ඔබේ ඇණවුම යවමින්...',
        'sending_order': '✅ පරිපාලකයාට ඔබේ ඇණවුම යවමින්...',
        'receipt_note_question': 'ඔබට පරිපාලකයා සඳහා සටහනක් එක් කිරීමට අවශ්‍යද, නැතහොත් දැන් ඔබේ ඇණවුම යැවීමට අවශ්‍යද?',
        'order_creating': '⏳ ඔබගේ ඇණවුම නිර්මාණය කරමින්...',
        'order_created': '✅ <b>ඇණවුම සෙවනැලින් නිර්මාණය කරන ලදී!</b>',
        'order_details': 'ඔබගේ ඇණවුම දැන් පරිපාලක අනුමતිය සඳහා අපේක්ෂා කරමින් පවතී. ඔබගේ ගිණුම සූදානම් වූ පසු ඔබ දැනුම් දෙනු ඇත.',
        'order_id': 'ඇණවුම් අංකය',        'data': 'දත්ත',
        'back_to_v2ray_package': '🔙 V2Ray පැකේජ වෙත ආපසු',
        'location_not_found': '❌ ස්ථානය හමු නොවීය',
        'payment_method_not_found': '❌ ගෙවීම් ක්‍රමය හමු නොවීය',
        'valid_name_required': '❌ කරුණාකර වලංගු නමක් ඇතුළත් කරන්න.',
        'receipt_photo_or_document_required': '❌ කරුණාකර ඔබගේ ගෙවීම් රිසිට් සඳහා photo එකක් හෝ document එකක් යවන්න',
        'receipt_unsupported_format': '❌ සහාය නොදක්වන රිසිට් ආකෘතිය. කරුණාකර photo එකක් හෝ PDF/JPG/PNG document එකක් යවන්න.',        'total_price': 'මුළු මිල',
        'waiting_approval': 'තත්ත්වය: ⏳ අනුමතිය සඳහා පොරොත්තු',
        'order_cancelled': '❌ ඇණවුම අවලංගු කරන ලදී.',
        'start_over': 'ඔබ නැවත ආරම්භ කිරීමට අවශ්‍ය ද?',
        
        # Admin
        'admin_auth': '🔐 පරිපාලක සත්‍යතා',
        'enter_password': 'කරුණාකර පරිපාලක මුරපදය ඇතුළු කරන්න:',
        'invalid_password': '❌ අනීතිමත් මුරපදය!',
        'pending_orders': '📋 අපේක්ෂා කරන ඇණවුම්',
        'no_pending_orders': '✅ අපේක්ෂා කරන ඇණවුම් නොමැත',
        'approve': '✅ අනුමත කරන්න',
        'reject': '❌ ප්‍රතික්ෂේප කරන්න',
        'order_number': 'ඇණවුම් #{order_id}',
        'from': 'සිට',
        'package_info': 'පැකේජ',
        'location': 'ස්ථානය',
        'price': 'මිල',
        'status': 'තත්ත්වය',
        'pending': '⏳ අපේක්ෂා කරමින්',
        'approved': '✅ අනුමත කරන ලදී',
        'rejected': '❌ ප්‍රතික්ෂේප කරන ලදී',
        'processing': '🔄 සකසමින්',
        'account_created': '✅ ගිණුම නිර්මාණය සිදුව ඇත',
        'orders_statistics': '📊 ඇණවුම් සංඛ්‍යාලේඛන',
        'total_orders': 'සම්පූර්ණ ඇණවුම්',
        'approved_count': 'අනුමත කරන ලදී',
        'pending_count': 'අපේක්ෂා කරමින්',
        'rejected_count': 'ප්‍රතික්ෂේප කරන ලදී',
        
        # Retry after rejection
        'retry': '🔄 නැවත උත්සාහ කරන්න',
        'contact_support': '📞 සහාය සම්බන්ධ කරන්න',
        'rejection_reason': 'ප්‍රතික්ෂේපයේ හැකි හේතු',
        'invalid_receipt': 'අවලංගු හෝ පැහැදිලි නොවන ගෙවීම් රිසිට්',
        'insufficient_payment': 'ප්‍රමාණවත් නොවන ගෙවීමේ මුදල',
        'unclear_details': 'පැහැදිලි නොවන ගනුදෙනු විස්තර',
        'retry_instructions': 'කරුණාකර තවත් පැහැදිලි රිසිට් එකක් හෝ අමතර විස්තර එක් කර නැවත උත්සාහ කරන්න.',
        'retry_new_receipt': 'නව ගෙවීම් රිසිට් උඩුගත කරන්න',
        'retry_instructions_detail': 'කරුණාකර ඔබගේ ගෙවීම් රිසිට් එක පැහැදිලි ඡායාරූපයක් හෝ ලේඛනයක් ලෙස උඩුගත කරන්න. සියලු විස්තර පැහැදිලිව පෙනිය යුතුය.',
        'cancel': '❌ අවලංගු කරන්න',
        'note_saved': '✅ සටහන සුරකිණ්ණ ලදී!',
        'your_note': 'ඔබේ සටහන',
        'order_submitted': '✅ සමාලෝචනය සඳහා ඇණවුම ඉදිරිපත් කරන ලදී!',
        'thank_you_retry': 'ඔබේ ඇණවුම නැවත ඉදිරිපත් කිරීම සඳහා ස්තුතියි. පරිපාලකයා ඉක්මනින් එය සමාලෝචනය කරනු ඇත.',
        'approve': '✅ අනුමත කරන්න',
        'reject': '❌ ප්‍රතික්ෂේප කරන්න',
        
        # Errors
        'not_authorized': '❌ ඔබට මෙම විධානය භාවිතා කිරීමට අධිකාරය නැත.',
        'isp_not_found': '❌ ISP සොයා ගත නොහැක',
        'package_not_found': '❌ පැකේජ සොයා ගත නොහැක',
        'no_packages_available': '❌ {name} සඳහා පැකේජ නොමැත.\nකරුණාකර පරිපාලකයා සම්බන්ධ කරන්න.',
        'error_occurred': '❌ දෝෂයක් ඇති විය. කරුණාකර නැවත උත්සාහ කරන්න.',
        'not_admin': '❌ මෙම විධානය අධිකරණ අධිකාරීන් සඳහා පමණි.',
        
        # Success
        'success': '✅ සෙවනැලින්',
        'saved': '✅ සෙවනැලින් සුරකිණ්ණ ලදී',
    }
}

def get_text(language: str, key: str, **kwargs) -> str:
    """
    Get translated text for a key in the specified language
    
    Args:
        language: Language code ('en' or 'si')
        key: Translation key
        **kwargs: Parameters to format the text
    
    Returns:
        Translated text with parameters filled
    """
    lang_dict = TRANSLATIONS.get(language, TRANSLATIONS['en'])
    text = lang_dict.get(key, TRANSLATIONS['en'].get(key, f'[{key}]'))
    
    return _safe_format_text(text, **kwargs)
