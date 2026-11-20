"""Expose the active UI language to every template.

Templates need this to render the switcher itself and to pick the right label in
the handful of places where a string lives in a JS expression rather than a text
node (Alpine ``x-text``), which the middleware cannot rewrite.
"""

from __future__ import annotations

from apps.ui_zh import language


def ui_language(request):
    current = language.resolve(request)
    return {
        "ui_lang": current,
        "ui_is_zh": current == "zh",
        "ui_languages": (
            ("zh", "中文"),
            ("en", "English"),
        ),
    }
