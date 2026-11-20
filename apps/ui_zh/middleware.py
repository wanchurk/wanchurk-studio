"""Render-time Chinese UI and white-label branding.

The upstream project does not use Django's i18n at all: 249 templates and every
Python string are hard-coded English, with no gettext calls, no LocaleMiddleware
and no locale directory. Two options existed:

  1. Wrap ~1,600 strings in {% trans %} across 249 templates and translate a PO
     file. Correct, but every template becomes a merge conflict on each upstream
     pull, and the project ships updates regularly.
  2. Translate the rendered HTML in middleware against a dictionary held here.

Option 2 keeps every template byte-identical to upstream. Upstream updates apply
cleanly; anything newly added in English shows up untranslated (visible, not
broken) and gets added to the dictionary. It is also reversible: drop the
middleware and the app is back to English.

The same middleware applies white-label branding, so the brand appears in one
place (settings.BRAND_NAME) instead of being hard-coded in templates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings

from apps.ui_zh import language

TRANSLATIONS_PATH = Path(__file__).with_name("translations.json")

# Never rewrite inside these elements: markup, scripts, or code samples.
SKIP_BLOCKS = re.compile(
    r"(<(script|style|pre|code|textarea)\b[^>]*>)(.*?)(</\2>)",
    re.I | re.S,
)

TEXT_ATTRS = ("placeholder", "title", "aria-label", "alt")
ATTR_RE = re.compile(r"\b(" + "|".join(TEXT_ATTRS) + r')="([^"]*)"', re.I)

TAG_SPLIT = re.compile(r"(<[^>]+>)")
HAS_LATIN = re.compile(r"[A-Za-z]")
WS = re.compile(r"\s+")


def _load() -> dict[str, str]:
    try:
        data = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v}


_TRANSLATIONS: dict[str, str] = _load()

# Longest key first so "Save Changes" wins over "Save". Plain substrings are
# only safe for multi-word or punctuated keys — a single English word like "or"
# would otherwise rewrite the inside of "for", "format", "author". Short keys
# therefore match on word boundaries (see _pattern_for).
_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'-]*$")


def _pattern_for(key: str) -> re.Pattern[str]:
    escaped = re.escape(key)
    if _WORD_RE.match(key):
        # \b is wrong at a leading/trailing non-word edge, so anchor on letters.
        return re.compile(rf"(?<![A-Za-z]){escaped}(?![A-Za-z])")
    return re.compile(escaped)


_COMPILED: dict[str, re.Pattern[str]] = {}

# Declared here, not just assigned through `global` below: translate_text() reads
# it, and relying on the import-time _compile_all() call to have already created
# the name is fragile.
_KEYS_BY_LENGTH: list[str] = []


def _compile_all() -> None:
    global _KEYS_BY_LENGTH, _COMPILED
    _KEYS_BY_LENGTH = sorted(_TRANSLATIONS, key=len, reverse=True)
    _COMPILED = {key: _pattern_for(key) for key in _KEYS_BY_LENGTH}


# Compile once at import: reload_translations() is only called on hot reload and
# when the dictionary changes, so without this the cache would start empty.
_compile_all()


def reload_translations() -> None:
    """Re-read the dictionary. Used by the dev watcher and after batch edits."""
    global _TRANSLATIONS
    _TRANSLATIONS = _load()
    _compile_all()


def lookup(text: str) -> str:
    """Exact dictionary lookup for strings assembled in Python.

    Template tags that build a label and hand it to JavaScript cannot rely on
    the render-time HTML pass, because the value never becomes a text node.
    """
    return _TRANSLATIONS.get(text, text)


def _brand_map() -> list[tuple[str, str]]:
    brand = getattr(settings, "BRAND_NAME", "") or ""
    if not brand:
        return []
    # Upstream spells it several ways; collapse them all to the operator's brand.
    return [
        ("BrightBean Studio", brand),
        ("Brightbean Studio", brand),
        ("BrightBean", brand),
        ("Brightbean", brand),
    ]


def translate_text(text: str) -> str:
    """Translate one text node, preserving leading/trailing whitespace."""
    if not text or not HAS_LATIN.search(text):
        return text

    original = WS.sub(" ", text).strip()

    # Exact dictionary hit first, on the untouched source text. Brand rewriting
    # must not run before this, or keys containing the upstream name never match.
    exact = _TRANSLATIONS.get(original)
    if exact is not None:
        return text.replace(text.strip(), exact, 1)

    work = original
    for key in _KEYS_BY_LENGTH:
        pattern = _COMPILED.get(key)
        if pattern is not None and pattern.search(work):
            work = pattern.sub(_TRANSLATIONS[key], work)
    for src, dst in _brand_map():
        if src in work:
            work = work.replace(src, dst)

    # Compare against the pre-brand text: a brand-only change is still a change.
    if work == original:
        return text
    # Keep the original outer whitespace so inline layout is unaffected.
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    return f"{lead}{work}{trail}"


def brand_text(text: str) -> str:
    """Re-brand only — used when the UI language is English.

    English is the upstream original, so no dictionary runs; but the operator's
    white-label brand must still replace the upstream product name.
    """
    if not text or not HAS_LATIN.search(text):
        return text
    work = text
    for src, dst in _brand_map():
        if src in work:
            work = work.replace(src, dst)
    return work


def translate_html(html: str, translate: bool = True) -> str:
    """Rewrite a finished HTML document.

    ``translate=False`` keeps the English original and applies the brand only,
    which is exactly what the language switcher's "English" option needs.
    """
    convert = translate_text if translate else brand_text

    def keep(match: re.Match[str]) -> str:
        return match.group(1) + "\x00" + match.group(3) + "\x00" + match.group(4)

    protected: list[str] = []

    def stash(match: re.Match[str]) -> str:
        protected.append(keep(match))
        return f"\x00{len(protected) - 1}\x00"

    html = SKIP_BLOCKS.sub(stash, html)

    parts = TAG_SPLIT.split(html)
    for i, part in enumerate(parts):
        if not part or part.startswith("<"):
            continue
        parts[i] = convert(part)
    html = "".join(parts)

    def attr(match: re.Match[str]) -> str:
        name, value = match.group(1), match.group(2)
        if not HAS_LATIN.search(value):
            return match.group(0)
        return f'{name}="{convert(value)}"'

    html = ATTR_RE.sub(attr, html)

    def restore(match: re.Match[str]) -> str:
        return protected[int(match.group(1))].replace("\x00", "")

    return re.sub(r"\x00(\d+)\x00", restore, html)


class UiZhMiddleware:
    """Translate and re-brand HTML responses on the way out."""

    def __init__(self, get_response):
        self.get_response = get_response
        # Dev convenience: pick up dictionary edits without a restart.
        if getattr(settings, "BRAND_I18N_HOT_RELOAD", False):
            reload_translations()
            self._mtime = TRANSLATIONS_PATH.stat().st_mtime if TRANSLATIONS_PATH.exists() else 0
        else:
            self._mtime = None

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(response, "streaming", False):
            return response
        ctype = response.get("Content-Type", "")
        if "text/html" not in ctype:
            return response

        # Directory scan hits this for every URL in the app, so fail open: if the
        # dictionary can't be loaded the page stays English, never broken.
        wanted = language.resolve(request)

        if self._mtime is not None:
            try:
                mtime = TRANSLATIONS_PATH.stat().st_mtime
                if mtime != self._mtime:
                    self._mtime = mtime
                    reload_translations()
            except OSError:
                pass

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (UnicodeDecodeError, AttributeError):
            return response

        # Branding applies in both languages; the dictionary only in Chinese.
        translated = translate_html(html, translate=(wanted == "zh"))
        if translated != html:
            response.content = translated.encode(response.charset or "utf-8")
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
        return response
