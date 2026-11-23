"""Public legal pages: reachable, complete, and never rewritten by the UI translator."""

import pytest
from django.urls import reverse

PAGES = [
    ("legal:terms", "Terms of Service", "Agreement to These Terms"),
    ("legal:privacy", "Privacy Policy", "Data We Collect"),
    ("legal:acceptable_use", "Acceptable Use Policy", "Prohibited Conduct"),
    ("legal:cookies", "Cookie Policy", "Cookies We Use"),
]


def test_index_serves_terms(client):
    response = client.get("/legal/")
    assert response.status_code == 200
    assert "Terms of Service" in response.content.decode()


@pytest.mark.parametrize("url_name,title,marker", PAGES)
def test_page_renders_with_title_and_body(client, url_name, title, marker):
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    body = response.content.decode()
    assert title in body
    assert marker in body


@pytest.mark.parametrize("url_name,title,marker", PAGES)
def test_page_requires_no_login(client, url_name, title, marker):
    """Signup and reset flows send anonymous visitors here, so no auth wall."""
    assert client.get(reverse(url_name)).status_code == 200


@pytest.mark.parametrize("url_name,title,marker", PAGES)
def test_entity_details_come_from_settings(client, settings, url_name, title, marker):
    settings.BRAND_NAME = "TestBrand"
    settings.LEGAL_ENTITY_NAME = "Test Entity Ltd"
    settings.LEGAL_CONTACT_EMAIL = "legal@example.test"
    settings.LEGAL_JURISDICTION = "Testland"
    settings.LEGAL_EFFECTIVE_DATE = "1 January 2026"

    body = client.get(reverse(url_name)).content.decode()
    assert "Test Entity Ltd" in body
    assert "legal@example.test" in body
    assert "1 January 2026" in body


@pytest.mark.parametrize("url_name,title,marker", PAGES)
def test_stays_english_when_ui_is_chinese(client, url_name, title, marker):
    """The zh dictionary must not rewrite binding contract text.

    The default UI language is Chinese, so without the /legal/ exemption the
    middleware would replace words like "Terms of Service" with Chinese and the
    quoted clause would no longer match the English original.
    """
    client.cookies["ui_lang"] = "zh"
    body = client.get(reverse(url_name)).content.decode()
    assert "This document is provided in English only." in body
    assert marker in body


def test_every_page_is_linked_from_every_page(client):
    for source, _, _ in PAGES:
        body = client.get(reverse(source)).content.decode()
        for target, title, _ in PAGES:
            assert reverse(target) in body, f"{target} missing from {source}"
            assert title in body


def test_accept_terms_links_to_legal_pages(client, db):
    """A user who has not yet accepted is shown the page with real links, not bare text."""
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    user = get_user_model().objects.create_user(
        email="terms@example.com", password="testpass123", name="Terms User", tos_accepted_at=None
    )
    client.force_login(user)

    response = client.get(reverse("accounts:accept_terms"))
    assert response.status_code == 200
    body = response.content.decode()
    assert reverse("legal:terms") in body
    assert reverse("legal:privacy") in body


def test_signup_template_links_to_legal_pages():
    """Registration can be closed per deployment, so assert on the template itself."""
    from pathlib import Path

    from django.conf import settings

    html = (Path(settings.BASE_DIR) / "templates/account/signup.html").read_text(encoding="utf-8")
    assert "legal:terms" in html
    assert "legal:privacy" in html


def test_banner_warns_while_details_are_placeholders(client, settings):
    settings.LEGAL_ENTITY_NAME = "[OPERATING ENTITY — TO BE COMPLETED]"
    settings.LEGAL_CONTACT_EMAIL = "[CONTACT EMAIL — TO BE COMPLETED]"
    settings.LEGAL_EFFECTIVE_DATE = "[EFFECTIVE DATE — TO BE COMPLETED]"

    body = client.get(reverse("legal:terms")).content.decode()
    assert "Not ready to publish." in body


def test_banner_disappears_once_details_are_real(client, settings):
    settings.LEGAL_ENTITY_NAME = "Real Entity Ltd"
    settings.LEGAL_CONTACT_EMAIL = "legal@real.test"
    settings.LEGAL_EFFECTIVE_DATE = "1 January 2026"

    body = client.get(reverse("legal:terms")).content.decode()
    assert "Not ready to publish." not in body
    assert "Real Entity Ltd" in body


def test_banner_appears_if_only_the_contact_is_missing(client, settings):
    settings.LEGAL_ENTITY_NAME = "Real Entity Ltd"
    settings.LEGAL_CONTACT_EMAIL = ""
    settings.LEGAL_EFFECTIVE_DATE = "1 January 2026"

    assert "Not ready to publish." in client.get(reverse("legal:privacy")).content.decode()
