"""Per-user UI language selection.

The UI is translated at render time by ``apps.ui_zh.middleware`` rather than
through Django's i18n framework, so the language is not a locale setting — it is
a switch that decides whether that middleware rewrites the HTML at all. English
is the upstream original, so switching to English means "do nothing"; switching
to Chinese means "run the dictionary".

The choice lives in a cookie, not on the user model: it must work for anonymous
visitors on the login page, and it must survive a logout. No migration, no DB
write on every request.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

LANGUAGE_COOKIE = "ui_lang"
LANGUAGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Map the language code onto the value ``settings.UI_LANGUAGE`` would hold.
# "en" is deliberately absent: English is the untranslated original.
SUPPORTED = {
    "zh": "zh-hans",
    "en": "en",
}


def normalize(code: str | None) -> str | None:
    """Return 'zh' / 'en' for a known code, else None."""
    if not code:
        return None
    code = code.strip().lower()
    if code in SUPPORTED:
        return code
    # Accept full tags so "zh-hans" / "zh-CN" / "en-US" also work.
    head = code.split("-")[0]
    return head if head in SUPPORTED else None


def resolve(request) -> str:
    """The effective language code for this request.

    Cookie first, then the site default from settings.UI_LANGUAGE. A visitor who
    has never chosen gets the site default, so a fresh install looks Chinese.
    """
    chosen = normalize(request.COOKIES.get(LANGUAGE_COOKIE))
    if chosen:
        return chosen
    return normalize(getattr(settings, "UI_LANGUAGE", "")) or "zh"


def is_chinese(request) -> bool:
    return resolve(request) == "zh"


@require_POST
def switch_view(request):
    """Set the language cookie and bounce back to the referring page.

    POST-only so a link prefetcher or an <img> can't flip someone's language.
    The redirect target is validated to prevent an open redirect.
    """
    target = normalize(request.POST.get("lang")) or "zh"
    nxt = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(
        nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        nxt = "/"
    response = HttpResponseRedirect(nxt)
    response.set_cookie(
        LANGUAGE_COOKIE,
        target,
        max_age=LANGUAGE_COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=False,
    )
    return response
