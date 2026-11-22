"""WhatsApp Business Cloud API provider (official Meta Graph API).

Scope: inbound text messages via webhook and outbound text replies. Posting,
OAuth and profile fetching do not apply to WhatsApp and are not implemented.

Credentials (PlatformCredential.credentials or .env):
    access_token   Permanent system-user token with whatsapp_business_messaging
    app_secret     Meta app secret, used to verify X-Hub-Signature-256
    verify_token   Token echoed back during the webhook subscription handshake

The SocialAccount for a WhatsApp number uses ``account_platform_id`` =
phone_number_id (the sender id of outbound messages).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .base import SocialProvider
from .exceptions import APIError, ProviderError
from .types import AccountProfile, AuthType, InboxMessage, MediaType, PostType, PublishContent, RateLimitConfig, ReplyResult

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
REQUEST_TIMEOUT = 30.0

# WhatsApp text messages are capped at 4096 characters.
MAX_TEXT_LENGTH = 4096


def parse_inbound_messages(value: dict) -> list[InboxMessage]:
    """Turn one ``value`` block from a WhatsApp webhook change into InboxMessages.

    Only ``type == "text"`` is mapped to text. Other message types are kept with
    an empty text and their type in ``extra`` so the inbox can still show them.
    """
    contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", [])}
    messages: list[InboxMessage] = []
    for msg in value.get("messages", []):
        message_id = msg.get("id")
        sender = msg.get("from")
        if not message_id or not sender:
            continue
        mtype = msg.get("type", "")
        text = ""
        if mtype == "text":
            text = (msg.get("text") or {}).get("body", "")
        try:
            ts = datetime.fromtimestamp(int(msg.get("timestamp", 0)), tz=UTC)
        except (TypeError, ValueError, OSError):
            ts = datetime.now(UTC)
        messages.append(
            InboxMessage(
                platform_message_id=message_id,
                sender_id=sender,
                sender_name=contacts.get(sender) or sender,
                text=text,
                timestamp=ts,
                message_type="dm",
                extra={"wa_type": mtype, "phone_number_id": (value.get("metadata") or {}).get("phone_number_id", "")},
            )
        )
    return messages


class WhatsAppProvider(SocialProvider):
    @property
    def platform_name(self) -> str:
        return "whatsapp"

    @property
    def auth_type(self) -> AuthType:
        # The system-user token is configured, not obtained through OAuth per user.
        return AuthType.INSTANCE_OAUTH

    @property
    def max_caption_length(self) -> int:
        return MAX_TEXT_LENGTH

    @property
    def supported_post_types(self) -> list[PostType]:
        return []

    @property
    def supported_media_types(self) -> list[MediaType]:
        return []

    @property
    def required_scopes(self) -> list[str]:
        return ["whatsapp_business_messaging"]

    @property
    def rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(requests_per_hour=1000, requests_per_day=10000, publish_per_day=0)

    def get_profile(self, access_token: str, phone_number_id: str = "") -> AccountProfile:
        """Verify a WhatsApp Business phone number and return its profile.

        ``access_token`` is the system-user token and ``phone_number_id`` the
        number to check. A successful Graph call proves the token can send from
        that number, which is what the connect step needs to confirm before it
        creates the account.
        """
        if not phone_number_id:
            raise ProviderError("WhatsApp needs a Phone Number ID.")
        data = self._get_json(
            f"{GRAPH_BASE}/{phone_number_id}",
            access_token,
            params={"fields": "id,display_phone_number,verified_name"},
        )
        display = (data.get("display_phone_number") or "").strip()
        name = (data.get("verified_name") or "").strip() or display or phone_number_id
        return AccountProfile(
            platform_id=str(data.get("id") or phone_number_id),
            name=name,
            handle=display or None,
            extra={"phone_number_id": str(data.get("id") or phone_number_id)},
        )

    def publish_post(self, access_token: str, content: PublishContent):
        raise ProviderError("WhatsApp does not support publishing posts; use the inbox to reply.")

    def get_messages(self, access_token: str, since=None) -> list[InboxMessage]:
        # Inbound messages arrive by webhook (apps.inbox.webhooks), not by polling.
        return []

    def reply_to_message(
        self,
        access_token: str,
        message_id: str,
        text: str,
        extra: dict | None = None,
        *,
        human_agent: bool = False,
    ) -> ReplyResult:
        """Send a text reply to ``extra["recipient_id"]`` from ``extra["phone_number_id"]``.

        ``message_id`` is the inbound WhatsApp message id; it is sent as the
        reply context so the customer sees the message being answered.
        """
        extra = extra or {}
        phone_number_id = extra.get("phone_number_id")
        recipient = extra.get("recipient_id") or extra.get("sender_id")
        if not phone_number_id or not recipient:
            raise ProviderError("WhatsApp reply needs phone_number_id and recipient_id.")
        if not text or not text.strip():
            raise ProviderError("WhatsApp reply text is empty.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ProviderError(f"WhatsApp text is limited to {MAX_TEXT_LENGTH} characters.")

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        if message_id:
            payload["context"] = {"message_id": message_id}

        data = self._post_json(f"{GRAPH_BASE}/{phone_number_id}/messages", access_token, payload)
        messages = data.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise APIError("WhatsApp accepted the request but returned no message id.", platform="whatsapp")
        return ReplyResult(platform_message_id=messages[0]["id"], extra={"raw": data})

    def reply_to_comment(self, access_token: str, comment_id: str, text: str, extra: dict | None = None) -> ReplyResult:
        raise ProviderError("WhatsApp has no comments; use reply_to_message.")

    def _get_json(self, url: str, access_token: str, params: dict | None = None) -> dict:
        import httpx

        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise APIError(f"WhatsApp request failed: {exc.__class__.__name__}", platform="whatsapp") from exc
        if resp.status_code >= 400:
            try:
                err = (resp.json().get("error") or {}).get("message", "")
            except ValueError:
                err = ""
            transient = resp.status_code >= 500 or resp.status_code == 429
            raise APIError(
                f"WhatsApp rejected the request ({resp.status_code}). {err}".strip(),
                status_code=resp.status_code,
                platform="whatsapp",
                retryable=transient,
            )
        return resp.json()

    def _post_json(self, url: str, access_token: str, payload: dict) -> dict:
        import httpx

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise APIError(f"WhatsApp request failed: {exc.__class__.__name__}", platform="whatsapp") from exc
        if resp.status_code >= 400:
            # Graph errors carry internal diagnostics (fbtrace_id); keep only the message.
            try:
                err = (resp.json().get("error") or {}).get("message", "")
            except ValueError:
                err = ""
            # 4xx means the request itself is wrong (bad recipient, outside the
            # 24h window, bad token). Retrying cannot fix it, so fail permanently.
            # 5xx and 429 are transient and stay retryable.
            transient = resp.status_code >= 500 or resp.status_code == 429
            raise APIError(
                f"WhatsApp rejected the message ({resp.status_code}). {err}".strip(),
                status_code=resp.status_code,
                platform="whatsapp",
                retryable=transient,
            )
        return resp.json()
