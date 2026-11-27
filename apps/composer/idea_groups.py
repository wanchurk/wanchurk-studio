"""Shared initialization for the Ideas board and draft creators."""

from django.db import transaction

from apps.workspaces.models import Workspace

from .models import Idea, IdeaGroup

_DEFAULT_COLUMNS = ("Unassigned", "To Do", "In Progress", "Done")


def ensure_idea_groups(workspace_id):
    groups = IdeaGroup.objects.for_workspace(workspace_id).order_by("position", "created_at")
    if groups.exists():
        return groups

    with transaction.atomic():
        # First use can come from the board or a brief. Serialize only the
        # initialization path so concurrent first visits cannot seed twice.
        Workspace.objects.select_for_update().only("id").get(pk=workspace_id)
        if not groups.exists():
            columns = IdeaGroup.objects.bulk_create(
                [
                    IdeaGroup(workspace_id=workspace_id, name=name, position=index)
                    for index, name in enumerate(_DEFAULT_COLUMNS)
                ]
            )
            Idea.objects.create(
                workspace_id=workspace_id,
                group=columns[0],
                title="This is a place to plan \u270d\ufe0f your content",
                description=(
                    "Save your Ideas before converting them into posts. "
                    "Brainstorm, plan ahead, and keep everything organized in one place."
                ),
                status=Idea.Status.UNASSIGNED,
                position=0,
            )
    return groups
