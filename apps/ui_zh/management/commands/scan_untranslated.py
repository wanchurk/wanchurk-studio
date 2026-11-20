"""Scan every reachable workspace/account route for UI text left in English.

Routes are discovered from the URL resolver rather than hard-coded, so the sweep
covers the whole app instead of only the pages I happened to guess. Run inside
the app container:

    docker compose exec -T -e PYTHONPATH=/app app \\
        python apps/ui_zh/management/commands/scan_untranslated.py

Options:
    --save PATH   write the raw report (default: no file)
    --min N       only report strings seen on at least N routes (default 1)
"""

from __future__ import annotations

import argparse
import os
import re

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import get_resolver  # noqa: E402

from apps.ui_zh.middleware import SKIP_BLOCKS, TAG_SPLIT  # noqa: E402

WORKSPACE_UUID = "5ec3442e-37dc-4fb4-9ce4-17f8795319df"

LATIN_LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9 ,.'&/()\-–—:!?+%#]*$")
# Route patterns that need more than a workspace id to be meaningful.
SKIP_PATTERNS = (
    "logout", "password/reset/key", "confirm-email", "reauthenticate",
    "3rdparty", "social/login", "social/signup", "google/login",
    "callback", "inactive", "delete", "revoke", "disconnect",
)


def discover_routes() -> list[str]:
    routes: list[str] = []

    def walk(patterns, prefix=""):
        for p in patterns.url_patterns:
            if hasattr(p, "url_patterns"):
                walk(p, prefix + str(p.pattern))
                continue
            route = prefix + str(p.pattern)
            if route.startswith("admin/"):
                continue
            if any(bad in route for bad in SKIP_PATTERNS):
                continue
            routes.append("/" + route.replace("^", "").replace("$", ""))

    walk(get_resolver())

    concrete = []
    for r in routes:
        if "<" not in r:
            concrete.append(r)
            continue
        # Only fill in ids we can actually supply.
        filled = r
        for token in ("workspace_id", "ws_id", "workspace_pk"):
            filled = re.sub(rf"<[^:>]*{token}[^>]*>", WORKSPACE_UUID, filled)
        if "<" in filled:
            continue
        concrete.append(filled)
    return sorted(set(concrete))


def nodes(html: str) -> list[str]:
    html = SKIP_BLOCKS.sub(" ", html)
    out: list[str] = []
    for part in TAG_SPLIT.split(html):
        if not part or part.startswith("<"):
            continue
        s = " ".join(part.split())
        if not s or not re.search(r"[A-Za-z]", s):
            continue
        if len(s) > 120 or not LATIN_LABEL.match(s):
            continue
        out.append(s)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default=None)
    ap.add_argument("--min", type=int, default=1)
    args = ap.parse_args()

    client = Client()
    user = get_user_model().objects.get(email="owner@example.com")
    client.force_login(user)

    routes = discover_routes()
    seen: dict[str, int] = {}
    where: dict[str, set[str]] = {}
    ok = 0
    bad: list[str] = []

    for route in routes:
        try:
            resp = client.get(route, follow=True)
        except Exception as exc:  # noqa: BLE001 - report, keep sweeping
            bad.append(f"{route}: {exc}")
            continue
        if resp.status_code != 200:
            bad.append(f"{route}: HTTP {resp.status_code}")
            continue
        ok += 1
        html = resp.content.decode("utf-8", "ignore")
        for s in nodes(html):
            seen[s] = seen.get(s, 0) + 1
            where.setdefault(s, set()).add(route)

    lines = []
    lines.append(f"routes discovered={len(routes)} ok={ok} failed={len(bad)}")
    for b in bad:
        lines.append(f"  !! {b}")
    lines.append("")
    lines.append(f"=== {len(seen)} unique untranslated UI strings ===")
    lines.append("")
    for s, n in sorted(seen.items(), key=lambda kv: (kv[1], kv[0])):
        if n < args.min:
            continue
        loc = ",".join(sorted(where[s]))[:70]
        lines.append(f"{n:3d}  {s!r:56s}  {loc}")

    report = "\n".join(lines)
    print(report)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            fh.write(report)


if __name__ == "__main__":
    main()
