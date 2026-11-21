"""Wrap template text nodes that mix English words with {{ variables }} in
{% blocktrans %}.

{% trans %} can't interpolate, so any line like "Page {{ n }} of {{ total }}"
was left untranslated by the first pass. blocktrans is the right tool, but it
only accepts plain variable references — no filters, no calls — and it can't be
nested inside other block tags. This script therefore rewrites only the simple
nodes:

- the node contains at least one {{ var }} (no |, no parens)
- it contains an English word (after removing the variables)
- it contains no {% ... %} at all (no nested logic, not already wrapped)

Everything is detected on a masked copy (script/style bodies and tag syntax
blanked to keep offsets aligned) but applied to the real source, so JS is never
touched. --apply writes back; the compile check that follows is the real gate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAG_SYNTAX = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
SCRIPT_BLOCK = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
TEXT_NODE = re.compile(r">([^<>]+)<", re.S)
ANY_VAR = re.compile(r"\{\{.*?\}\}", re.S)
FILTERED_VAR = re.compile(r"\{\{\s*[^}]*\|[^}]*\}\}|\{\{\s*[^}]*\([^)]*\)[^}]*\}\}")
ENGLISH_WORD = re.compile(r"[A-Za-z]{3,}")
HAS_BLOCKTAG = re.compile(r"\{%")


def mask(text: str) -> str:
    """Blank everything that is not a plain text node, keeping offsets stable.

    Script and style bodies become a pair of sentinels rather than a run of
    spaces. Blanked to spaces only, the node would carry no < or > and the
    text-node regex would join the copy on either side of it into one node,
    which then swallows the whole script body.
    """
    text = SCRIPT_BLOCK.sub(lambda m: "<" + " " * (len(m.group(0)) - 2) + ">", text)
    text = TAG_SYNTAX.sub(lambda m: " " * len(m.group(0)), text)
    return text


def candidates(source: str) -> list[tuple[int, int]]:
    masked = mask(source)
    out: list[tuple[int, int]] = []
    for m in TEXT_NODE.finditer(masked):
        s, e = m.start(1), m.end(1)
        real = source[s:e]
        if not ANY_VAR.search(real):
            continue
        if HAS_BLOCKTAG.search(real):
            continue
        if FILTERED_VAR.search(real):
            continue
        words = ENGLISH_WORD.findall(ANY_VAR.sub(" ", real))
        if not words:
            continue
        out.append((s, e))
    return out


def apply_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    spans = candidates(source)
    if not spans:
        return 0
    for s, e in sorted(spans, key=lambda x: x[0], reverse=True):
        inner = source[s:e]
        source = source[:s] + "{% blocktrans trimmed %}" + inner + "{% endblocktrans %}" + source[e:]
    path.write_text(source, encoding="utf-8")
    return len(spans)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()

    paths = [Path(f) for f in args.files] if args.files else sorted(Path(args.root).rglob("*.html"))

    total = 0
    for p in paths:
        if p.suffix != ".html":
            continue
        if args.apply:
            n = apply_file(p)
            if n:
                total += n
                print(f"{n}  {p}")
        else:
            n = len(candidates(p.read_text(encoding="utf-8")))
            if n:
                total += n
                print(f"{n}  {p}")
    print(f"\n{total} blocktrans candidates", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
