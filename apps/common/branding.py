"""Single source of truth for the product's display name.

The brand name comes from ``settings.BRAND_NAME`` (set per deployment; it
defaults to the shipped name). Email bodies and other no-request rendering
paths need it in their context, and it must never be hard-coded in a template
or string, so every such path calls ``resolve_brand_name()`` instead of the
literal.
"""

from django.conf import settings


def resolve_brand_name() -> str:
    """The product's display name for the current deployment.

    ``BRAND_NAME`` is normally the shipped name unless a deployment overrides
    it. An empty override means "not white-labelled", so fall back to the
    shipped name rather than rendering an empty brand.
    """
    return getattr(settings, "BRAND_NAME", "") or settings.SHIPPED_BRAND_NAME
