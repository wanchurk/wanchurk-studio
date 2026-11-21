"""Report template text nodes that mix English words with {{ variables }}.

Those cannot be handled by {% trans %} (it has no interpolation) and need
{% blocktrans %}. The scan deliberately ignores anything inside <script>,
<style>, or template tag syntax, because those are not text nodes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAG_SYNTAX = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
SCRIPT_BLOCK = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
TEXT_NODE = re.compile(r">([^<>]+)<", re.S)
HAS_VAR = re.compile(r"\{\{.*?\}\}", re.S)
ENGLISH_WORD = re.compile(r"[A-Za-z]{3,}")
# {% blocktrans %} only accepts simple variable references: {{ name }} or
# {{ obj.attr }}. Filters and calls are rejected by the template parser.
FILTERED_VAR = re.compile(r"\{\{\s*[^}]*\|[^}]*\}\}")


def mask(text: str) -> str:
    """Blank out regions that are not plain text, keeping offsets stable.

    Script and style bodies are replaced with a pair of sentinels rather than
    spaces: a bare run of spaces would let the text-node regex join the text on
    either side of the block into one node, which then swallows the JS source.
    """
    text = SCRIPT_BLOCK.sub(lambda m: "<" + " " * (len(m.group(0)) - 2) + ">", text)
    text = TAG_SYNTAX.sub(lambda m: " " * len(m.group(0)), text)
    return text


def candidates(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    masked = mask(source)
    found = []
    for m in TEXT_NODE.finditer(masked):
        body = source[m.start(1) : m.end(1)]
        if not HAS_VAR.search(body):
            continue
        if not ENGLISH_WORD.search(HAS_VAR.sub(" ", body)):
            continue
        line = source.count("\n", 0, m.start(1)) + 1
        found.append((line, body.strip()))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    ap.add_argument("--filtered", action="store_true", help="only unfixable (filtered) vars")
    args = ap.parse_args()

    root = Path(args.root)
    total = 0
    files = 0
    for path in sorted(root.rglob("*.html")):
        rows = candidates(path)
        if not rows:
            continue
        if args.filtered:
            rows = [(ln, s) for ln, s in rows if FILTERED_VAR.search(s)]
            if not rows:
                continue
        files += 1
        rel = path.relative_to(root)
        for line, body in rows:
            flag = " [FILTERED]" if FILTERED_VAR.search(body) else ""
            one = " ".join(body.split())[:150]
            print(f"{rel}:{line}{flag}  {one}")
        total += len(rows)
    print(f"\n{total} candidates in {files} files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
