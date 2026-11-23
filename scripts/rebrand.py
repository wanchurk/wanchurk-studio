"""Rename the visible brand across templates, styles and apps.

Driven entirely by environment variables, so the repository carries no literal
product name:

    REBRAND_FROM="OldBrand Studio,OldBrand,old-brand,oldbrand" \
    REBRAND_TO="wanchurk-studio" \
    python scripts/rebrand.py --apply

Longer variants are matched first, so "OldBrand Studio" wins over "OldBrand".

Anything listed in REBRAND_PROTECT (comma-separated) is shielded from the pass.
Use it for identifiers that reach stored data or the wire protocol: HKDF
`info=` strings, HMAC peppers, idempotency-key prefixes, custom header names,
database names and migration names. Changing those silently invalidates data
already on disk, which is why they are opt-in rather than renamed by default.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def build_rules() -> tuple[list[tuple[str, str]], list[str]]:
    brand = os.environ.get("REBRAND_TO", "").strip()
    sources = _csv("REBRAND_FROM")
    if not brand or not sources:
        raise SystemExit(
            "Set REBRAND_FROM and REBRAND_TO. Example:\n"
            '  REBRAND_FROM="OldBrand Studio,OldBrand,oldbrand" '
            'REBRAND_TO="wanchurk-studio" python scripts/rebrand.py'
        )
    # Every case variant matters: the source string is often lower-case in the
    # template and rendered upper-case by CSS, so a case-sensitive pass leaves
    # stray fragments behind. Longest first so a compound name is not eaten by
    # its own prefix.
    expanded = []
    for old in sources:
        expanded.extend((old, old.upper(), old.lower(), old.title()))
    seen, rules = set(), []
    for old in sorted(expanded, key=len, reverse=True):
        if old in seen:
            continue
        seen.add(old)
        rules.append((old, brand if old != old.upper() else brand.upper()))
    return rules, _csv("REBRAND_PROTECT")


SCAN_DIRS = ["templates", "theme/static_src/src", "apps"]
SKIP_PARTS = {"migrations", ".git", "node_modules", "__pycache__", "output", "locale"}
TEXT_SUFFIXES = {".html", ".txt", ".py", ".json", ".css", ".md", ".js"}

SENTINEL = "\x00PROTECT{}\x00"


def should_skip(path: Path) -> bool:
    return any(p in SKIP_PARTS for p in path.parts)


def rewrite(text: str, rules: list[tuple[str, str]], protected: list[str]) -> tuple[str, int]:
    hits = 0
    # Shield protected spans first so a rule cannot reach into them.
    saved = []
    for token in protected:
        if token in text:
            saved.append(token)
            text = text.replace(token, SENTINEL.format(len(saved) - 1))
    for old, new in rules:
        n = text.count(old)
        if n:
            hits += n
            text = text.replace(old, new)
    for i, token in enumerate(saved):
        text = text.replace(SENTINEL.format(i), token)
    return text, hits


def main(dry_run: bool) -> int:
    rules, protected = build_rules()
    total_files = 0
    total_hits = 0
    for d in SCAN_DIRS:
        for path in (ROOT / d).rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES or should_skip(path):
                continue
            try:
                src = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new, hits = rewrite(src, rules, protected)
            if hits and new != src:
                total_files += 1
                total_hits += hits
                if not dry_run:
                    path.write_text(new, encoding="utf-8")
                print(f"{hits:4d}  {path.relative_to(ROOT)}")
    print(f"\n{'DRY RUN ' if dry_run else ''}files={total_files} replacements={total_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--apply" not in sys.argv))
