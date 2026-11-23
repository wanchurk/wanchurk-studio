"""Assertions here are on upstream English copy.

The deployment UI defaults to Chinese and the translator middleware rewrites visible
text, so any assertion on an English string fails unless the language is pinned.
config.settings.test pins it globally, but the developer .env selects the settings
module and overrides that; pinning per package keeps these tests independent of it.

Tests that exercise the Chinese UI set their own value or a `ui_lang` cookie.
"""

import pytest


@pytest.fixture(autouse=True)
def _pin_english_ui(settings):
    settings.UI_LANGUAGE = "en"
