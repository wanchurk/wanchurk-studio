"""The profile page shows the email read-only; changing it goes through allauth.

Without a link the email manager at ``/accounts/email/`` is unreachable from the
UI, which is how it shipped: the page printed the address as plain text and
nothing in the product pointed at the manager.
"""

import pytest
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def user_with_tos(db, django_user_model):
    return django_user_model.objects.create_user(
        email="a@example.com", password="pw12345678", tos_accepted_at=timezone.now()
    )


@pytest.mark.django_db
def test_the_email_row_links_to_the_email_manager(client, user_with_tos):
    client.force_login(user_with_tos)
    body = client.get(reverse("accounts:settings")).content.decode()
    assert f'href="{reverse("account_email")}"' in body


@pytest.mark.django_db
def test_the_link_is_labelled_in_chinese(client, user_with_tos, settings):
    settings.UI_LANGUAGE = "zh-hans"
    client.force_login(user_with_tos)
    body = client.get(reverse("accounts:settings")).content.decode()
    assert ">修改<" in body
