"""Convert the legacy translations.json dictionary into a gettext seed catalog.

The JSON dictionary was applied by rewriting rendered HTML, so it stores some
keys in their *escaped* form ("Articles &amp; posts"). gettext matches msgids
against the source text, where the ampersand is a literal "&", so the keys are
unescaped on the way in.

The output is a starting point for translators, not a build input: it is merged
into the catalog makemessages produces, because makemessages only knows about
strings that are actually wrapped in {% trans %} / gettext.

Usage:
    python scripts/seed_po_from_json.py locale/zh_Hans/LC_MESSAGES/django.po
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import polib

JSON_PATH = Path(__file__).resolve().parents[1] / "apps/ui_zh/translations.json"


def main(po_path: str) -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    po = polib.pofile(po_path) if Path(po_path).exists() else polib.POFile()
    po.metadata = {
        "Project-Id-Version": "wanchurk-studio",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Language": "zh_Hans",
        "Plural-Forms": "nplurals=1; plural=0;",
    }

    added = updated = skipped = 0
    for raw_key, raw_value in data.items():
        # The dictionary matched against rendered HTML, so its keys can carry
        # entities. Source text has plain characters.
        msgid = html.unescape(raw_key)
        msgstr = html.unescape(raw_value)
        if not msgid.strip() or not msgstr.strip():
            skipped += 1
            continue
        entry = po.find(msgid)
        if entry is None:
            po.append(polib.POEntry(msgid=msgid, msgstr=msgstr))
            added += 1
        elif not entry.msgstr:
            entry.msgstr = msgstr
            # msgmerge marks a changed msgid as fuzzy; gettext then ignores the
            # translation entirely, so the string shows up untranslated.
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            updated += 1
        else:
            skipped += 1

    po.save(po_path)
    print(f"added={added} filled={updated} kept_existing={skipped} total={len(po)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "locale/zh_Hans/LC_MESSAGES/django.po")
