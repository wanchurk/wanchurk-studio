"""Tests for the WhatsApp Cloud API webhook and provider."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.test import override_settings
from django.urls import reverse

from apps.inbox.models import InboxMessage
from apps.social_accounts.models import SocialAccount
from providers.exceptions import APIError, ProviderError
from providers.whatsapp import WhatsAppProvider, parse_inbound_messages

PHONE_ID = "1055550001"
SECRET = "wa-app-secret"


@pytest.fixture
def workspace(db, organization):
    from apps.workspaces.models import Workspace

    return Workspace.objects.create(name="WA WS", organization=organization)


@pytest.fixture
def wa_account(db, workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="whatsapp",
        account_platform_id=PHONE_ID,
        account_name="WA Support",
        connection_status=SocialAccount.ConnectionStatus.CONNECTED,
    )


def _payload(message_id="wamid.A", text="hi", sender="8613800000000", phone_id=PHONE_ID, msg_type="text"):
    msg = {"from": sender, "id": message_id, "timestamp": "1767225600", "type": msg_type}
    if msg_type == "text":
        msg["text"] = {"body": text}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "x", "phone_number_id": phone_id},
                            "contacts": [{"profile": {"name": "Alice"}, "wa_id": sender}],
                            "messages": [msg],
                        },
                    }
                ],
            }
        ],
    }


def _post(client, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        reverse("inbox_webhooks:webhook_whatsapp"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
    )


@pytest.mark.django_db
class TestWhatsAppWebhookVerify:
    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN="wa-token")
    def test_correct_token_echoes_challenge(self, client):
        r = client.get(
            reverse("inbox_webhooks:webhook_whatsapp"),
            {"hub.mode": "subscribe", "hub.verify_token": "wa-token", "hub.challenge": "chal"},
        )
        assert r.status_code == 200
        assert r.content == b"chal"

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN="wa-token")
    def test_wrong_token_is_rejected(self, client):
        r = client.get(
            reverse("inbox_webhooks:webhook_whatsapp"),
            {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "chal"},
        )
        assert r.status_code == 403

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN="")
    def test_unconfigured_verify_token_is_rejected(self, client):
        r = client.get(
            reverse("inbox_webhooks:webhook_whatsapp"),
            {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "chal"},
        )
        assert r.status_code == 403


@pytest.mark.django_db
class TestWhatsAppWebhookReceive:
    @override_settings(PLATFORM_CREDENTIALS_FROM_ENV={"whatsapp": {"app_secret": SECRET}})
    def test_signed_text_message_creates_dm(self, client, wa_account):
        r = _post(client, _payload(text="Is it in stock?"))
        assert r.status_code == 200
        msg = InboxMessage.objects.get(platform_message_id="wamid.A")
        assert msg.message_type == InboxMessage.MessageType.DM
        assert msg.body == "Is it in stock?"
        assert msg.sender_name == "Alice"
        assert msg.social_account_id == wa_account.id

    @override_settings(PLATFORM_CREDENTIALS_FROM_ENV={"whatsapp": {"app_secret": SECRET}})
    def test_bad_signature_is_rejected_and_writes_nothing(self, client, wa_account):
        r = _post(client, _payload(), secret="forged")
        assert r.status_code == 403
        assert not InboxMessage.objects.filter(platform_message_id="wamid.A").exists()

    @override_settings(PLATFORM_CREDENTIALS_FROM_ENV={"whatsapp": {"app_secret": SECRET}})
    def test_duplicate_delivery_is_idempotent(self, client, wa_account):
        _post(client, _payload(message_id="wamid.DUP"))
        _post(client, _payload(message_id="wamid.DUP"))
        assert InboxMessage.objects.filter(platform_message_id="wamid.DUP").count() == 1

    @override_settings(PLATFORM_CREDENTIALS_FROM_ENV={"whatsapp": {"app_secret": SECRET}})
    def test_unknown_phone_number_creates_nothing(self, client, wa_account):
        r = _post(client, _payload(message_id="wamid.X", phone_id="9999"))
        assert r.status_code == 200
        assert not InboxMessage.objects.filter(platform_message_id="wamid.X").exists()

    @override_settings(PLATFORM_CREDENTIALS_FROM_ENV={"whatsapp": {"app_secret": SECRET}})
    def test_status_only_payload_creates_nothing(self, client, wa_account):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": PHONE_ID},
                                "statuses": [{"id": "wamid.S", "status": "delivered"}],
                            },
                        }
                    ]
                }
            ]
        }
        r = _post(client, payload)
        assert r.status_code == 200
        assert not InboxMessage.objects.filter(platform_message_id="wamid.S").exists()

    def test_other_orgs_secret_cannot_write_into_this_org(self, client, wa_account, db):
        """Org B signs a delivery for a number that belongs to org A.

        Org A's account must reject it even though org B's secret is valid
        for *some* org. This uses real per-org credentials, not mocks, so it
        fails if the per-account org binding is removed.
        """
        from apps.credentials.models import PlatformCredential
        from apps.organizations.models import Organization

        org_b = Organization.objects.create(name="Org B")
        b_secret = "org-b-secret"
        # Org A (the account's org) has SECRET; org B has its own, different secret.
        PlatformCredential.objects.create(
            organization=wa_account.workspace.organization,
            platform="whatsapp",
            credentials={"app_secret": SECRET, "access_token": "a", "verify_token": "a"},
        )
        PlatformCredential.objects.create(
            organization=org_b,
            platform="whatsapp",
            credentials={"app_secret": b_secret, "access_token": "b", "verify_token": "b"},
        )
        r = _post(client, _payload(message_id="wamid.CROSS"), secret=b_secret)
        assert r.status_code == 200
        assert not InboxMessage.objects.filter(platform_message_id="wamid.CROSS").exists()


class TestParseInboundMessages:
    def test_text_message_maps_fields(self):
        value = {
            "contacts": [{"wa_id": "86138", "profile": {"name": "Bo"}}],
            "metadata": {"phone_number_id": PHONE_ID},
            "messages": [{"id": "m1", "from": "86138", "timestamp": "1767225600", "type": "text", "text": {"body": "yo"}}],
        }
        (msg,) = parse_inbound_messages(value)
        assert msg.platform_message_id == "m1"
        assert msg.sender_name == "Bo"
        assert msg.text == "yo"
        assert msg.extra["phone_number_id"] == PHONE_ID

    def test_non_text_message_keeps_empty_body(self):
        value = {"messages": [{"id": "m2", "from": "86138", "timestamp": "1", "type": "image"}]}
        (msg,) = parse_inbound_messages(value)
        assert msg.text == ""
        assert msg.extra["wa_type"] == "image"

    def test_message_without_id_is_skipped(self):
        assert parse_inbound_messages({"messages": [{"from": "86138", "type": "text"}]}) == []


class TestWhatsAppProviderSend:
    def _ok(self, message_id="wamid.OUT"):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"messages": [{"id": message_id}]}
        return resp

    def test_sends_text_with_context_and_returns_id(self):
        provider = WhatsAppProvider(credentials={})
        with patch("httpx.post", return_value=self._ok()) as post:
            result = provider.reply_to_message(
                "tok",
                "wamid.IN",
                "Yes, in stock.",
                extra={"phone_number_id": PHONE_ID, "recipient_id": "86138"},
            )
        assert result.platform_message_id == "wamid.OUT"
        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        assert url.endswith(f"/{PHONE_ID}/messages")
        assert body["to"] == "86138"
        assert body["type"] == "text"
        assert body["text"]["body"] == "Yes, in stock."
        assert body["context"] == {"message_id": "wamid.IN"}
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"

    def test_missing_recipient_fails_before_network(self):
        provider = WhatsAppProvider(credentials={})
        with patch("httpx.post") as post, pytest.raises(ProviderError):
            provider.reply_to_message("tok", "wamid.IN", "hi", extra={"phone_number_id": PHONE_ID})
        post.assert_not_called()

    def test_text_over_limit_fails_before_network(self):
        provider = WhatsAppProvider(credentials={})
        with patch("httpx.post") as post, pytest.raises(ProviderError):
            provider.reply_to_message(
                "tok", "wamid.IN", "x" * 4097, extra={"phone_number_id": PHONE_ID, "recipient_id": "86138"}
            )
        post.assert_not_called()

    def test_4xx_is_permanent_and_5xx_is_retryable(self):
        provider = WhatsAppProvider(credentials={})
        extra = {"phone_number_id": PHONE_ID, "recipient_id": "86138"}

        bad = MagicMock(status_code=400)
        bad.json.return_value = {"error": {"message": "Outside the 24h window", "fbtrace_id": "SECRET-TRACE"}}
        with patch("httpx.post", return_value=bad), pytest.raises(APIError) as e4:
            provider.reply_to_message("tok", "wamid.IN", "hi", extra=extra)
        assert e4.value.retryable is False
        assert "Outside the 24h window" in str(e4.value)
        assert "SECRET-TRACE" not in str(e4.value)

        boom = MagicMock(status_code=503)
        boom.json.return_value = {}
        with patch("httpx.post", return_value=boom), pytest.raises(APIError) as e5:
            provider.reply_to_message("tok", "wamid.IN", "hi", extra=extra)
        assert e5.value.retryable is True

    def test_network_error_is_wrapped_without_leaking_detail(self):
        provider = WhatsAppProvider(credentials={})
        with patch("httpx.post", side_effect=httpx.ConnectError("boom")), pytest.raises(APIError) as exc:
            provider.reply_to_message(
                "tok", "wamid.IN", "hi", extra={"phone_number_id": PHONE_ID, "recipient_id": "86138"}
            )
        assert "ConnectError" in str(exc.value)
