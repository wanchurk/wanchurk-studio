"""Wrap remaining English copy in {% trans %}, skipping anything that is data.

The first wrapping pass only touched strings already present in the legacy
dictionary, so copy added later was never marked. This pass is the opposite:
take every text node that reads like human copy and mark it, then let the .po
supply Chinese. An untranslated msgid renders as itself, so over-marking is
harmless; under-marking is the bug.

The danger is the reverse - marking a data value or, worse, a fragment of
JavaScript that happens to sit between two angle brackets. Alpine expressions
are full of `>` and `<`, so a naive "text between > and <" pass will happily
wrap half an @click handler and then render a translated string into it. The
guards below exist for that: no JavaScript tokens, no brand names, no entities,
no attribute fragments, at least two real words.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SCRIPT_BLOCK = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
TEMPLATE_COMMENT = re.compile(r"\{#.*?#\}", re.S)
TAG_SYNTAX = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
TEXT_NODE = re.compile(r">([^<>]+)<", re.S)
ENGLISH_WORD = re.compile(r"[A-Za-z]{2,}")

# Anything that signals "this is code, an attribute fragment, or a value".
CODE_OR_VALUE = re.compile(
    r"""\$|=>|\bclassList\b|\bwindow\.|\bdocument\.|@click|@keydown|\bx-data\b
       |\bx-show\b|\bx-text\b|\balpinejs\b|\baddEventListener\b|;\s*$|^\s*[)\]}]""",
    re.X,
)
ENTITY_ONLY = re.compile(r"^[\s&;a-zA-Z]{0,3}$|^&[a-z]+;$", re.I)

# Product and platform names stay in English in every locale.
BRANDS = {
    "wanchurk-studio",
    "wanchurk",
    "instagram",
    "linkedin",
    "tiktok",
    "facebook",
    "youtube",
    "pinterest",
    "threads",
    "bluesky",
    "mastodon",
    "google",
    "dev.to",
    "stripe",
    "trustpilot",
    "reels",
    "pin",
    "youtube preview",
    "api",
    "url",
    "ai",
    "id",
    "ok",
    "csv",
    "pdf",
}

FILTERED_VAR = re.compile(r"\{\{\s*[^}]*[|(][^}]*\}\}")
VAR_PRESENT = re.compile(r"\{\{.*?\}\}")
# A node that begins with sentence punctuation was split from a neighbour by an
# inline <strong>/<a>; translating the tail alone yields a half-sentence.
FRAGMENT_START = re.compile(r"^[.,;:?!)\]]")

# Things that look like copy to a word counter but are values or placeholders.
NOT_COPY = re.compile(
    r"""^\{[A-Za-z_]+\}$                 # {sender_name} JS template literal
      | ^[^\s@]+@[^\s@]+\.[a-z]{2,}$     # email address
      | ^/[\w/….-]+$                    # /channel/UC… route stub
      | ^[\w.-]+\.[a-z]{2,}/\S*$         # dev.to/x path
    """,
    re.X | re.I,
)

SPLIT_TAIL_OPENERS = {
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "means",
    "readout",
    "in",
    "on",
    "at",
    "to",
    "of",
    "for",
    "with",
    "by",
    "from",
    "as",
    "that",
}

MIN_LEN = 12
MIN_WORDS = 2


def mask(text: str) -> str:
    text = SCRIPT_BLOCK.sub(lambda m: "<" + " " * (len(m.group(0)) - 2) + ">", text)
    text = TEMPLATE_COMMENT.sub(lambda m: " " * len(m.group(0)), text)
    return TAG_SYNTAX.sub(lambda m: " " * len(m.group(0)), text)


def is_copy(visible: str, real: str) -> bool:
    text = " ".join(visible.split())
    if len(text) < MIN_LEN:
        return False
    words = ENGLISH_WORD.findall(text)
    if len(words) < MIN_WORDS:
        return False
    if CODE_OR_VALUE.search(real):
        return False
    if ENTITY_ONLY.match(text):
        return False
    if "{%" in real:  # nested logic -> hand
        return False
    if text.lower().strip(" .:!?") in BRANDS:
        return False
    # A node that is only brand names and separators is chrome, not copy.
    stripped = text
    for brand in sorted(BRANDS, key=len, reverse=True):
        stripped = re.sub(rf"\b{re.escape(brand)}\b", " ", stripped, flags=re.I)
    if not ENGLISH_WORD.search(re.sub(r"[^A-Za-z]", " ", stripped)):
        return False
    # Attribute fragments quote- or paren-terminated by the scanner.
    if text.startswith(("!", "=")) or text.endswith(("\\", "=")):
        return False
    # {% trans %} cannot interpolate, and blocktrans rejects inline filters.
    if FILTERED_VAR.search(real):
        return False
    # Half of a sentence split by an inline tag.
    if FRAGMENT_START.match(text):
        return False
    if NOT_COPY.match(text):
        return False
    # A sentence fragment that opens on a preposition or a bare verb with no
    # subject reads as prose but is really the tail of a split sentence.
    first = text.split()[0].lower().strip(",.") if text.split() else ""
    if first in SPLIT_TAIL_OPENERS:
        return False
    # African lowercase opener that is not a known abbreviation: the node is the
    # tail of a sentence whose head lives in a previous text node.
    head = text.lstrip("(").lstrip()
    if head[:1].islower() and not re.match(r"^(e\.g\.|i\.e\.|x-)", head):
        return False
    # Simple variable, handled by blocktrans - not this pass.
    return not VAR_PRESENT.search(real)


def spans(source: str) -> list[tuple[int, int]]:
    masked = mask(source)
    out = []
    for m in TEXT_NODE.finditer(masked):
        visible = masked[m.start(1) : m.end(1)]
        real = source[m.start(1) : m.end(1)]
        if not visible.strip():
            continue
        if is_copy(visible, real):
            out.append((m.start(1), m.end(1)))
    return out


def quote_for(text: str) -> str | None:
    if '"' not in text:
        return '"'
    if "'" not in text:
        return "'"
    return None


def apply_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    found = spans(source)
    if not found:
        return 0
    applied = 0
    for s, e in sorted(found, key=lambda x: x[0], reverse=True):
        inner = source[s:e]
        if not inner.strip():
            continue
        lead = inner[: len(inner) - len(inner.lstrip())]
        trail = inner[len(inner.rstrip()) :]
        core = inner.strip()
        q = quote_for(core)
        if q is None:
            continue
        # Do NOT re-escape &: template source already carries entities like
        # &amp; and &middot;, and escaping them again renders the literal
        # "&amp;amp;" on the page.
        source = source[:s] + lead + "{% trans " + q + core + q + " %}" + trail + source[e:]
        applied += 1
    if applied:
        path.write_text(source, encoding="utf-8")
    return applied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = 0
    for path in sorted(Path(args.root).rglob("*.html")):
        n = apply_file(path) if args.apply else len(spans(path.read_text(encoding="utf-8")))
        if n:
            total += n
            print(f"{n:3d}  {path}")
    print(f"\n{total} nodes {'wrapped' if args.apply else 'to wrap'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
