from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("new/", views.create, name="create"),
    path("<uuid:conversation_id>/", views.inbox, name="conversation"),
    path("<uuid:conversation_id>/update/", views.update, name="update"),
]
