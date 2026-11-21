"""Find plain-text template nodes that still contain English copy and are not
already marked for translation.

The first pass deliberately wrapped only strings that existed in the legacy
dictionary, so that every rewrite was verifiable against a known translation.
That left genuinely-new copy untouched. Now that a real .po exists, any English
text node can be marked; an untranslated msgid simply renders as itself, so
marking is safe even before the Chinese is written.

Reports, per node, whether it is wrappable automatically (plain text, no nested
template logic) or needs a hand (contains {% if %}/{% for %}, where the words
are inside branches).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_BLOCK = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
TEMPLATE_COMMENT = re.compile(r"\{#.*?#\}", re.S)
TAG_SYNTAX = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)
TEXT_NODE = re.compile(r">([^<>]+)<", re.S)
ENGLISH_WORD = re.compile(r"[A-Za-z]{3,}")
ANY_TAG = re.compile(r"\{%")
# Strings that are data rather than copy: these must never reach gettext.
DATA_ONLY = re.compile(
    r"""^\s*(?:
        [a-z0-9_.\-]+@[a-z0-9_.\-]+           # email
      | [A-Z][A-Za-z]+/[A-Za-z_+/\-0-9]+      # IANA timezone
      | [A-Z][A-Za-z]*(?:_[A-Za-z]+)+         # bare tz city
      | https?://\S+                          # url
      | [A-Z0-9_\-]{3,}                       # constant
      | [\d\s.,:%/\-+()&;×·—–]*               # numbers & punctuation
    )\s*$""",
    re.X,
)


def mask(text: str) -> str:
    text = SCRIPT_BLOCK.sub(lambda m: "<" + " " * (len(m.group(0)) - 2) + ">", text)
    text = TEMPLATE_COMMENT.sub(lambda m: " " * len(m.group(0)), text)
    return TAG_SYNTAX.sub(lambda m: " " * len(m.group(0)), text)


def scan(source: str) -> list[tuple[int, str, bool]]:
    """Return (line, text, needs_hand) for each untranslated English node.

    The English check runs against the MASKED node, not the raw source: a node
    whose whole body is a {# comment #} or an &entity; masks down to spaces and
    is not copy. The text reported to the user is still the readable original.
    """
    masked = mask(source)
    out = []
    for m in TEXT_NODE.finditer(masked):
        visible = masked[m.start(1) : m.end(1)]
        real = source[m.start(1) : m.end(1)]
        if not visible.strip():
            continue
        if not ENGLISH_WORD.search(visible):
            continue
        flat = " ".join(real.split())
        if DATA_ONLY.match(flat):
            continue
        bare = " ".join(visible.split())
        if len(bare) < 4:
            continue
        line = source.count("\n", 0, m.start(1)) + 1
        out.append((line, flat, bool(ANY_TAG.search(real))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    ap.add_argument("--needs-hand", action="store_true")
    args = ap.parse_args()

    auto = hand = files = 0
    for path in sorted(Path(args.root).rglob("*.html")):
        source = path.read_text(encoding="utf-8")
        rows = scan(source)
        if args.needs_hand:
            rows = [r for r in rows if r[2]]
        if not rows:
            continue
        files += 1
        for line, text, hand_required in rows:
            print(f"{'HAND' if hand_required else 'auto'}  {path}:{line}  {text[:140]}")
            if hand_required:
                hand += 1
            else:
                auto += 1
    print(f"\nauto={auto} hand={hand} files={files}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
