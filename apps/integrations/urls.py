from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("github/status/", views.github_status, name="github_status"),
]
