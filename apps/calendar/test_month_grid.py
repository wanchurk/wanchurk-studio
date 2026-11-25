"""The month grid must render every week of the month.

A month can span six Monday-first week rows (November 2026 starts on a Sunday
and ends on a Monday, so it needs six). The grid used a fixed per-cell
min-height, so six rows overflowed the calendar pane and the last week sat
below the fold until the user scrolled.

These tests cover the rendered output: every date in the grid appears once,
including the last day of the month, and the cell count matches the number of
weeks the calendar says the month has.

They guard the data the grid is built from. Whether six rows fit on screen is
a layout property, checked in a browser rather than here.
"""

import calendar as cal_mod
import re
from datetime import UTC, datetime

from django.test import TestCase

from apps.accounts.models import User
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace


def _week_count(year: int, month: int) -> int:
    """Monday-first week rows the month needs."""
    return len(cal_mod.Calendar(firstweekday=0).monthdatescalendar(year, month))


class MonthGridRowsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="grid@example.com",
            password="pw-for-tests-only",
            # The TOS middleware redirects an unaccepted user away from every
            # page, so a fixture that omits this never reaches the calendar.
            tos_accepted_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.org = Organization.objects.create(name="Grid Org")
        OrgMembership.objects.create(user=self.user, organization=self.org, org_role="owner")
        self.workspace = Workspace.objects.create(organization=self.org, name="Grid WS")
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            workspace_role="admin",
        )
        self.client.force_login(self.user)

    def _month_body(self, year, month):
        response = self.client.get(
            f"/workspace/{self.workspace.id}/calendar/",
            {
                "mode": "calendar",
                "view": "month",
                "date": f"{year}-{month:02d}-01",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _rendered_dates(self, body):
        return re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"', body)

    def test_six_week_month_renders_every_day_including_the_last(self):
        """November 2026 needs six rows; 30 Nov must be in the output."""
        self.assertEqual(_week_count(2026, 11), 6)
        dates = self._rendered_dates(self._month_body(2026, 11))
        self.assertIn("2026-11-30", dates)
        self.assertEqual(len(dates), 6 * 7)

    def test_five_week_month_renders_every_day(self):
        """A month that fits five rows renders five rows, not six."""
        self.assertEqual(_week_count(2026, 9), 5)
        dates = self._rendered_dates(self._month_body(2026, 9))
        self.assertIn("2026-09-30", dates)
        self.assertEqual(len(dates), 5 * 7)

    def test_each_rendered_day_is_unique(self):
        dates = self._rendered_dates(self._month_body(2026, 11))
        self.assertEqual(len(dates), len(set(dates)))
