"""Find English prose sitting inside {% if %}/{% else %} branches.

wrap_remaining_copy skips any text node that contains template tags, which is
correct for mixed nodes but leaves pure-English branch bodies untouched.
This lists the branch bodies that are plain prose (no tags, no code) so they
can be marked explicitly. Run without --apply to review first.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

BRANCH = re.compile(r"\{%\s*(?:else|elif[^%]*|if[^%]*)\s*%\}([^{<]*?)(?=\{%|<)", re.S)
COPY = re.compile(r"[A-Za-z]{2,}(?:\s+[A-Za-z']+){3,}[.!?]?")
CODE = re.compile(r"[=(){};$]|\bclass\b|@|x-|https?://")


def candidates(source: str) -> list[tuple[int, int, str]]:
    out = []
    for m in BRANCH.finditer(source):
        body = m.group(1)
        text = " ".join(body.split())
        if not text or CODE.search(text):
            continue
        if not COPY.search(text):
            continue
        s, e = m.start(1), m.end(1)
        out.append((s, e, text))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    args = ap.parse_args()
    total = 0
    for path in sorted(Path(args.root).rglob("*.html")):
        src = path.read_text(encoding="utf-8")
        found = candidates(src)
        for _, _, text in found:
            total += 1
            print(f"{path}  |  {text[:100]}")
    print(f"\n{total} branch bodies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
