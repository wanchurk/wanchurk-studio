"""Render-time Chinese UI and white-label branding.

The app does not route its copy through Django's i18n: templates and Python
strings carry the English source text, and the translation is applied at render
time. Two options existed:

  1. Wrap ~1,600 strings in {% trans %} across 249 templates and translate a PO
     file. Correct, but every copy change then has to be mirrored in the
     catalogue, and the template diffs get noisy.
  2. Translate the rendered HTML in middleware against a dictionary held here.

Option 2 keeps every template byte-identical to the English source, so template
edits apply cleanly; anything newly added in English shows up untranslated
(visible, not broken) and gets added to the dictionary. It is also reversible:
drop the middleware and the app is back to English.

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
    r"(<(script|style|pre|code)\b[^>]*>)(.*?)(</\2>)",
    re.I | re.S,
)

# A textarea's *content* is user input and must survive verbatim, but its opening
# tag carries UI copy (placeholder, aria-label) that has to be translated.
# Stashing the whole element swallowed those attributes, so only the inner text
# is sheltered and the tag stays in the flow.
TEXTAREA_INNER = re.compile(r"(<textarea\b[^>]*>)(.*?)(</textarea>)", re.I | re.S)

TEXT_ATTRS = ("placeholder", "title", "aria-label", "alt")
# Match real attribute names, not Alpine :title / x-bind:aria-label or data-title.
ATTR_RE = re.compile(r"(?<=\s)(" + "|".join(TEXT_ATTRS) + r')="([^"]*)"', re.I)

TAG_SPLIT = re.compile(r"(<[^>]+>)")

# <option> inner text is data (IANA names, codes), never copy.
OPTION_BLOCK = re.compile(r"(<option\b[^>]*>)(.*?)(</option>)", re.I | re.S)
HAS_LATIN = re.compile(r"[A-Za-z]")
# Region/City or Etc/GMT±N style identifiers. Anchored so ordinary sentences
# containing a slash ("Read/write access") are not mistaken for one.
TZ_ID = re.compile(r"^(?:[A-Z][A-Za-z_]+/[A-Za-z_+\-/0-9]+|Etc/[A-Za-z0-9+\-]+|UTC|GMT)$")
# The ui_select component strips the region prefix, leaving "New_York".
TZ_CITY = re.compile(r"^[A-Z][A-Za-z]*(?:_[A-Z][A-Za-z]*)+$")
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
    # Anchor on letters, never \b: a key may start or end with punctuation
    # ("Save & close", "Really?"), where \b would not fire. Without the guard a
    # key like "RSS URL" also matches inside "RSS URLs", yielding "RSS 地址s".
    left = r"(?<![A-Za-z])" if key[:1].isalpha() else ""
    right = r"(?![A-Za-z])" if key[-1:].isalpha() else ""
    return re.compile(rf"{left}{escaped}{right}")


_COMPILED: dict[str, re.Pattern[str]] = {}

# Declared here, not just assigned through `global` below: translate_text() reads
# it, and relying on the import-time _compile_all() call to have already created
# the name is fragile.
_KEYS_BY_LENGTH: list[str] = []


def _compile_all() -> None:
    global _KEYS_BY_LENGTH, _COMPILED
    # Only multi-word (punctuated / spaced) keys may rewrite substrings. A bare
    # word ("No", "New", "you") inside a longer sentence is data or copy that
    # the dictionary does not cover — rewriting it corrupts the text, and the
    # exact-dict-hit path above still translates the word when a node is
    # exactly that word.
    _KEYS_BY_LENGTH = sorted((k for k in _TRANSLATIONS if not _WORD_RE.match(k)), key=len, reverse=True)
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
    # The shipped name is spelled several ways; collapse them all to the operator's brand.
    return [
        ("wanchurk-studio", brand),
        ("wanchurk-studio", brand),
        ("wanchurk-studio", brand),
        ("wanchurk-studio", brand),
    ]


def translate_text(text: str) -> str:
    """Translate one text node, preserving leading/trailing whitespace."""
    if not text or not HAS_LATIN.search(text):
        return text

    original = WS.sub(" ", text).strip()

    # IANA timezone identifiers ("America/New_York", "Etc/GMT+5") are data.
    # A partially translated one is unusable, and they surface as dropdown
    # labels as well as values — sometimes with the region prefix stripped, so
    # a bare "New_York" or "Los_Angeles" must be caught too.
    if TZ_ID.match(original) or TZ_CITY.match(original):
        return text

    # Exact dictionary hit first, on the untouched source text. Brand rewriting
    # must not run before this, or keys containing the shipped name never match.
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

    English is the source text, so no dictionary runs; but the operator's
    white-label brand must still replace the shipped product name.
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

    # Shelter textarea contents only; the opening tag keeps flowing so its
    # placeholder/aria-label get translated by ATTR_RE further down.
    def stash_inner(match: re.Match[str]) -> str:
        protected.append(match.group(2))
        return f"{match.group(1)}\x00{len(protected) - 1}\x00{match.group(3)}"

    html = TEXTAREA_INNER.sub(stash_inner, html)

    # Option labels are mixed: sort dropdowns hold copy ("Newest first") while
    # timezone selects hold data (America/New_York). Data must survive verbatim —
    # a translated value is rejected by the server on save. Treat an option as
    # data when its label looks like an identifier (slash, underscore, code-like)
    # or is identical to its value; everything else is ordinary copy.
    kept_opts: list[str] = []

    def stash_option(match: re.Match[str]) -> str:
        tag, inner = match.group(1), match.group(2)
        label = inner.strip()
        m = re.search(r'value="([^"]*)"', tag, re.I)
        value = m.group(1) if m else ""
        is_data = "/" in label or (label == value and re.fullmatch(r"[A-Za-z0-9_+\-:/]+", label or ""))
        if not is_data:
            return match.group(0)
        kept_opts.append(inner)
        return f"{tag}\x00o{len(kept_opts) - 1}\x00{match.group(3)}"

    html = OPTION_BLOCK.sub(stash_option, html)

    parts = TAG_SPLIT.split(html)
    for i, part in enumerate(parts):
        if not part or part.startswith("<") or re.fullmatch(r"\x00o\d+\x00", part):
            continue
        parts[i] = convert(part)
    html = "".join(parts)
    html = re.sub(r"\x00o(\d+)\x00", lambda m: kept_opts[int(m.group(1))], html)

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
        # Legal pages stay in English: binding contract text must not be rewritten
        # by a UI translator, which would also invalidate a quoted clause.
        translate_dictionary = wanted == "zh" and not request.path.startswith("/legal/")
        translated = translate_html(html, translate=translate_dictionary)
        if translated != html:
            response.content = translated.encode(response.charset or "utf-8")
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
        return response
