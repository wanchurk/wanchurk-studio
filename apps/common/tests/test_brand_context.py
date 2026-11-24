"""The brand name reaches templates from settings, never from literal text.

Deployments re-brand this product through ``BRAND_NAME``. The zh translator
already rewrites visible occurrences of the shipped name, which masks the
problem in rendered HTML — a page that hard-codes the name still looks right
until the middleware is bypassed, or until the brand is rendered somewhere the
middleware does not reach (an email, a PDF, a title assembled in Python).

So these tests assert on the template context and on the template sources, not
on the rendered text.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

# A title is either the `<title>` element or the `title` block a page overrides.
TITLE_LINE = re.compile(r"(<title>|\{%\s*block title\s*%\})")


def _page_templates() -> list[Path]:
    """Templates rendered with a request, so a context processor can reach them.

    Email bodies render without a request object and therefore cannot use one.
    """
    root = Path(settings.BASE_DIR) / "templates"
    return [p for p in sorted(root.rglob("*.html")) if "/email/" not in str(p) and not p.name.startswith("email_")]


def test_context_processor_exposes_the_configured_brand(client, db, settings):
    settings.BRAND_NAME = "Acme Co"
    response = client.get(reverse("account_login"))
    assert response.context["brand_name"] == "Acme Co"


def test_falls_back_to_the_shipped_name_when_unbranded(client, db, settings):
    """BRAND_NAME="" means "no white-label override", not "render nothing"."""
    settings.BRAND_NAME = ""
    response = client.get(reverse("account_login"))
    assert response.context["brand_name"] == settings.SHIPPED_BRAND_NAME


def test_the_brand_is_available_without_authentication(client, db, settings):
    """Login and password-reset pages are the ones an anonymous visitor sees."""
    settings.BRAND_NAME = "Acme Co"
    for url_name in ("account_login", "account_reset_password"):
        assert client.get(reverse(url_name)).context["brand_name"] == "Acme Co"


@pytest.mark.parametrize("path", [str(p) for p in _page_templates()], ids=lambda p: Path(p).name)
def test_no_page_title_hard_codes_the_shipped_brand(path, settings):
    offenders = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if TITLE_LINE.search(line) and settings.SHIPPED_BRAND_NAME in line:
            offenders.append(f"{Path(path).name}:{number}: {line.strip()[:90]}")
    assert not offenders, "hard-coded brand in a page title:\n" + "\n".join(offenders)


def test_the_default_title_uses_the_brand_variable():
    base = (Path(settings.BASE_DIR) / "templates/base.html").read_text(encoding="utf-8")
    assert "{{ brand_name }}" in base.split("</title>")[0]
