import uuid

from django.conf import settings
from django.db import models

from apps.common.managers import WorkspaceScopedModel


class SupportConversation(WorkspaceScopedModel):
    """A manually recorded buyer conversation. Never a social InboxMessage."""

    class Platform(models.TextChoices):
        TIKTOK_SHOP = "tiktok_shop", "TikTok Shop"
        AMAZON = "amazon", "Amazon"
        SHOPEE = "shopee", "Shopee"
        LAZADA = "lazada", "Lazada"
        TEMU = "temu", "Temu"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=24, choices=Platform.choices)
    shop_name = models.CharField(max_length=100)
    subject = models.CharField(max_length=140)
    buyer_alias = models.CharField(max_length=100, blank=True)
    order_reference = models.CharField(max_length=100, blank=True)
    body = models.TextField(max_length=6000)
    reply_draft = models.TextField(max_length=6000, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    revision = models.PositiveBigIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["workspace", "status", "-created_at"], name="commerce_inbox_status_idx")]
