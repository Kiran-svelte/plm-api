"""
PLM Enterprise Billing - Stripe Integration
Handles pricing tiers, checkout, usage tracking, and webhooks
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER", "")
STRIPE_PRICE_PROFESSIONAL = os.getenv("STRIPE_PRICE_PROFESSIONAL", "")
STRIPE_PRICE_ENTERPRISE = os.getenv("STRIPE_PRICE_ENTERPRISE", "")

# Tier limits
TIER_LIMITS = {
    "starter": {
        "queries_per_month": 1000,
        "models": 1,
        "knowledge_entries": 500,
        "users": 3,
        "price": 49,
    },
    "professional": {
        "queries_per_month": 10000,
        "models": 5,
        "knowledge_entries": 5000,
        "users": 10,
        "price": 199,
    },
    "enterprise": {
        "queries_per_month": 100000,
        "models": 20,
        "knowledge_entries": 50000,
        "users": 50,
        "price": 499,
    },
}


class BillingManager:
    """Manages Stripe billing for PLM Enterprise"""

    def __init__(self):
        self.stripe = None
        if STRIPE_SECRET_KEY:
            try:
                import stripe

                stripe.api_key = STRIPE_SECRET_KEY
                self.stripe = stripe
                logger.info("Stripe billing initialized")
            except ImportError:
                logger.warning("stripe package not installed - billing disabled")
        else:
            logger.warning("STRIPE_SECRET_KEY not set - billing disabled")

    @property
    def is_configured(self) -> bool:
        return self.stripe is not None

    async def create_checkout_session(
        self,
        org_id: str,
        tier: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session for a pricing tier"""
        if not self.is_configured:
            return {"error": "Billing not configured", "url": None}

        price_map = {
            "starter": STRIPE_PRICE_STARTER,
            "professional": STRIPE_PRICE_PROFESSIONAL,
            "enterprise": STRIPE_PRICE_ENTERPRISE,
        }

        price_id = price_map.get(tier)
        if not price_id:
            return {"error": f"Unknown tier: {tier}", "url": None}

        try:
            session = self.stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"org_id": org_id, "tier": tier},
            )
            return {"url": session.url, "session_id": session.id}
        except Exception as e:
            logger.error(f"Checkout session creation failed: {e}")
            return {"error": str(e), "url": None}

    async def handle_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Handle Stripe webhook events"""
        if not self.is_configured:
            return {"error": "Billing not configured"}

        try:
            event = self.stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            logger.error(f"Webhook verification failed: {e}")
            return {"error": str(e)}

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            org_id = session["metadata"].get("org_id")
            tier = session["metadata"].get("tier")
            logger.info(f"Payment completed for org {org_id}, tier: {tier}")
            return {
                "action": "activate_tier",
                "org_id": org_id,
                "tier": tier,
                "subscription_id": session.get("subscription"),
            }

        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            logger.info(f"Subscription cancelled: {subscription['id']}")
            return {
                "action": "deactivate_subscription",
                "subscription_id": subscription["id"],
            }

        elif event["type"] == "invoice.payment_failed":
            invoice = event["data"]["object"]
            logger.warning(f"Payment failed for invoice: {invoice['id']}")
            return {
                "action": "payment_failed",
                "invoice_id": invoice["id"],
            }

        return {"action": "ignored", "type": event["type"]}

    def get_tier_limits(self, tier: str) -> Dict[str, Any]:
        """Get usage limits for a tier"""
        return TIER_LIMITS.get(tier, TIER_LIMITS["starter"])

    async def check_usage(
        self, org_id: str, tier: str, current_queries: int
    ) -> Dict[str, Any]:
        """Check if organization is within usage limits"""
        limits = self.get_tier_limits(tier)
        queries_limit = limits["queries_per_month"]
        return {
            "within_limits": current_queries < queries_limit if queries_limit > 0 else False,
            "queries_used": current_queries,
            "queries_limit": queries_limit,
            "usage_percent": round(
                (current_queries / queries_limit) * 100, 1
            ) if queries_limit > 0 else 0.0,
        }


# Singleton
_billing_manager: Optional[BillingManager] = None


def get_billing_manager() -> BillingManager:
    global _billing_manager
    if _billing_manager is None:
        _billing_manager = BillingManager()
    return _billing_manager
