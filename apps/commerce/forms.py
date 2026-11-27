from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SupportConversation


class ConversationForm(forms.ModelForm):
    class Meta:
        model = SupportConversation
        fields = ("platform", "shop_name", "subject", "buyer_alias", "order_reference", "body")
        labels = {
            "platform": _("Platform"),
            "shop_name": _("Shop name"),
            "subject": _("Subject"),
            "buyer_alias": _("Buyer alias"),
            "order_reference": _("Order reference"),
            "body": _("Buyer message"),
        }
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}


class TriageForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=1, max_value=2**63 - 1, widget=forms.HiddenInput)

    class Meta:
        model = SupportConversation
        fields = ("reply_draft", "status")
        labels = {"reply_draft": _("Reply draft"), "status": _("Conversation status")}
        widgets = {"reply_draft": forms.Textarea(attrs={"rows": 4})}
