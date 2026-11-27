"""Workspace navigation and operations, including access boundaries."""

import re
from html import escape

import pytest
from django.test import Client
from django.urls import reverse

from apps.commerce.models import SupportConversation
from apps.composer.models import Idea, IdeaGroup
from apps.members.models import CustomRole, WorkspaceMembership
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def ops_workspace(client, org_owner, organization):
    workspace = Workspace.objects.create(name="Operations test", organization=organization)
    WorkspaceMembership.objects.create(user=org_owner, workspace=workspace, workspace_role="manager")
    client.force_login(org_owner)
    return workspace


@pytest.fixture
def triage_conversation(ops_workspace):
    return SupportConversation.objects.create(
        workspace=ops_workspace, platform="amazon", shop_name="Shop", subject="Question", body="Original"
    )


def _triage_revision(response):
    field = re.search(r'<input type="hidden" name="revision" value="(\d+)"', response.content.decode())
    assert field, "Expected a hidden triage revision"
    return int(field[1])


def test_commerce_inbox_starts_with_an_explicit_manual_intake_state(client, ops_workspace):
    url = f"/workspace/{ops_workspace.pk}/commerce/inbox/"
    client.cookies["ui_lang"] = "zh"
    response = client.get(url)
    assert response.status_code == 200
    assert "电商客服信箱" in response.content.decode()
    assert "未连接平台" in response.content.decode()
    assert "暂无待处理会话" in response.content.decode()
    assert ':title="emoji.n"' in response.content.decode()
    assert "发送回复" not in response.content.decode()


def test_commerce_sidebar_keeps_social_inbox_separate(client, ops_workspace):
    response = client.get(reverse("calendar:calendar", kwargs={"workspace_id": ops_workspace.pk}))
    html = response.content.decode()
    assert 'data-workspace-section="social"' in html
    assert 'data-workspace-section="commerce"' in html
    assert f'href="/workspace/{ops_workspace.pk}/inbox/"' in html
    assert f'href="/workspace/{ops_workspace.pk}/commerce/inbox/"' in html


def test_manual_buyer_conversation_keeps_a_draft_and_can_be_resolved(client, ops_workspace, org_owner):
    root = f"/workspace/{ops_workspace.pk}/commerce/inbox/"
    response = client.post(
        f"{root}new/",
        {
            "platform": "tiktok_shop",
            "shop_name": "Preview Shop",
            "subject": "Bag colour question",
            "buyer_alias": "Sample Buyer",
            "order_reference": "SAMPLE-014",
            "body": "Does the bag come in green? <script>plain input</script>",
        },
    )
    assert response.status_code == 302
    record = SupportConversation.objects.get(workspace=ops_workspace)
    assert record.created_by == org_owner
    assert response.url == f"{root}{record.pk}/"
    detail = client.get(response.url)
    assert "&lt;script&gt;plain input&lt;/script&gt;" in detail.content.decode()
    assert "SAMPLE-014" in detail.content.decode()
    updated = client.post(
        f"{response.url}update/",
        {"revision": _triage_revision(detail), "status": "resolved", "reply_draft": "Yes, in olive green."},
    )
    assert updated.status_code == 302
    record.refresh_from_db()
    assert record.status == "resolved"
    assert record.reply_draft == "Yes, in olive green."
    assert "Bag colour question" not in client.get(root).content.decode()
    assert "Bag colour question" in client.get(f"{root}?status=resolved").content.decode()


def test_stale_commerce_triage_requires_review_before_saving_again(client, ops_workspace, triage_conversation):
    record = triage_conversation
    args = {"workspace_id": ops_workspace.pk, "conversation_id": record.pk}
    detail = reverse("commerce:conversation", kwargs=args)
    update = reverse("commerce:update", kwargs=args)
    client.cookies["ui_lang"] = "zh"

    first_revision = _triage_revision(client.get(detail))
    second_revision = _triage_revision(client.get(detail))
    assert first_revision == second_revision == 1

    saved_draft = "Saved in the first tab."
    first = client.post(update, {"revision": first_revision, "status": "resolved", "reply_draft": saved_draft})
    assert first.status_code == 302
    record.refresh_from_db()
    assert (record.reply_draft, record.status) == (saved_draft, "resolved")
    saved_at = record.updated_at

    submitted_draft = "Typed in the second tab.\n<draft>Keep this line.</draft>"
    stale = client.post(update, {"revision": second_revision, "status": "open", "reply_draft": submitted_draft})
    record.refresh_from_db()
    assert (stale.status_code, record.reply_draft, record.status) == (409, saved_draft, "resolved")
    assert record.updated_at == saved_at

    html = stale.content.decode()
    assert "此会话已有更新，您的修改未保存。" in html
    assert "您未保存的回复草稿" in html
    assert f"<pre>{escape(submitted_draft)}</pre>" in html
    assert html.count(escape(submitted_draft)) == 1
    assert saved_draft in html
    current_form = stale.context["triage_form"]
    assert current_form["reply_draft"].value() == saved_draft
    assert current_form["status"].value() == "resolved"
    current_revision = _triage_revision(stale)
    assert current_revision == first_revision + 1

    retry = client.post(update, {"revision": current_revision, "status": "open", "reply_draft": submitted_draft})
    assert retry.status_code == 302
    record.refresh_from_db()
    assert (record.reply_draft, record.status) == (submitted_draft, "open")


@pytest.mark.parametrize("revision", [None, "not-a-version", "0", str(2**63)])
def test_commerce_triage_rejects_invalid_revision(client, ops_workspace, triage_conversation, revision):
    record = triage_conversation
    url = reverse("commerce:update", kwargs={"workspace_id": ops_workspace.pk, "conversation_id": record.pk})
    data = {"status": "resolved", "reply_draft": "Keep my unsaved draft."}
    if revision is not None:
        data["revision"] = revision
    client.cookies["ui_lang"] = "zh"
    response = client.post(url, data)
    assert response.status_code == 422
    assert response.context["triage_form"].has_error("revision")
    html = response.content.decode()
    assert "请重新打开此会话后再保存。" in html
    assert data["reply_draft"] in html
    record.refresh_from_db()
    assert (record.reply_draft, record.status) == ("", "open")


def test_invalid_commerce_triage_keeps_the_submitted_revision(client, ops_workspace, triage_conversation):
    record = triage_conversation
    args = {"workspace_id": ops_workspace.pk, "conversation_id": record.pk}
    revision = _triage_revision(client.get(reverse("commerce:conversation", kwargs=args)))
    update = reverse("commerce:update", kwargs=args)
    saved_draft = "Latest saved draft."
    saved = client.post(update, {"revision": revision, "status": "resolved", "reply_draft": saved_draft})
    assert saved.status_code == 302

    response = client.post(
        update, {"revision": revision, "status": "invalid", "reply_draft": "Draft with a validation error."}
    )
    assert response.status_code == 422
    assert response.context["triage_form"].has_error("status")
    assert "Draft with a validation error." in response.content.decode()
    assert _triage_revision(response) == revision
    record.refresh_from_db()
    assert (record.reply_draft, record.status) == (saved_draft, "resolved")


def test_commerce_cannot_open_or_update_other_workspace_conversation(client, ops_workspace, org_owner):
    other = Workspace.objects.create(name="Other workspace", organization=ops_workspace.organization)
    WorkspaceMembership.objects.create(user=org_owner, workspace=other, workspace_role="manager")
    record = SupportConversation.objects.create(
        workspace=other, platform="amazon", shop_name="Separate shop", subject="Separate message", body="Original"
    )
    url = f"/workspace/{ops_workspace.pk}/commerce/inbox/{record.pk}/"
    assert client.get(url).status_code == 404
    assert client.post(f"{url}update/", {"status": "resolved", "revision": record.revision}).status_code == 404
    record.refresh_from_db()
    assert record.status == SupportConversation.Status.OPEN


def test_viewer_does_not_get_commerce_navigation_or_access(client, ops_workspace, org_owner):
    WorkspaceMembership.objects.filter(user=org_owner, workspace=ops_workspace).update(workspace_role="viewer")
    response = client.get(reverse("calendar:calendar", kwargs={"workspace_id": ops_workspace.pk}))
    assert 'data-workspace-section="commerce"' not in response.content.decode()
    assert 'data-workspace-section="creative"' not in response.content.decode()
    assert client.get(f"/workspace/{ops_workspace.pk}/commerce/inbox/").status_code == 403
    url = reverse("studio:video", kwargs={"workspace_id": ops_workspace.pk})
    assert client.get(url).status_code == 403
    assert client.post(url, {"title": "Not allowed", "aspect_ratio": "9:16", "direction": "Draft"}).status_code == 403


def test_compose_module_uses_workspace_ideas_instead_of_submitting_a_generation(client, ops_workspace):
    root = f"/workspace/{ops_workspace.pk}/studio/"
    client.cookies["ui_lang"] = "zh"
    for kind, heading in (("video", "AI 视频"), ("image", "AI 图片")):
        url = f"{root}{kind}/"
        response = client.get(url)
        assert response.status_code == 200
        html = response.content.decode()
        assert heading in html
        assert f"/media/?type={kind}" in html
        assert 'data-workspace-section="creative" open' in html
        assert "未接入生成服务" in html
        response = client.post(
            url, {"title": f"Weekend {kind}", "aspect_ratio": "9:16", "direction": "Keep one green bag."}
        )
        assert response.status_code == 302
        idea = Idea.objects.for_workspace(ops_workspace.pk).get(title=f"Weekend {kind}")
        assert heading in idea.description
        assert "9:16" in idea.description
        assert "Keep one green bag." in idea.description


def test_first_creative_brief_is_visible_in_an_uninitialized_ideas_board(client, ops_workspace):
    assert not IdeaGroup.objects.for_workspace(ops_workspace.pk).exists()
    url = reverse("studio:video", kwargs={"workspace_id": ops_workspace.pk})
    response = client.post(url, {"title": "First board entry", "aspect_ratio": "9:16", "direction": "Film the zipper."})
    assert response.status_code == 302
    board = client.get(reverse("composer:create_landing", kwargs={"workspace_id": ops_workspace.pk}))
    assert board.status_code == 200
    assert "First board entry" in board.content.decode()
    assert IdeaGroup.objects.for_workspace(ops_workspace.pk).count() == 4


def test_commerce_read_only_custom_role_cannot_create_or_triage(client, ops_workspace, org_owner):
    role = CustomRole.objects.create(
        organization=ops_workspace.organization, name="Can read conversations", permissions={"use_inbox": True}
    )
    WorkspaceMembership.objects.filter(user=org_owner, workspace=ops_workspace).update(custom_role=role)
    record = SupportConversation.objects.create(
        workspace=ops_workspace, platform="shopee", shop_name="Shop", subject="Question", body="Original"
    )
    base = {"workspace_id": ops_workspace.pk}
    args = {**base, "conversation_id": record.pk}
    page = client.get(reverse("commerce:conversation", kwargs=args))
    assert page.status_code == 200
    body = page.content.decode()
    assert "Original" in body
    assert 'name="reply_draft"' not in body
    assert 'name="revision"' not in body
    assert client.get(reverse("commerce:create", kwargs=base)).status_code == 403
    update = client.post(reverse("commerce:update", kwargs=args), {"status": "resolved", "revision": record.revision})
    assert update.status_code == 403
    record.refresh_from_db()
    assert record.status == SupportConversation.Status.OPEN


def test_mutations_require_csrf_and_get_does_not_update(client, ops_workspace, org_owner):
    client = Client(enforce_csrf_checks=True)
    client.force_login(org_owner)
    args = {"workspace_id": ops_workspace.pk}
    record = SupportConversation.objects.create(
        workspace=ops_workspace, platform="amazon", shop_name="Shop", subject="Question", body="Question body"
    )
    update = reverse("commerce:update", kwargs={**args, "conversation_id": record.pk})
    assert client.get(update).status_code == 405
    assert client.post(update, {"status": "resolved", "revision": record.revision}).status_code == 403
    for url in (reverse("commerce:create", kwargs=args), reverse("studio:image", kwargs=args)):
        assert client.post(url, {}).status_code == 403
    record.refresh_from_db()
    assert record.status == SupportConversation.Status.OPEN


def test_invalid_conversation_and_brief_values_do_not_write(client, ops_workspace):
    args = {"workspace_id": ops_workspace.pk}
    response = client.post(
        reverse("commerce:create", kwargs=args),
        {"platform": "invalid", "shop_name": "Shop", "subject": "Title", "body": "Original"},
    )
    assert "platform" in response.context["form"].errors
    assert not SupportConversation.objects.for_workspace(ops_workspace.pk).exists()
    response = client.post(
        reverse("studio:video", kwargs=args), {"title": "Title", "aspect_ratio": "4:5", "direction": "Draft"}
    )
    assert "aspect_ratio" in response.context["brief_form"].errors
    assert not Idea.objects.for_workspace(ops_workspace.pk).exists()
