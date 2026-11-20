"""URL routes for the language switcher."""

from django.urls import path

from apps.ui_zh import language

app_name = "ui_zh"

urlpatterns = [
    path("set-language/", language.switch_view, name="set_language"),
]
