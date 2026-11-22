"""Rebrand user-visible text from BrightBean / 跨境铺子 to wanchurk-studio.

Protected identifiers are never touched: encryption/HMAC info strings, the
idempotency-key prefix, the X-Brightbean-Email-Class header, DB names and
migration names. Those change stored data or wire protocol.
"""
import re
import sys
from pathlib import Path

ROOT = Path("/Users/wanchurk/wanchurk-studio")
BRAND = "wanchurk-studio"

# Strings that must survive exactly as-is (data / protocol / crypto).
PROTECTED = [
    'info=b"brightbean-field-encryption"',
    'info=b"brightbean-api-key-hmac"',
    'f"brightbean-{platform_post.id}"',
    'X-Brightbean-Email-Class',
    '"brightbean-favorites"',
    "brightbean-favorites",
    "brightbean_test",
    "postgres://postgres:***@localhost:5432/brightbean",
    "postgres://postgres:***@postgres:5432/brightbean",
]

# Ordered: longer / more specific first so "BrightBean Studio" wins over "BrightBean".
REPLACEMENTS = [
    ("BrightBean Studio", BRAND),
    ("Brightbean Studio", BRAND),
    ("brightbean-studio", BRAND),
    ("BrightBean's", f"{BRAND}'s"),
    ("Brightbean", BRAND),
    ("BrightBean", BRAND),
]

SCAN_DIRS = ["templates", "theme/static_src/src", "apps"]
SKIP_PARTS = {"migrations", ".git", "node_modules", "__pycache__", "output", "locale"}
TEXT_SUFFIXES = {".html", ".txt", ".py", ".json", ".css", ".md", ".js"}

SENTINEL = "\x00PROTECT{}\x00"


def should_skip(path: Path) -> bool:
    return any(p in SKIP_PARTS for p in path.parts)


def rewrite(text: str) -> tuple[str, int]:
    hits = 0
    # Shield protected spans first.
    saved = []
    for i, token in enumerate(PROTECTED):
        if token in text:
            saved.append(token)
            text = text.replace(token, SENTINEL.format(len(saved) - 1))
    for old, new in REPLACEMENTS:
        n = text.count(old)
        if n:
            hits += n
            text = text.replace(old, new)
    for i, token in enumerate(saved):
        text = text.replace(SENTINEL.format(i), token)
    return text, hits


def main(dry_run: bool) -> int:
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
            new, hits = rewrite(src)
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
