"""Rewrite dotted variables inside {% blocktrans %} into `with` bindings.

Django's blocktrans only resolves plain names from the context. A dotted
reference such as {{ page.number }} compiles without complaint but renders as
the empty string, so "Page {{ page.number }} of {{ total }}" silently loses both
numbers. The fix is the documented one: bind each dotted value to a simple name
on the tag itself.

    {% blocktrans trimmed %}Page {{ page.number }} of {{ n }}{% endblocktrans %}
    {% blocktrans trimmed with page_number=page.number %}Page {{ page_number }} of {{ n }}{% endblocktrans %}

Blocks that already carry a `with` clause have the new bindings appended.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

BLOCK = re.compile(r"\{% blocktrans(?P<tag>[^%]*?)%\}(?P<body>.*?)\{% endblocktrans %\}", re.S)
VAR = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
TAG_WITH = re.compile(r"\bwith\b(?P<rest>[^%]*)$")


def alias_for(expr: str) -> str:
    return expr.replace(".", "_")


def rewrite_block(match: re.Match[str]) -> str:
    tag, body = match.group("tag"), match.group("body")
    dotted = [v for v in VAR.findall(body) if "." in v]
    if not dotted:
        return match.group(0)

    # Preserve order, drop duplicates.
    seen: dict[str, str] = {}
    for expr in dotted:
        seen.setdefault(alias_for(expr), expr)

    new_body = body
    for alias, expr in seen.items():
        new_body = re.sub(
            r"\{\{\s*" + re.escape(expr) + r"\s*\}\}", "{{ " + alias + " }}", new_body
        )

    bindings = " ".join(f"{a}={e}" for a, e in seen.items())
    if TAG_WITH.search(tag):
        new_tag = tag.rstrip() + " " + bindings + " "
    elif "trimmed" in tag:
        new_tag = tag.replace("trimmed", "trimmed with " + bindings, 1)
    else:
        new_tag = " with " + bindings + " " + tag
        if not new_tag.startswith(" "):
            new_tag = " " + new_tag

    return "{% blocktrans" + new_tag.rstrip() + " %}" + new_body + "{% endblocktrans %}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = 0
    for path in sorted(Path(args.root).rglob("*.html")):
        source = path.read_text(encoding="utf-8")
        if "blocktrans" not in source:
            continue
        new = BLOCK.sub(rewrite_block, source)
        if new == source:
            continue
        len(BLOCK.findall(new)) - 0
        sum(
            1
            for m in BLOCK.finditer(new)
            if any("." in v for v in VAR.findall(m.group("body")))
        )
        # Count how many blocks actually differ from the original.
        orig = {m.group(0) for m in BLOCK.finditer(source)}
        fixed = sum(1 for m in BLOCK.finditer(new) if m.group(0) not in orig)
        if not fixed:
            continue
        total += fixed
        print(f"{fixed}  {path}")
        if args.apply:
            path.write_text(new, encoding="utf-8")
    print(f"\n{total} blocks {'rewritten' if args.apply else 'to rewrite'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
