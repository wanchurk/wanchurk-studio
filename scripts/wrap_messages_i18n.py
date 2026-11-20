"""Wrap user-facing message literals in gettext and add the import.

Only the first argument of a messages.* call is touched: that is the text the
user reads. Anything already wrapped, or built at runtime (f-strings, .format),
is left alone — gettext needs a literal msgid.

Usage:
    python scripts/wrap_messages_i18n.py --dry-run
    python scripts/wrap_messages_i18n.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "apps"

# messages.success(request, "Text")  /  messages.error(request, "Text", extra_tags)
CALL = re.compile(
    r"(?P<head>messages\.(?:success|error|warning|info)\(\s*[^,()]+,\s*)"
    r'(?P<q>")(?P<text>(?:[^"\\]|\\.)+)(?P=q)'
)

IMPORT_LINE = "from django.utils.translation import gettext\n"


def already_imported(src: str) -> bool:
    # Exact import line, not a substring: "gettext" also appears inside
    # "gettext_lazy", and adding a duplicate import would shadow it.
    return "from django.utils.translation import gettext\n" in src


def add_import(src: str) -> str:
    """Insert the import in the Django import block, keeping isort happy."""
    lines = src.splitlines(keepends=True)
    last_django = -1
    for i, line in enumerate(lines):
        if line.startswith("from django") or line.startswith("import django"):
            last_django = i
    if last_django >= 0:
        lines.insert(last_django + 1, IMPORT_LINE)
        return "".join(lines)
    # No django import yet: put it after __future__ / docstring, before the rest.
    for i, line in enumerate(lines):
        if line.startswith("from __future__"):
            lines.insert(i + 1, "\n" + IMPORT_LINE)
            return "".join(lines)
    return IMPORT_LINE + src


def process(path: Path, apply: bool) -> int:
    src = path.read_text(encoding="utf-8")

    def repl(m: re.Match[str]) -> str:
        q = m.group("q")
        text = m.group("text")
        return f"{m.group('head')}gettext({q}{text}{q})"

    new, n = CALL.subn(repl, src)
    if n == 0:
        return 0
    if not already_imported(new):
        new = add_import(new)
    if apply:
        path.write_text(new, encoding="utf-8")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = files = 0
    for f in sorted(ROOT.rglob("*.py")):
        if "migrations" in f.parts:
            continue
        n = process(f, args.apply)
        if n:
            files += 1
            total += n
            print(f"{'wrapped' if args.apply else 'would wrap'} {n:3d}  {f.relative_to(ROOT.parent)}")
    print(f"\n{'applied' if args.apply else 'dry-run'}: {total} messages in {files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
