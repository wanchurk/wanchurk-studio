"""Capture creative briefs without triggering a generation or external request."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.members.decorators import require_permission
from apps.ui_zh.language import is_chinese
from apps.ui_zh.middleware import lookup

from .idea_groups import ensure_idea_groups
from .models import Idea

_COMMON_RATIOS = (("9:16", "9:16"), ("1:1", "1:1"), ("16:9", "16:9"))
_STUDIO_TYPES = {
    "video": (
        "AI Video",
        "Plan a product video: write the hook, shot sequence and ending before you generate it.",
        "Example: Open with the bag on a train seat, show what fits inside, then end with a close-up of the zipper.",
        _COMMON_RATIOS,
    ),
    "image": (
        "AI Image",
        "Plan a product image: describe its placement, background, lighting and details to preserve.",
        "Example: Place the bag on a warm white background with soft side lighting. Keep the stitching and logo unchanged.",
        (("4:5", "4:5"), *_COMMON_RATIOS),
    ),
}


class CreativeBriefForm(forms.Form):
    title = forms.CharField(label=_("Title"), max_length=140)
    aspect_ratio = forms.ChoiceField(label=_("Aspect ratio"))
    direction = forms.CharField(label=_("Creative brief"), max_length=6000, widget=forms.Textarea(attrs={"rows": 6}))

    def __init__(self, *args, kind, **kwargs):
        super().__init__(*args, **kwargs)
        _, _, example, ratios = _STUDIO_TYPES[kind]
        self.fields["aspect_ratio"].choices = ratios
        self.fields["direction"].widget.attrs["placeholder"] = example


@login_required
@require_permission("create_posts")
@require_http_methods(["GET", "HEAD", "POST"])
def create_brief(request, workspace_id, kind):
    title, intro, _, _ = _STUDIO_TYPES[kind]
    brief_form = CreativeBriefForm(request.POST if request.method == "POST" else None, kind=kind)
    if request.method == "POST" and brief_form.is_valid():
        data = brief_form.cleaned_data
        group = ensure_idea_groups(workspace_id).first()
        # Idea text is user data after it is saved. Localise the metadata once,
        # without translating or sending the creator's free text anywhere.
        kind_label = lookup(title) if is_chinese(request) else title
        Idea.objects.create(
            workspace_id=workspace_id,
            author=request.user,
            group=group,
            title=data["title"],
            description=f"{kind_label} · {data['aspect_ratio']}\n\n{data['direction']}",
        )
        messages.success(request, "Brief saved to Ideas. No generation was started.")
        return redirect(f"studio:{kind}", workspace_id=workspace_id)
    return render(
        request,
        "composer/studio.html",
        {"workspace_id": workspace_id, "brief_form": brief_form, "kind": kind, "studio_title": title, "intro": intro},
    )
