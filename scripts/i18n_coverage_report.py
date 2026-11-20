"""Dry-run: find template text nodes whose content already has a translation.

Reports what a mechanical {% trans %} pass could cover, without touching any
file. The point is to size the job and to check that the extraction is precise:
a false positive here becomes a broken template later.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PO = ROOT / "locale/zh_Hans/LC_MESSAGES/django.po"

# A text node: between a ">" and the next "<", with no template syntax inside.
TEXT_NODE = re.compile(r">([^<>{}%]+)<")
# Attribute values that hold user-visible copy.
ATTR = re.compile(r'(?P<pre>\b(?:placeholder|title|alt|aria-label|value)=")(?P<text>[^"{}%]+)(?P<post>")')
SKIP_BLOCK = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
HAS_WORD = re.compile(r"[A-Za-z]{2,}")


def load_msgids() -> set[str]:
    ids: set[str] = set()
    for line in PO.read_text(encoding="utf-8").splitlines():
        if line.startswith("msgid "):
            raw = line[6:]
            s = raw[1:-1] if raw.startswith('"') and raw.endswith('"') else raw
            s = s.replace('\\"', '"').replace("\\n", "\n")
            if s:
                ids.add(s)
    return ids


def main() -> None:
    msgids = load_msgids()
    print(f"msgids in catalog: {len(msgids)}")

    templates = sorted((ROOT / "templates").rglob("*.html"))
    hits_total = 0
    files_with_hits = 0
    unmatched_sample: list[str] = []

    for tpl in templates:
        src = tpl.read_text(encoding="utf-8")
        # Work on a copy with script/style masked so their contents never match.
        masked = SKIP_BLOCK.sub(lambda m: " " * len(m.group(0)), src)
        hits = 0
        for m in TEXT_NODE.finditer(masked):
            text = html.unescape(m.group(1)).strip()
            if not text or not HAS_WORD.search(text):
                continue
            if text in msgids:
                hits += 1
            elif len(unmatched_sample) < 25 and len(text) > 8:
                unmatched_sample.append(text)
        for m in ATTR.finditer(masked):
            text = html.unescape(m.group("text")).strip()
            if text and HAS_WORD.search(text) and text in msgids:
                hits += 1
        if hits:
            files_with_hits += 1
            hits_total += hits
            if hits >= 5:
                print(f"  {tpl.relative_to(ROOT)}: {hits}")

    print(f"\nfiles: {len(templates)}, with translatable hits: {files_with_hits}")
    print(f"text/attr nodes coverable by existing catalog: {hits_total}")
    print("\n-- sample of English-looking text NOT in catalog --")
    for s in unmatched_sample[:15]:
        print(f"  {s[:90]}")


if __name__ == "__main__":
    sys.exit(main())
