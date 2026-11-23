"""Public legal pages.

These pages stay English even when the UI language is Chinese: binding contract
text must not be rewritten by the UI translator, so ``apps.ui_zh`` skips every
path under ``/legal/``. Entity details come from settings so a single deployment
can be re-branded without editing the templates.
"""

from django.conf import settings
from django.shortcuts import render

#: Tabs across the top of every page, and the footer links.
LEGAL_PAGES = (
    ("legal:terms", "Terms of Service"),
    ("legal:privacy", "Privacy Policy"),
    ("legal:acceptable_use", "Acceptable Use Policy"),
    ("legal:cookies", "Cookie Policy"),
)


def _unconfigured() -> bool:
    """True while the entity details are still the shipped placeholders."""
    return any(
        not value or value.startswith("[")
        for value in (settings.LEGAL_ENTITY_NAME, settings.LEGAL_CONTACT_EMAIL, settings.LEGAL_EFFECTIVE_DATE)
    )


def _context(current_page: str) -> dict:
    return {
        "current_page": current_page,
        "legal_unconfigured": _unconfigured(),
        "brand_name": settings.BRAND_NAME,
        "legal_entity": settings.LEGAL_ENTITY_NAME,
        "legal_contact_email": settings.LEGAL_CONTACT_EMAIL,
        "legal_jurisdiction": settings.LEGAL_JURISDICTION,
        "legal_address": settings.LEGAL_ADDRESS,
        "legal_effective_date": settings.LEGAL_EFFECTIVE_DATE,
        "legal_pages": LEGAL_PAGES,
    }


def index(request):
    return terms(request)


def terms(request):
    return render(request, "legal/terms.html", _context("legal:terms"))


def privacy(request):
    return render(request, "legal/privacy.html", _context("legal:privacy"))


def acceptable_use(request):
    return render(request, "legal/acceptable_use.html", _context("legal:acceptable_use"))


def cookies(request):
    return render(request, "legal/cookies.html", _context("legal:cookies"))
