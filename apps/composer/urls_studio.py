from django.urls import path

from .studio import create_brief

app_name = "studio"

urlpatterns = [
    path("video/", create_brief, {"kind": "video"}, name="video"),
    path("image/", create_brief, {"kind": "image"}, name="image"),
]
