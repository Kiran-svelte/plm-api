"""
PLM Enterprise Notifications Service
Handles in-app notifications and webhook dispatching with HMAC signatures.
"""

import os
import hmac
import hashlib
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class NotificationService:
    """Creates in-app notifications and fires webhooks."""

    def __init__(self, db_client):
        self.db = db_client

    async def create_notification(
        self,
        org_id: str,
        user_id: Optional[str],
        notification_type: str,
        title: str,
        body: Optional[str] = None,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an in-app notification."""
        try:
            row = {
                "organization_id": org_id,
                "user_id": user_id,
                "type": notification_type,
                "title": title,
                "body": body,
                "read": False,
                "action_url": action_url,
                "metadata": metadata or {},
            }
            response = self.db.client.table("notifications").insert(row).execute()
            return response.data[0] if response.data else row
        except Exception as exc:
            logger.error(f"Failed to create notification: {exc}")
            return {}

    async def notify_org_users(
        self,
        org_id: str,
        notification_type: str,
        title: str,
        body: Optional[str] = None,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Send a notification to all users in an org. Returns count sent."""
        try:
            users_resp = self.db.client.table("users").select("id").eq("organization_id", org_id).execute()
            count = 0
            for user in (users_resp.data or []):
                await self.create_notification(
                    org_id=org_id,
                    user_id=user["id"],
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    action_url=action_url,
                    metadata=metadata,
                )
                count += 1
            return count
        except Exception as exc:
            logger.error(f"notify_org_users failed: {exc}")
            return 0

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch notifications for a user."""
        try:
            query = (
                self.db.client.table("notifications")
                .select("*")
                .eq("user_id", user_id)
            )
            if unread_only:
                query = query.eq("read", False)
            response = query.order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as exc:
            logger.error(f"get_notifications failed: {exc}")
            return []

    async def get_unread_count(self, user_id: str) -> int:
        """Return the number of unread notifications."""
        try:
            response = (
                self.db.client.table("notifications")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("read", False)
                .execute()
            )
            return response.count if response.count is not None else len(response.data or [])
        except Exception as exc:
            logger.error(f"get_unread_count failed: {exc}")
            return 0

    async def mark_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a single notification as read."""
        try:
            self.db.client.table("notifications").update(
                {"read": True}
            ).eq("id", notification_id).eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.error(f"mark_read failed: {exc}")
            return False

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        try:
            response = (
                self.db.client.table("notifications")
                .update({"read": True})
                .eq("user_id", user_id)
                .eq("read", False)
                .execute()
            )
            return len(response.data or [])
        except Exception as exc:
            logger.error(f"mark_all_read failed: {exc}")
            return 0

    # ----------------------------------------------------------------
    # Webhook dispatching
    # ----------------------------------------------------------------

    async def fire_webhooks(
        self,
        org_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> int:
        """Fire webhooks for an event. Returns count of successful deliveries."""
        try:
            hooks_resp = (
                self.db.client.table("webhooks")
                .select("*")
                .eq("organization_id", org_id)
                .eq("status", "active")
                .execute()
            )
            hooks = hooks_resp.data or []
            sent = 0
            for hook in hooks:
                if event_type not in (hook.get("events") or []):
                    continue
                try:
                    self._deliver_webhook(hook, event_type, payload)
                    sent += 1
                    # Reset failure count on success
                    self.db.client.table("webhooks").update({
                        "failure_count": 0,
                        "last_triggered_at": datetime.utcnow().isoformat(),
                    }).eq("id", hook["id"]).execute()
                except Exception as exc:
                    logger.warning(f"Webhook {hook['id']} delivery failed: {exc}")
                    failure_count = (hook.get("failure_count") or 0) + 1
                    updates: Dict[str, Any] = {"failure_count": failure_count}
                    # Auto-disable after 10 consecutive failures
                    if failure_count >= 10:
                        updates["status"] = "disabled"
                        logger.warning(f"Webhook {hook['id']} disabled after {failure_count} failures")
                    self.db.client.table("webhooks").update(updates).eq("id", hook["id"]).execute()
            return sent
        except Exception as exc:
            logger.error(f"fire_webhooks failed: {exc}")
            return 0

    @staticmethod
    def _deliver_webhook(hook: Dict[str, Any], event_type: str, payload: Dict[str, Any]) -> None:
        """Deliver a webhook with HMAC-SHA256 signature."""
        body = json.dumps({
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": payload,
        }, default=str)

        secret = hook.get("secret", "")
        signature = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-PLM-Signature": f"sha256={signature}",
            "X-PLM-Event": event_type,
        }

        resp = requests.post(hook["url"], data=body, headers=headers, timeout=10)
        resp.raise_for_status()


# ----------------------------------------------------------------
# Convenience: event helpers
# ----------------------------------------------------------------

async def notify_training_complete(
    db_client, org_id: str, model_name: str, job_id: str
) -> None:
    """Notify org users that training is done."""
    svc = NotificationService(db_client)
    await svc.notify_org_users(
        org_id=org_id,
        notification_type="training_complete",
        title="Training Complete",
        body=f"Model '{model_name}' has finished training.",
        action_url=f"/dashboard?tab=health",
        metadata={"job_id": job_id},
    )
    await svc.fire_webhooks(org_id, "training.completed", {
        "model_name": model_name, "job_id": job_id,
    })


async def notify_training_failed(
    db_client, org_id: str, model_name: str, job_id: str, error: str
) -> None:
    """Notify org users that training failed."""
    svc = NotificationService(db_client)
    await svc.notify_org_users(
        org_id=org_id,
        notification_type="training_failed",
        title="Training Failed",
        body=f"Model '{model_name}' training failed: {error[:200]}",
        action_url=f"/dashboard?tab=health",
        metadata={"job_id": job_id, "error": error[:500]},
    )
    await svc.fire_webhooks(org_id, "training.failed", {
        "model_name": model_name, "job_id": job_id, "error": error[:500],
    })


async def notify_usage_warning(
    db_client, org_id: str, user_id: str, usage_percent: float, tier: str
) -> None:
    """Warn a user about approaching usage limits."""
    svc = NotificationService(db_client)
    await svc.create_notification(
        org_id=org_id,
        user_id=user_id,
        notification_type="usage_warning",
        title="Approaching Usage Limit",
        body=f"You have used {usage_percent:.0f}% of your {tier} tier monthly quota.",
        action_url="/dashboard?tab=settings",
        metadata={"usage_percent": usage_percent, "tier": tier},
    )
