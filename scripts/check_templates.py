"""Compile every template so a broken tag fails here, not in production.

Django only raises TemplateSyntaxError when a template is actually loaded, so a
typo in a rarely-rendered partial can ship unnoticed. This walks the tree and
loads each one.

Run inside the container: docker compose exec -T app python scripts/check_templates.py
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    import django

    django.setup()
    from django.template.loader import get_template

    paths = sorted(glob.glob("templates/**/*.html", recursive=True))
    bad = []
    for path in paths:
        try:
            get_template(path[len("templates/") :])
        except Exception as exc:
            bad.append((path, str(exc).split("\n")[0][:140]))
    print(f"compiled {len(paths) - len(bad)}/{len(paths)}")
    for path, err in bad:
        print(f"  FAIL {path} | {err}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
