"""Reserved integrations expose status, never imply an active connection."""

import pytest
from django.urls import reverse

from apps.members.models import CustomRole, WorkspaceMembership
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace_membership(organization, org_owner):
    workspace = Workspace.objects.create(organization=organization, name="Integrations test")
    return WorkspaceMembership.objects.create(
        workspace=workspace, user=org_owner, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )


@pytest.fixture
def github_status_url(workspace_membership):
    return f"/workspace/{workspace_membership.workspace_id}/integrations/github/status/"


@pytest.fixture
def previous_workspace_id(organization, org_owner):
    previous_workspace = Workspace.objects.create(organization=organization, name="Previously visited")
    WorkspaceMembership.objects.create(
        workspace=previous_workspace, user=org_owner, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    org_owner.last_workspace_id = previous_workspace.pk
    org_owner.save(update_fields=["last_workspace_id"])
    return previous_workspace.pk


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_github_status_is_explicitly_reserved(client, org_owner, github_status_url, previous_workspace_id, method):
    client.force_login(org_owner)
    response = client.generic(method, github_status_url)
    assert response.status_code == 200
    org_owner.refresh_from_db(fields=["last_workspace_id"])
    assert org_owner.last_workspace_id == previous_workspace_id
    if method == "GET":
        assert response.json() == {"provider": "github", "status": "reserved", "connected": False}
    else:
        assert response.content == b""
    assert "no-store" in response["Cache-Control"]


def test_github_status_requires_login(client, github_status_url):
    response = client.get(github_status_url)
    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={github_status_url}"


def test_github_status_rejects_a_member_of_a_different_workspace(client, org_owner, organization, workspace_membership):
    org_owner.last_workspace_id = workspace_membership.workspace_id
    org_owner.save(update_fields=["last_workspace_id"])
    client.force_login(org_owner)
    another = Workspace.objects.create(organization=organization, name="No membership")
    assert client.get(f"/workspace/{another.pk}/integrations/github/status/").status_code == 403


@pytest.mark.parametrize("role", [WorkspaceMembership.WorkspaceRole.VIEWER, WorkspaceMembership.WorkspaceRole.EDITOR])
def test_github_status_requires_workspace_settings_permission(
    client, org_owner, workspace_membership, github_status_url, previous_workspace_id, role
):
    workspace_membership.workspace_role = role
    workspace_membership.save(update_fields=["workspace_role"])
    client.force_login(org_owner)
    assert client.get(github_status_url).status_code == 403
    org_owner.refresh_from_db(fields=["last_workspace_id"])
    assert org_owner.last_workspace_id == previous_workspace_id


def test_github_status_accepts_explicit_custom_role_permission(
    client, org_owner, organization, workspace_membership, github_status_url
):
    workspace_membership.workspace_role = WorkspaceMembership.WorkspaceRole.VIEWER
    workspace_membership.custom_role = CustomRole.objects.create(
        organization=organization, name="Integration admin", permissions={"manage_workspace_settings": True}
    )
    workspace_membership.save(update_fields=["workspace_role", "custom_role"])
    client.force_login(org_owner)
    assert client.get(github_status_url).status_code == 200


def test_github_status_is_not_available_for_archived_workspaces(
    client, org_owner, workspace_membership, github_status_url, previous_workspace_id
):
    workspace = workspace_membership.workspace
    workspace.is_archived = True
    workspace.save(update_fields=["is_archived"])
    client.force_login(org_owner)
    assert client.get(github_status_url).status_code == 404
    org_owner.refresh_from_db(fields=["last_workspace_id"])
    assert org_owner.last_workspace_id == previous_workspace_id


def test_github_status_does_not_accept_connection_commands(client, org_owner, github_status_url, previous_workspace_id):
    client.force_login(org_owner)
    response = client.post(github_status_url, {"action": "connect"})
    assert response.status_code == 405
    org_owner.refresh_from_db(fields=["last_workspace_id"])
    assert org_owner.last_workspace_id == previous_workspace_id
    assert set(response["Allow"].split(", ")) == {"GET", "HEAD"}


def test_workspace_settings_navigation_tracks_last_workspace(
    client, org_owner, workspace_membership, previous_workspace_id
):
    client.force_login(org_owner)
    url = reverse("workspaces:settings", kwargs={"workspace_id": workspace_membership.workspace_id})
    assert previous_workspace_id != workspace_membership.workspace_id
    assert client.get(url).status_code == 200
    org_owner.refresh_from_db(fields=["last_workspace_id"])
    assert org_owner.last_workspace_id == workspace_membership.workspace_id
