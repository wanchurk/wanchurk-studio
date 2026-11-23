"""Accounts tests assert on upstream English copy and upstream signup defaults.

The deployment deliberately differs from upstream: the UI defaults to Chinese (the
translator middleware then rewrites visible text), and the signup entry point may be
replaced or closed through SIGNUP_MODE / CUSTOM_SIGNUP_URL in .env. Tests here assert
on the upstream originals, so pin those settings for this package only.

config.settings.test does the same globally, but the rest of the suite asserts on
localized Chinese copy and cannot run under it, and the developer .env overrides the
settings module anyway. Pinning here keeps both kinds of test honest.

A test that specifically exercises the switcher, a custom signup URL, or the Chinese
UI sets its own value with the `settings` fixture or a `ui_lang` cookie.
"""

import pytest


@pytest.fixture(autouse=True)
def _pin_upstream_defaults(settings):
    settings.UI_LANGUAGE = "en"
    settings.SIGNUP_MODE = "open"
    settings.CUSTOM_SIGNUP_URL = ""
