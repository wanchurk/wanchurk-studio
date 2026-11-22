"""URL routes for the language switcher."""

from django.urls import path
from django.views.i18n import JavaScriptCatalog

from apps.ui_zh import language

app_name = "ui_zh"

urlpatterns = [
    path("set-language/", language.switch_view, name="set_language"),
    # Exposes gettext() to Alpine expressions so client-side copy goes through
    # the same catalog as server-rendered copy instead of a word map.
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript_catalog"),
]
