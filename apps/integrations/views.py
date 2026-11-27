from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.members.decorators import require_permission, skip_last_workspace_tracking


@skip_last_workspace_tracking
@never_cache
@login_required
@require_permission("manage_workspace_settings")
@require_safe
def github_status(request, workspace_id):
    """Stable status contract; no credentials, installation, or transport yet."""
    if request.workspace.is_archived:
        raise Http404
    return JsonResponse({"provider": "github", "status": "reserved", "connected": False})
