"""Tests for the per-visitor UI language switcher.

The switcher is a render-time switch, not Django i18n: Chinese runs the
dictionary, English leaves the upstream strings alone (branding still applies).
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from apps.ui_zh import language

pytestmark = pytest.mark.django_db

SWITCH_URL = "/i18n/set-language/"

_ASSET_ATTR = re.compile(r'(?:src|href|action)="[^"]*"')


def _visible_text(html: str) -> str:
    """HTML with asset/URL attributes removed, leaving what a visitor reads."""
    return _ASSET_ATTR.sub("", html)


@pytest.fixture
def client_zh():
    c = Client()
    c.cookies[language.LANGUAGE_COOKIE] = "zh"
    return c


def test_resolve_defaults_to_site_language():
    """No cookie means the site default, so a fresh install reads Chinese."""
    from django.test import RequestFactory

    req = RequestFactory().get("/")
    with override_settings(UI_LANGUAGE="zh-hans"):
        assert language.resolve(req) == "zh"
    with override_settings(UI_LANGUAGE="en"):
        assert language.resolve(req) == "en"


def test_resolve_prefers_cookie_over_site_default():
    from django.test import RequestFactory

    req = RequestFactory().get("/")
    req.COOKIES[language.LANGUAGE_COOKIE] = "en"
    with override_settings(UI_LANGUAGE="zh-hans"):
        assert language.resolve(req) == "en"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en", "en"),
        ("zh", "zh"),
        ("EN", "en"),
        ("en-US", "en"),
        ("zh-hans", "zh"),
        ("zh-CN", "zh"),
        ("fr", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize(raw, expected):
    assert language.normalize(raw) == expected


def test_switch_requires_post():
    """A GET must not change anyone's language (prefetchers, <img>, links)."""
    assert Client().get(SWITCH_URL).status_code == 405


def test_switch_sets_cookie_and_redirects(client):
    resp = client.post(SWITCH_URL, {"lang": "en", "next": "/accounts/login/"})
    assert resp.status_code == 302
    assert resp["Location"] == "/accounts/login/"
    assert resp.cookies[language.LANGUAGE_COOKIE].value == "en"


def test_switch_rejects_unknown_language(client):
    resp = client.post(SWITCH_URL, {"lang": "fr"})
    assert resp.cookies[language.LANGUAGE_COOKIE].value == "zh"


def test_switch_blocks_open_redirect(client):
    resp = client.post(SWITCH_URL, {"lang": "en", "next": "https://evil.example/steal"})
    assert resp["Location"] == "/"


@override_settings(UI_LANGUAGE="zh-hans", BRAND_NAME="Crossborder Shop")
def test_login_page_renders_chinese_by_default(client):
    body = client.get("/accounts/login/").content.decode()
    assert "欢迎回来" in body
    assert "Welcome back" not in body


@override_settings(UI_LANGUAGE="zh-hans", BRAND_NAME="Crossborder Shop")
def test_login_page_renders_english_with_cookie(client):
    client.cookies[language.LANGUAGE_COOKIE] = "en"
    body = client.get("/accounts/login/").content.decode()
    assert "Welcome back" in body
    assert "欢迎回来" not in body
    # White-label still applies in English.
    assert "Crossborder Shop" in body
    # Only visible text must be white-labelled; asset URLs keep the shipped file
    # names, so strip attributes before looking for the built-in brand.
    assert "wanchurk-studio" not in _visible_text(body)


@override_settings(UI_LANGUAGE="zh-hans", BRAND_NAME="Crossborder Shop")
def test_brand_applies_in_both_languages(client):
    for lang in ("zh", "en"):
        client.cookies[language.LANGUAGE_COOKIE] = lang
        body = client.get("/accounts/login/").content.decode()
        assert "Crossborder Shop" in body, f"brand missing in {lang}"
        assert "wanchurk-studio" not in _visible_text(body), f"default brand leaked in {lang}"


@override_settings(UI_LANGUAGE="zh-hans", BRAND_NAME="Crossborder Shop")
def test_switcher_form_is_available_to_logged_in_users(client):
    """The switcher lives in the sidebar user menu on every full app page."""
    from django.utils import timezone

    from apps.members.models import OrgMembership, WorkspaceMembership
    from apps.organizations.models import Organization
    from apps.workspaces.models import Workspace

    user = get_user_model().objects.create_user(
        email="owner@example.com",
        password="pw-for-tests-only",
        tos_accepted_at=timezone.now(),
    )
    org = Organization.objects.create(name="Test Org")
    ws = Workspace.objects.create(organization=org, name="WS")
    OrgMembership.objects.create(user=user, organization=org, org_role=OrgMembership.OrgRole.OWNER)
    WorkspaceMembership.objects.create(
        user=user,
        workspace=ws,
        workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
    )
    client.force_login(user)

    body = client.get(f"/workspace/{ws.id}/calendar/").content.decode()
    assert reverse("ui_zh:set_language") in body
    # Both options render, and the current one is marked active.
    assert "中文" in body and "English" in body


@override_settings(UI_LANGUAGE="zh-hans")
def test_ui_select_placeholder_follows_language(client):
    """The placeholder sits inside Alpine's JS, so the tag translates it."""
    from apps.ui_zh.middleware import lookup

    assert lookup("All Tags") == "全部标签"
    assert lookup("Channels") == "渠道"
    # Unknown strings pass straight through.
    assert lookup("Not A Real Key") == "Not A Real Key"


class FormValuesAreDataNotCopy:
    """Regression: a <option value="..."> must never be rewritten.

    Timezone options carry IANA names as their value. Translating the value
    produced "Europe/阿姆斯特丹", which the server then rejects on save.
    """

    def test_option_value_is_untouched_but_label_is_translated(self):
        from apps.ui_zh.middleware import translate_html

        html = '<option value="Europe/Amsterdam">Europe/Amsterdam</option>'
        out = translate_html(html)
        assert 'value="Europe/Amsterdam"' in out

    def test_timezone_value_contains_no_cjk(self):
        from apps.ui_zh.middleware import translate_html

        html = '<select><option value="America/New_York">America/New_York</option></select>'
        out = translate_html(html)
        import re

        values = re.findall(r'value="([^"]*)"', out)
        self.assertTrue(all(not re.search(r"[\u4e00-\u9fff]", v) for v in values), values)


def test_identifier_option_is_never_translated():
    """A timezone option's label and value must survive byte-for-byte."""
    from apps.ui_zh.middleware import translate_html

    html = '<select><option value="America/New_York">America/New_York</option></select>'
    out = translate_html(html)
    assert '<option value="America/New_York">America/New_York</option>' in out, out


def test_copy_option_is_translated():
    """Sort dropdowns hold copy, not identifiers, so they still translate."""
    from apps.ui_zh.middleware import translate_html

    html = '<select><option value="newest">Newest first</option></select>'
    out = translate_html(html)
    assert "最新优先" in out, out


def test_surrounding_text_still_translated_next_to_an_option():
    from apps.ui_zh.middleware import translate_html

    html = '<button>New</button><select><option value="Europe/Amsterdam">Europe/Amsterdam</option></select>'
    out = translate_html(html)
    assert ">新建</button>" in out, out
    assert 'value="Europe/Amsterdam">Europe/Amsterdam<' in out, out


def test_timezone_identifier_is_never_partially_translated():
    """Dropdown labels outside <option> (the ui_select component) are data too."""
    from apps.ui_zh.middleware import translate_text

    for tz in ("America/New_York", "Europe/Amsterdam", "Etc/GMT+5", "US/Eastern"):
        assert translate_text(tz) == tz, tz


def test_sentence_with_a_slash_still_translates():
    """The timezone guard must not swallow ordinary copy."""
    from apps.ui_zh.middleware import translate_text

    assert translate_text("Save Changes") == "保存修改"
