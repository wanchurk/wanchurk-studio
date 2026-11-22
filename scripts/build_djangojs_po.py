"""Build the djangojs catalog from gettext() calls in templates.

JavaScriptCatalog reads the djangojs domain, not django's, and makemessages
never looks inside x-text attributes - so any msgid that only exists in an
Alpine expression is invisible to both. This collects every gettext('...') in
the templates, reuses the translation already sitting in django.po when the
msgid matches, and reports the ones still needing Chinese.

Keeping this catalog to just the JS msgids (rather than mirroring django.po)
means one place to edit per string and no drift between two 1200-entry files.

Run: docker compose exec -T app python scripts/build_djangojs_po.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

GETTEXT_CALL = re.compile(r"""gettext\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*\)""")
NGETTEXT_CALL = re.compile(
    r"""ngettext\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*,\s*(['"])((?:\\.|(?!\3).)*)\3\s*,"""
)

HEADER = r'''msgid ""
msgstr ""
"Project-Id-Version: wanchurk-studio\n"
"Report-Msgid-Bugs-To: \n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Language: zh_Hans\n"
"Plural-Forms: nplurals=1; plural=0;\n"
'''


def collect(root: Path) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    """gettext msgid -> templates; ngettext (singular, plural) -> templates."""
    found: dict[str, set[str]] = {}
    plurals: dict[tuple[str, str], set[str]] = {}
    for path in sorted(root.rglob("*.html")):
        source = path.read_text(encoding="utf-8")
        for m in GETTEXT_CALL.finditer(source):
            raw = m.group(2)
            if not raw.strip():
                continue
            msgid = raw.replace("\\'", "'").replace('\\"', '"')
            found.setdefault(msgid, set()).add(str(path))
        for m in NGETTEXT_CALL.finditer(source):
            singular = m.group(2).replace("\\'", "'")
            plural = m.group(4).replace("\\'", "'")
            if not singular.strip() or not plural.strip():
                continue
            key = (singular, plural)
            plurals.setdefault(key, set()).add(str(path))
    return found, plurals


def read_django_po(path: Path) -> dict[str, str]:
    """Minimal .po reader: msgid -> msgstr for single-line entries."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    entries: list[tuple[str, str]] = []
    cur_id: list[str] = []
    cur_str: list[str] = []
    mode = None

    def flush() -> None:
        if cur_id:
            entries.append(("".join(cur_id), "".join(cur_str)))

    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("msgid "):
            if cur_id or cur_str:
                flush()
            cur_id, cur_str, mode = [_unquote(s[6:])], [], "id"
        elif s.startswith("msgstr "):
            mode = "str"
            cur_str.append(_unquote(s[7:]))
        elif s.startswith('"') and mode in ("id", "str"):
            (cur_id if mode == "id" else cur_str).append(_unquote(s))
        elif not s:
            if cur_id or cur_str:
                flush()
            cur_id, cur_str, mode = [], [], None
    flush()
    for msgid, msgstr in entries:
        if msgid:
            out[msgid] = msgstr
    return out


def _unquote(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1]
    return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\'", "'")


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def parse_blocks(path: Path) -> dict[str, str]:
    """msgid -> raw block text, so plural entries and their translations survive a rebuild."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for block in re.split(r"\n\s*\n", text):
        m = re.search(r'^msgid "((?:[^"\\]|\\.)*)"', block, re.M)
        if not m or not m.group(1):
            continue
        key = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
        blocks[key] = block.strip("\n")
    return blocks


def is_translated(block: str) -> bool:
    return bool(re.search(r'msgstr(?:\[\d\])? "[^"]+"', block))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="templates")
    ap.add_argument("--out", default="locale/zh_Hans/LC_MESSAGES/djangojs.po")
    ap.add_argument("--django-po", default="locale/zh_Hans/LC_MESSAGES/django.po")
    args = ap.parse_args()

    found, plurals = collect(Path(args.root))
    reuse = read_django_po(Path(args.django_po))

    out_path = Path(args.out)
    existing = parse_blocks(out_path)

    blocks: list[str] = [HEADER.rstrip("\n")]
    missing: list[str] = []
    reused = 0

    for msgid in sorted(found):
        if msgid in existing and is_translated(existing[msgid]):
            blocks.append(existing[msgid])
            continue
        if msgid in reuse and reuse[msgid]:
            msgstr = reuse[msgid]
            reused += 1
        else:
            msgstr = ""
            missing.append(msgid)
        blocks.append(f'msgid "{escape(msgid)}"\nmsgstr "{escape(msgstr)}"')

    for singular, plural in sorted(plurals):
        if singular in existing and is_translated(existing[singular]):
            blocks.append(existing[singular])
            continue
        if singular in reuse and reuse[singular]:
            blocks.append(
                f'msgid "{escape(singular)}"\n'
                f'msgid_plural "{escape(plural)}"\n'
                f'msgstr[0] "{escape(reuse[singular])}"'
            )
            reused += 1
            continue
        blocks.append(
            f'msgid "{escape(singular)}"\n'
            f'msgid_plural "{escape(plural)}"\n'
            f'msgstr[0] ""'
        )
        missing.append(f"{singular} | {plural}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    total = len(found) + len(plurals)
    print(f"{total} msgids ({len(found)} gettext, {len(plurals)} ngettext); {reused} reused")
    print(f"needs Chinese: {len(missing)}")
    for m in missing:
        print(f"  MISSING {m!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
