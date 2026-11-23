from django.urls import path

from . import views

app_name = "legal"

urlpatterns = [
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("acceptable-use/", views.acceptable_use, name="acceptable_use"),
    path("cookies/", views.cookies, name="cookies"),
    path("", views.index, name="index"),
]
