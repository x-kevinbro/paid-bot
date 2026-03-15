"""
Stripe Payment Integration for V2Ray Bot
Handles automated payment processing and verification
"""

import stripe
import os
import logging
from typing import Optional, Dict
from datetime import datetime
from firebase_db import load_config, save_config

logger = logging.getLogger(__name__)

# Initialize Stripe
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
    logger.info("✅ Stripe payment gateway initialized")
else:
    logger.warning("⚠️ STRIPE_SECRET_KEY not set - Stripe payments disabled")


def is_stripe_enabled() -> bool:
    """Check if Stripe is configured and enabled"""
    config = load_config()
    return (
        STRIPE_SECRET_KEY is not None 
        and config.get('stripe_enabled', False)
    )


async def create_payment_link(
    order_id: str,
    amount: float,
    currency: str,
    description: str,
    customer_email: str = None,
    metadata: dict = None
) -> Optional[Dict]:
    """
    Create a Stripe payment link for an order
    
    Args:
        order_id: Unique order ID
        amount: Amount in the currency's smallest unit (e.g., cents for USD, paisa for LKR)
        currency: Currency code (e.g., 'lkr', 'usd')
        description: Payment description
        customer_email: Customer email (optional)
        metadata: Additional metadata to attach to payment
    
    Returns:
        Dict with payment_url, session_id, or None if failed
    """
    if not is_stripe_enabled():
        logger.error("Stripe is not enabled")
        return None
    
    try:
        # Convert to smallest currency unit (LKR doesn't use decimals, so multiply by 1)
        # For USD/EUR, you'd multiply by 100
        if currency.lower() == 'lkr':
            amount_smallest = int(amount)  # LKR doesn't have subunits
        else:
            amount_smallest = int(amount * 100)  # For USD, EUR, etc.
        
        # Prepare metadata
        payment_metadata = {
            'order_id': order_id,
            'source': 'v2ray_bot',
            **(metadata or {})
        }
        
        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': currency.lower(),
                    'unit_amount': amount_smallest,
                    'product_data': {
                        'name': 'V2Ray Account',
                        'description': description,
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{os.getenv('BOT_WEBHOOK_URL', 'https://example.com')}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{os.getenv('BOT_WEBHOOK_URL', 'https://example.com')}/payment/cancel?session_id={{CHECKOUT_SESSION_ID}}",
            customer_email=customer_email,
            metadata=payment_metadata,
            expires_at=int(datetime.now().timestamp()) + 3600,  # Expires in 1 hour
        )
        
        # Store session in config for tracking
        config = load_config()
        stripe_sessions = config.get('stripe_sessions', {})
        stripe_sessions[session.id] = {
            'order_id': order_id,
            'amount': amount,
            'currency': currency,
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }
        config['stripe_sessions'] = stripe_sessions
        save_config(config)
        
        logger.info(f"✅ Created Stripe payment session {session.id} for order {order_id}")
        
        return {
            'payment_url': session.url,
            'session_id': session.id,
            'expires_at': session.expires_at
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error creating payment: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error creating Stripe payment: {e}")
        return None


async def verify_payment(session_id: str) -> Optional[Dict]:
    """
    Verify a Stripe payment by session ID
    
    Returns:
        Dict with payment details if verified, None otherwise
    """
    if not is_stripe_enabled():
        return None
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == 'paid':
            # Update local tracking
            config = load_config()
            stripe_sessions = config.get('stripe_sessions', {})
            
            if session_id in stripe_sessions:
                stripe_sessions[session_id]['status'] = 'paid'
                stripe_sessions[session_id]['paid_at'] = datetime.now().isoformat()
                config['stripe_sessions'] = stripe_sessions
                save_config(config)
            
            return {
                'verified': True,
                'order_id': session.metadata.get('order_id'),
                'amount_paid': session.amount_total / 100 if session.currency != 'lkr' else session.amount_total,
                'currency': session.currency.upper(),
                'payment_intent': session.payment_intent,
                'customer_email': session.customer_email,
                'paid_at': datetime.fromtimestamp(session.created).isoformat()
            }
        else:
            return {
                'verified': False,
                'status': session.payment_status,
                'order_id': session.metadata.get('order_id')
            }
            
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error verifying payment: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error verifying Stripe payment: {e}")
        return None


def handle_webhook(payload: bytes, signature: str) -> Optional[Dict]:
    """
    Handle Stripe webhook events for automatic payment verification
    
    Args:
        payload: Raw webhook payload
        signature: Stripe signature header
    
    Returns:
        Dict with event details if valid, None otherwise
    """
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("Stripe webhook secret not configured")
        return None
    
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET
        )
        
        logger.info(f"📨 Received Stripe webhook: {event['type']}")
        
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            
            if session.payment_status == 'paid':
                order_id = session.metadata.get('order_id')
                
                # Update order status in config
                config = load_config()
                pending = config.get('pending_approvals', [])
                
                for order in pending:
                    if order.get('order_id') == order_id:
                        order['stripe_verified'] = True
                        order['stripe_session_id'] = session.id
                        order['stripe_payment_intent'] = session.payment_intent
                        order['payment_verified_at'] = datetime.now().isoformat()
                        logger.info(f"✅ Auto-verified payment for order {order_id}")
                        break
                
                config['pending_approvals'] = pending
                save_config(config)
                
                return {
                    'event': 'payment_verified',
                    'order_id': order_id,
                    'session_id': session.id,
                    'amount': session.amount_total
                }
        
        return {'event': event['type'], 'processed': True}
        
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"❌ Invalid Stripe webhook signature: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error handling Stripe webhook: {e}")
        return None


async def create_refund(payment_intent_id: str, amount: Optional[float] = None, reason: str = None) -> bool:
    """
    Create a refund for a payment
    
    Args:
        payment_intent_id: Stripe payment intent ID
        amount: Amount to refund (optional, full refund if None)
        reason: Refund reason
    
    Returns:
        True if refund created, False otherwise
    """
    if not is_stripe_enabled():
        return False
    
    try:
        refund_data = {
            'payment_intent': payment_intent_id,
        }
        
        if amount:
            refund_data['amount'] = int(amount * 100)  # Convert to cents
        
        if reason:
            refund_data['reason'] = reason
        
        refund = stripe.Refund.create(**refund_data)
        
        logger.info(f"✅ Created refund {refund.id} for payment {payment_intent_id}")
        return True
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error creating refund: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error creating refund: {e}")
        return False


async def get_payment_status(session_id: str) -> str:
    """Get current status of a payment session"""
    if not is_stripe_enabled():
        return 'unavailable'
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status
    except:
        return 'unknown'
