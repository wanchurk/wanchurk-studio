from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.members.decorators import membership_permissions, require_permission

from .forms import ConversationForm, TriageForm
from .models import SupportConversation


def _render_inbox(request, workspace_id, *, selected=None, triage_form=None, conflict_draft=None, response_status=200):
    conversations = SupportConversation.objects.for_workspace(workspace_id)
    can_triage = membership_permissions(request).get("reply_from_inbox", False)
    if selected is not None and can_triage and triage_form is None:
        triage_form = TriageForm(instance=selected, initial={"revision": selected.revision})
    platform = request.GET.get("platform", "")
    if platform in SupportConversation.Platform.values:
        conversations = conversations.filter(platform=platform)
    else:
        platform = ""

    status = request.GET.get("status", selected.status if selected else SupportConversation.Status.OPEN)
    if status not in {"all", *SupportConversation.Status.values}:
        status = SupportConversation.Status.OPEN
    counts = conversations.aggregate(
        open=Count("id", filter=Q(status=SupportConversation.Status.OPEN)),
        resolved=Count("id", filter=Q(status=SupportConversation.Status.RESOLVED)),
    )
    if status != "all":
        conversations = conversations.filter(status=status)
    page = Paginator(conversations, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "commerce/inbox.html",
        {
            "workspace_id": workspace_id,
            "selected": selected,
            "status": status,
            "platform": platform,
            "platform_choices": SupportConversation.Platform.choices,
            "counts": counts,
            "page": page,
            "can_triage": can_triage,
            "triage_form": triage_form,
            "conflict_draft": conflict_draft,
        },
        status=response_status,
    )


@login_required
@require_permission("use_inbox")
@require_safe
def inbox(request, workspace_id, conversation_id=None):
    selected = None
    if conversation_id is not None:
        selected = get_object_or_404(SupportConversation.objects.for_workspace(workspace_id), pk=conversation_id)
    return _render_inbox(request, workspace_id, selected=selected)


@login_required
@require_permission("use_inbox")
@require_permission("reply_from_inbox")
@require_http_methods(["GET", "HEAD", "POST"])
def create(request, workspace_id):
    form = ConversationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        conversation = form.save(commit=False)
        conversation.workspace_id = workspace_id
        conversation.created_by = request.user
        conversation.save()
        return redirect("commerce:conversation", workspace_id=workspace_id, conversation_id=conversation.pk)
    return render(request, "commerce/create.html", {"workspace_id": workspace_id, "form": form})


@login_required
@require_permission("use_inbox")
@require_permission("reply_from_inbox")
@require_POST
def update(request, workspace_id, conversation_id):
    target = SupportConversation.objects.for_workspace(workspace_id).filter(pk=conversation_id)
    form = TriageForm(request.POST, instance=get_object_or_404(target))
    if not form.is_valid():
        # Validation can mutate the form's instance; show the saved values alongside the bound form.
        return _render_inbox(
            request, workspace_id, selected=get_object_or_404(target), triage_form=form, response_status=422
        )

    data = form.cleaned_data
    saved = target.filter(revision=data["revision"]).update(
        reply_draft=data["reply_draft"],
        status=data["status"],
        updated_at=timezone.now(),
        revision=F("revision") + 1,
    )
    if saved:
        return redirect("commerce:conversation", workspace_id=workspace_id, conversation_id=conversation_id)

    return _render_inbox(
        request,
        workspace_id,
        selected=get_object_or_404(target),
        conflict_draft=request.POST.get("reply_draft", ""),
        response_status=409,
    )
