"""
Tests for the stats app.

Covers: StatsView (staff-only dashboard) and stats_data (JSON endpoint).
All view tests use hardcoded URL paths because the stats URLs are not yet
registered in the root URLconf.

Test class:
  TestStatsViews — access control and JSON shape for /stats/dashboard/ and /stats/data/
"""

import pytest
from django.test import Client

from conftest import CategoryFactory, HelpRequestFactory, UserFactory


# ===================================================================
# STATS VIEW TESTS
# ===================================================================


class TestStatsViews:
    """Access-control and response-shape tests for the stats app views."""

    # ------------------------------------------------------------------
    # /stats/dashboard/
    # ------------------------------------------------------------------

    @pytest.mark.django_db
    def test_dashboard_as_staff(self):
        """Staff user receives 200 OK on the dashboard."""
        # Arrange
        staff_user = UserFactory(is_staff=True)
        client = Client()
        client.force_login(staff_user)

        # Act
        response = client.get("/stats/dashboard/")

        # Assert
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_dashboard_as_non_staff(self, client_logged_in_volunteer):
        """Authenticated non-staff user receives 403 Forbidden on the dashboard."""
        # Arrange — client_logged_in_volunteer is a logged-in volunteer (non-staff)

        # Act
        response = client_logged_in_volunteer.get("/stats/dashboard/")

        # Assert
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_dashboard_unauthenticated(self):
        """Anonymous user is redirected (302) to the login page."""
        # Arrange
        anon_client = Client()

        # Act
        response = anon_client.get("/stats/dashboard/")

        # Assert
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_dashboard_category_labels_are_json_escaped(self):
        """Chart data is emitted via json_script so labels with HTML/JS
        special characters cannot break out of the <script> context (XSS-safe)."""
        # Arrange — a malicious category name containing a closing script tag
        staff_user = UserFactory(is_staff=True)
        malicious_name = "</script><img src=x onerror=alert(1)>"
        category = CategoryFactory(name=malicious_name, slug="xss-category")
        HelpRequestFactory(category=category)
        client = Client()
        client.force_login(staff_user)

        # Act
        response = client.get("/stats/dashboard/")

        # Assert
        assert response.status_code == 200
        content = response.content.decode()
        # json_script renders a dedicated, escaped data island
        assert 'id="category-labels-data"' in content
        # The raw closing tag must never appear unescaped in the response
        assert "</script><img src=x onerror=alert(1)>" not in content

    # ------------------------------------------------------------------
    # /stats/data/
    # ------------------------------------------------------------------

    @pytest.mark.django_db
    def test_stats_data_json(self):
        """Staff user receives 200 JSON response with 'statuses' and 'categories' keys."""
        # Arrange
        staff_user = UserFactory(is_staff=True)
        client = Client()
        client.force_login(staff_user)

        # Act
        response = client.get("/stats/data/")

        # Assert — status and content type
        assert response.status_code == 200
        assert "application/json" in response["Content-Type"]

        # Assert — required top-level keys are present in the payload
        payload = response.json()
        assert "statuses" in payload
        assert "categories" in payload

    @pytest.mark.django_db
    def test_stats_data_non_staff(self, client_logged_in_volunteer):
        """Authenticated non-staff user receives 403 Forbidden on the JSON endpoint."""
        # Arrange — client_logged_in_volunteer is a logged-in volunteer (non-staff)

        # Act
        response = client_logged_in_volunteer.get("/stats/data/")

        # Assert
        assert response.status_code == 403
