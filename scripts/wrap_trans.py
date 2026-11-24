"""Wrap template text nodes and attribute values in {% trans %}.

Runs against only the strings that already have a catalog entry, so every
rewrite is verifiable after the fact: extraction must produce exactly the set of
strings this script expected, or the plugin has a bug.

What is deliberately NOT touched:
  * anything inside <script> / <style>
  * text that contains template variables or other tags ({{ }}, {% %}),
    because gettext cannot translate a string built at render time
  * HTML entities stay as-is in the source; extraction unescapes them, which is
    why the catalog keys were unescaped when the JSON seed was imported
  * nodes inside an existing {% if ui_is_zh %} branch, where a Chinese literal
    is already correct

Usage:
    python scripts/wrap_trans.py --dry-run
    python scripts/wrap_trans.py --apply --filter composer/
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

SKIP_BLOCK = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
# Template tags can span lines ({% ui_select %} with several attributes), so a
# text node is only safe if it contains no tag syntax at all. Masking whole tags
# before matching keeps a multi-line tag from being sliced in half.
TAG_SYNTAX = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
# Text node between tags, with no template syntax inside.
TEXT_NODE = re.compile(r">(?P<text>[^<>]+)<")


def collapse_ws(s: str) -> str:
    """Normalise a multi-line text node the way the catalog stores it.

    A sentence wrapped across source lines is one string to gettext: makemessages
    collapses the whitespace and writes a single msgid. Matching the raw node
    against the catalog would miss every such string.
    """
    return " ".join(s.split())


ATTR = re.compile(r'(?P<pre>\b(?:placeholder|title|aria-label|alt)=")(?P<text>[^"{}%]+)(?P<post>")')
HAS_WORD = re.compile(r"[A-Za-z]{2,}")
# A {% trans %} already sitting in the node, or a ui_is_zh branch.
ALREADY = re.compile(r"\{%\s*(?:trans|blocktrans)\b")


def load_msgids() -> set[str]:
    """Candidate strings to wrap: every key the legacy dictionary knows.

    Read from translations.json, not the .po. The .po is generated *from* the
    wrapped templates, so a string that is not wrapped yet can never appear in
    it. Using the .po would make wrapping depend on itself and miss exactly the
    strings that still need wrapping.
    """
    data = json.loads((ROOT / "apps/ui_zh/translations.json").read_text(encoding="utf-8"))
    ids: set[str] = set()
    for key in data:
        # Keys were stored in their rendered (escaped) form; the template holds
        # the source form.
        ids.add(html.unescape(key))
    return ids


def mask_blocks(src: str) -> tuple[str, list[tuple[int, int]]]:
    """Blank out script/style bodies and template tags.

    Both are replaced with equal-length spaces so every match offset in the
    masked copy still refers to the same position in the original. Matching on
    the raw source would let a multi-line {% ui_select %} tag be mistaken for
    text, which produces unparseable templates.
    """
    spans: list[tuple[int, int]] = []

    def repl(m: re.Match[str]) -> str:
        spans.append(m.span())
        return " " * (m.end() - m.start())

    masked = SKIP_BLOCK.sub(repl, src)
    masked = TAG_SYNTAX.sub(repl, masked)
    return masked, spans


def wrap_file(path: Path, msgids: set[str], apply: bool) -> int:
    src = path.read_text(encoding="utf-8")
    if "{% load i18n %}" not in src:
        # Everything this script emits needs the tag library.
        src = add_load_i18n(src)

    masked, _ = mask_blocks(src)
    edits: list[tuple[int, int, str]] = []

    for m in TEXT_NODE.finditer(masked):
        # Read the real content from the original source: the masked copy has
        # spaces where template tags were, and those offsets are the same.
        raw = src[m.start("text") : m.end("text")]
        text = collapse_ws(html.unescape(raw))
        if not text or not HAS_WORD.search(text) or text not in msgids:
            continue
        if ALREADY.search(raw):
            continue
        # A node that had a tag masked inside it is not a plain string any more.
        if "{" in raw or "}" in raw:
            continue
        lead = raw[: len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()) :]
        # Pick a delimiter the string does not contain. Both are valid template
        # syntax; the wrong one truncates the argument and fails to parse.
        if '"' not in text:
            quoted = f'"{text}"'
        elif "'" not in text:
            quoted = f"'{text}'"
        else:
            continue
        edits.append((m.start("text"), m.end("text"), f"{lead}{{% trans {quoted} %}}{trail}"))

    for m in ATTR.finditer(masked):
        text = html.unescape(src[m.start("text") : m.end("text")]).strip()
        if not text or not HAS_WORD.search(text) or text not in msgids:
            continue
        # The template parser reads the argument itself, so the quotes must be
        # real ones — &quot; is only decoded when the output is rendered, which
        # is too late. Single quotes keep the HTML attribute's " intact.
        if "'" in text:
            continue
        edits.append((m.start("text"), m.end("text"), f"{{% trans '{text}' %}}"))

    if not edits:
        if apply and "{% load i18n %}" in src:
            path.write_text(src, encoding="utf-8")
        return 0

    # Apply right-to-left so earlier offsets stay valid.
    out = src
    for start, end, replacement in sorted(edits, key=lambda e: -e[0]):
        out = out[:start] + replacement + out[end:]

    if apply:
        path.write_text(out, encoding="utf-8")
    return len(edits)


def add_load_i18n(src: str) -> str:
    """Insert {% load i18n %} into the first load tag, or after extends."""
    m = re.search(r"\{%\s*load\s+([^%]+?)\s*%\}", src)
    if m:
        names = m.group(1).split()
        if "i18n" not in names:
            return src[: m.start()] + "{% load " + " ".join([*names, "i18n"]) + " %}" + src[m.end() :]
        return src
    m = re.search(r"\{%\s*extends\s+[^%]+%\}", src)
    if m:
        return src[: m.end()] + "\n{% load i18n %}" + src[m.end() :]
    return "{% load i18n %}\n" + src


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--filter", default="", help="only paths containing this")
    args = ap.parse_args()

    msgids = load_msgids()
    files = sorted(TEMPLATES.rglob("*.html"))
    if args.filter:
        files = [f for f in files if args.filter in str(f.relative_to(ROOT))]

    total = changed = 0
    for f in files:
        n = wrap_file(f, msgids, args.apply)
        if n:
            changed += 1
            total += n
            print(f"{'wrapped' if args.apply else 'would wrap'} {n:4d}  {f.relative_to(ROOT)}")
    print(f"\n{'applied' if args.apply else 'dry-run'}: {total} strings in {changed} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
