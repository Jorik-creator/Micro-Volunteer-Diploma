"""
Tests for the requests app.

Covers:
  Models       — Category, HelpRequest, Response (str, defaults, ordering, constraints)
  Utils        — haversine_distance, offset_coordinates
  Forms        — HelpRequestForm validation, FilterForm, ResponseForm
  Views        — list, detail, create, update, respond, accept, reject, complete, cancel
  Management   — expire_requests command
"""

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta

from apps.requests.models import Category, HelpRequest, Response
from apps.requests.utils import haversine_distance, offset_coordinates

from conftest import (
    CategoryFactory,
    HelpRequestFactory,
    RecipientFactory,
    ResponseFactory,
    VolunteerFactory,
)


# ===================================================================
# CATEGORY MODEL TESTS
# ===================================================================


class TestCategoryModel:
    """Tests for the Category model."""

    def test_category_str(self, category):
        """Category __str__ returns its name."""
        assert str(category) == category.name

    def test_category_slug_unique(self, category, db):
        """Category slug must be unique."""
        with pytest.raises(Exception):
            CategoryFactory(slug=category.slug)

    def test_category_ordering(self, db):
        """Categories are ordered alphabetically by name."""
        c_b = CategoryFactory(name="Бета", slug="beta")
        c_a = CategoryFactory(name="Альфа", slug="alpha")
        categories = list(Category.objects.filter(slug__in=["alpha", "beta"]))
        assert categories[0] == c_a  # Альфа before Бета


# ===================================================================
# HELP REQUEST MODEL TESTS
# ===================================================================


class TestHelpRequestModel:
    """Tests for the HelpRequest model."""

    def test_help_request_str(self, help_request):
        """HelpRequest __str__ returns title with status."""
        expected = f"{help_request.title} (Активний)"
        assert str(help_request) == expected

    def test_help_request_default_status(self, db):
        """New HelpRequest defaults to 'active' status."""
        hr = HelpRequestFactory()
        assert hr.status == HelpRequest.Status.ACTIVE

    def test_help_request_default_urgency(self, db):
        """New HelpRequest defaults to 'medium' urgency."""
        hr = HelpRequestFactory()
        assert hr.urgency == HelpRequest.Urgency.MEDIUM

    def test_help_request_ordering(self, db):
        """HelpRequests are ordered by -created_at (newest first)."""
        hr1 = HelpRequestFactory(title="First")
        hr2 = HelpRequestFactory(title="Second")
        requests = list(HelpRequest.objects.filter(title__in=["First", "Second"]))
        assert requests[0] == hr2  # Second created → first in queryset

    def test_volunteers_needed_default(self, help_request):
        """Default volunteers_needed is 1."""
        assert help_request.volunteers_needed == 1


# ===================================================================
# RESPONSE MODEL TESTS
# ===================================================================


class TestResponseModel:
    """Tests for the Response (volunteer response) model."""

    def test_response_str(self, volunteer_response):
        """Response __str__ returns volunteer → request title (status)."""
        r = volunteer_response
        assert str(r.volunteer) in str(r)
        assert r.help_request.title in str(r)

    def test_response_default_status(self, volunteer_response):
        """New Response defaults to 'pending' status."""
        assert volunteer_response.status == Response.Status.PENDING

    def test_unique_together_constraint(self, volunteer_response, db):
        """Cannot create two responses from the same volunteer to the same request."""
        with pytest.raises(IntegrityError):
            Response.objects.create(
                help_request=volunteer_response.help_request,
                volunteer=volunteer_response.volunteer,
                status=Response.Status.PENDING,
            )


# ===================================================================
# UTILS TESTS — Haversine Distance
# ===================================================================


class TestHaversineDistance:
    """Tests for the haversine_distance utility function."""

    def test_same_point_returns_zero(self):
        """Distance between the same point is 0."""
        distance = haversine_distance(50.4501, 30.5234, 50.4501, 30.5234)
        assert distance == 0.0

    def test_known_distance_kyiv_to_lviv(self):
        """Distance Kyiv → Lviv is approximately 470 km."""
        distance = haversine_distance(50.4501, 30.5234, 49.8397, 24.0297)
        assert 460 < distance < 480

    def test_known_distance_short(self):
        """Short distance (~1 km) is calculated correctly."""
        distance = haversine_distance(50.4501, 30.5234, 50.4591, 30.5234)
        assert 0.5 < distance < 1.5

    def test_antipodal_points(self):
        """Distance between antipodal points is approximately half Earth circumference."""
        distance = haversine_distance(0, 0, 0, 180)
        assert 20000 < distance < 20100


class TestOffsetCoordinates:
    """Tests for the offset_coordinates privacy function."""

    def test_offset_returns_different_coordinates(self):
        """Offset coordinates differ from original."""
        lat, lon = 50.4501, 30.5234
        new_lat, new_lon = offset_coordinates(lat, lon, offset_meters=100)
        assert (new_lat, new_lon) != (lat, lon)

    def test_offset_stays_within_range(self):
        """Offset coordinates stay within expected range (~100m)."""
        lat, lon = 50.4501, 30.5234
        new_lat, new_lon = offset_coordinates(lat, lon, offset_meters=100)
        assert abs(new_lat - lat) < 0.002
        assert abs(new_lon - lon) < 0.002


# ===================================================================
# FORM TESTS
# ===================================================================


@pytest.mark.django_db
class TestHelpRequestForm:
    """Tests for HelpRequestForm validation."""

    def test_valid_form(self, category):
        """Form is valid with all required fields."""
        from apps.requests.forms import HelpRequestForm

        data = {
            "title": "Потрібна допомога",
            "description": "Детальний опис запиту",
            "category": category.pk,
            "urgency": "medium",
            "needed_date": (timezone.now() + timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "duration": "1h",
            "volunteers_needed": 1,
            "address": "вул. Хрещатик, 1, Київ",
        }
        form = HelpRequestForm(data=data)
        assert form.is_valid(), form.errors

    def test_past_date_invalid(self, category):
        """Form rejects needed_date in the past."""
        from apps.requests.forms import HelpRequestForm

        data = {
            "title": "Тест",
            "description": "Опис",
            "category": category.pk,
            "urgency": "medium",
            "needed_date": (timezone.now() - timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "duration": "1h",
            "volunteers_needed": 1,
            "address": "вул. Хрещатик, 1",
        }
        form = HelpRequestForm(data=data)
        assert not form.is_valid()
        assert "needed_date" in form.errors

    def test_missing_required_fields(self):
        """Form is invalid when required fields are missing."""
        from apps.requests.forms import HelpRequestForm

        form = HelpRequestForm(data={})
        assert not form.is_valid()
        assert "title" in form.errors
        assert "description" in form.errors


@pytest.mark.django_db
class TestResponseForm:
    """Tests for ResponseForm."""

    def test_response_form_message_optional(self):
        """ResponseForm is valid without a message."""
        from apps.requests.forms import ResponseForm

        form = ResponseForm(data={"message": ""})
        assert form.is_valid()

    def test_response_form_with_message(self):
        """ResponseForm is valid with a message."""
        from apps.requests.forms import ResponseForm

        form = ResponseForm(data={"message": "Можу допомогти завтра о 10:00"})
        assert form.is_valid()


# ===================================================================
# VIEW TESTS
# ===================================================================


@pytest.mark.django_db
class TestHelpRequestListView:
    """Tests for the request list view."""

    def test_list_requires_login(self, client):
        """Unauthenticated user is redirected to login."""
        response = client.get("/requests/")
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_list_shows_active_requests(self, client_logged_in_volunteer, help_request):
        """Logged-in user sees active requests."""
        response = client_logged_in_volunteer.get("/requests/")
        assert response.status_code == 200
        assert help_request.title.encode() in response.content

    def test_list_filter_by_category(
        self, client_logged_in_volunteer, help_request, db
    ):
        """Filter by category returns only matching requests."""
        other_cat = CategoryFactory(name="Інше", slug="other")
        HelpRequestFactory(category=other_cat)
        response = client_logged_in_volunteer.get(
            f"/requests/?category={help_request.category.pk}"
        )
        assert response.status_code == 200
        assert help_request.title.encode() in response.content

    def test_list_excludes_non_active(self, client_logged_in_volunteer, db):
        """Completed/cancelled requests are not shown in the list."""
        completed = HelpRequestFactory(status=HelpRequest.Status.COMPLETED)
        response = client_logged_in_volunteer.get("/requests/")
        assert completed.title.encode() not in response.content


@pytest.mark.django_db
class TestHelpRequestDetailView:
    """Tests for the request detail view."""

    def test_detail_requires_login(self, client, help_request):
        """Unauthenticated user is redirected."""
        response = client.get(f"/requests/{help_request.pk}/")
        assert response.status_code == 302

    def test_detail_accessible_to_volunteer(
        self, client_logged_in_volunteer, help_request
    ):
        """Volunteer can view request detail."""
        response = client_logged_in_volunteer.get(f"/requests/{help_request.pk}/")
        assert response.status_code == 200
        assert help_request.title.encode() in response.content

    def test_detail_accessible_to_recipient_owner(
        self, client_logged_in_recipient, help_request
    ):
        """Recipient owner can view their own request."""
        response = client_logged_in_recipient.get(f"/requests/{help_request.pk}/")
        assert response.status_code == 200

    def test_detail_shows_responses_to_owner(
        self, client_logged_in_recipient, help_request, volunteer_response
    ):
        """Owner sees responses list on detail page."""
        response = client_logged_in_recipient.get(f"/requests/{help_request.pk}/")
        assert response.status_code == 200
        assert volunteer_response.volunteer.get_full_name().encode() in response.content


@pytest.mark.django_db
class TestHelpRequestCreateView:
    """Tests for creating a help request."""

    def test_create_requires_recipient(self, client_logged_in_volunteer):
        """Volunteer cannot access create view."""
        response = client_logged_in_volunteer.get("/requests/create/")
        assert response.status_code == 302

    def test_create_form_displayed(self, client_logged_in_recipient):
        """Recipient sees the creation form."""
        response = client_logged_in_recipient.get("/requests/create/")
        assert response.status_code == 200
        assert "form" in response.context

    def test_create_valid_request(self, client_logged_in_recipient, category):
        """Recipient can successfully create a request."""
        data = {
            "title": "Тестовий запит",
            "description": "Опис тестового запиту",
            "category": category.pk,
            "urgency": "medium",
            "needed_date": (timezone.now() + timedelta(days=2)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "duration": "1h",
            "volunteers_needed": 1,
            "address": "вул. Тестова, 1",
        }
        response = client_logged_in_recipient.post("/requests/create/", data)
        assert response.status_code == 302
        assert HelpRequest.objects.filter(title="Тестовий запит").exists()

    def test_create_max_active_requests_blocked(
        self, client_logged_in_recipient, recipient, category
    ):
        """Creating more than 10 active requests is blocked."""
        for i in range(10):
            HelpRequestFactory(recipient=recipient, status=HelpRequest.Status.ACTIVE)
        data = {
            "title": "Зайвий запит",
            "description": "Опис",
            "category": category.pk,
            "urgency": "low",
            "needed_date": (timezone.now() + timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "duration": "30min",
            "volunteers_needed": 1,
            "address": "Адреса",
        }
        response = client_logged_in_recipient.post("/requests/create/", data)
        # Should redirect (blocked), not create
        assert not HelpRequest.objects.filter(title="Зайвий запит").exists()


@pytest.mark.django_db
class TestHelpRequestUpdateView:
    """Tests for editing a help request."""

    def test_edit_by_owner_active(
        self, client_logged_in_recipient, help_request, category
    ):
        """Owner can edit an active request."""
        data = {
            "title": "Оновлена назва",
            "description": "Оновлений опис",
            "category": category.pk,
            "urgency": "high",
            "needed_date": (timezone.now() + timedelta(days=3)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "duration": "30min",
            "volunteers_needed": 1,
            "address": "Нова адреса",
        }
        response = client_logged_in_recipient.post(
            f"/requests/{help_request.pk}/edit/", data
        )
        assert response.status_code == 302
        help_request.refresh_from_db()
        assert help_request.title == "Оновлена назва"

    def test_edit_blocked_for_non_owner(self, client_logged_in_volunteer, help_request):
        """Non-owner cannot access edit view."""
        response = client_logged_in_volunteer.get(f"/requests/{help_request.pk}/edit/")
        assert response.status_code == 302

    def test_edit_blocked_for_completed(
        self, client_logged_in_recipient, recipient, category
    ):
        """Completed request cannot be edited."""
        hr = HelpRequestFactory(
            recipient=recipient,
            category=category,
            status=HelpRequest.Status.COMPLETED,
        )
        response = client_logged_in_recipient.get(f"/requests/{hr.pk}/edit/")
        assert response.status_code == 302


@pytest.mark.django_db
class TestRespondToRequest:
    """Tests for volunteer responding to a request."""

    def test_volunteer_can_respond(self, client_logged_in_volunteer, help_request):
        """Volunteer can respond to an active request."""
        response = client_logged_in_volunteer.post(
            f"/requests/{help_request.pk}/respond/",
            {"message": "Можу допомогти"},
        )
        assert response.status_code == 302
        assert (
            Response.objects.filter(
                help_request=help_request,
            ).count()
            == 1
        )

    def test_duplicate_response_blocked(
        self, client_logged_in_volunteer, help_request, volunteer
    ):
        """Volunteer cannot respond twice to the same request."""
        ResponseFactory(help_request=help_request, volunteer=volunteer)
        response = client_logged_in_volunteer.post(
            f"/requests/{help_request.pk}/respond/",
            {"message": "Ще раз"},
        )
        assert response.status_code == 302
        # Still only 1 response
        assert Response.objects.filter(help_request=help_request).count() == 1

    def test_recipient_cannot_respond(self, client_logged_in_recipient, help_request):
        """Recipient cannot respond to a request (wrong role)."""
        response = client_logged_in_recipient.post(
            f"/requests/{help_request.pk}/respond/",
            {"message": "Тест"},
        )
        assert response.status_code == 302
        assert not Response.objects.filter(help_request=help_request).exists()


@pytest.mark.django_db
class TestAcceptRejectVolunteer:
    """Tests for accept/reject volunteer actions."""

    def test_accept_volunteer(self, client_logged_in_recipient, volunteer_response):
        """Recipient can accept a pending response."""
        response = client_logged_in_recipient.post(
            f"/requests/responses/{volunteer_response.pk}/accept/"
        )
        assert response.status_code == 302
        volunteer_response.refresh_from_db()
        assert volunteer_response.status == Response.Status.ACCEPTED

    def test_accept_transitions_to_in_progress_when_quota_met(
        self, client_logged_in_recipient, help_request, volunteer_response
    ):
        """When accepted count reaches volunteers_needed, request → in_progress."""
        # volunteers_needed=1, accept one volunteer
        client_logged_in_recipient.post(
            f"/requests/responses/{volunteer_response.pk}/accept/"
        )
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.IN_PROGRESS

    def test_accept_rejects_remaining_pending(
        self, client_logged_in_recipient, help_request, volunteer
    ):
        """After quota met, remaining pending responses are auto-rejected."""
        # volunteers_needed=1
        v1_resp = ResponseFactory(help_request=help_request, volunteer=volunteer)
        v2 = VolunteerFactory()
        v2_resp = ResponseFactory(help_request=help_request, volunteer=v2)

        client_logged_in_recipient.post(f"/requests/responses/{v1_resp.pk}/accept/")
        v2_resp.refresh_from_db()
        assert v2_resp.status == Response.Status.REJECTED

    def test_reject_volunteer(self, client_logged_in_recipient, volunteer_response):
        """Recipient can reject a pending response."""
        response = client_logged_in_recipient.post(
            f"/requests/responses/{volunteer_response.pk}/reject/"
        )
        assert response.status_code == 302
        volunteer_response.refresh_from_db()
        assert volunteer_response.status == Response.Status.REJECTED

    def test_non_owner_cannot_accept(
        self, client_logged_in_volunteer, volunteer_response
    ):
        """Non-owner cannot accept a volunteer response."""
        response = client_logged_in_volunteer.post(
            f"/requests/responses/{volunteer_response.pk}/accept/"
        )
        assert response.status_code in (302, 404)
        volunteer_response.refresh_from_db()
        assert volunteer_response.status == Response.Status.PENDING


@pytest.mark.django_db
class TestCompleteRequest:
    """Tests for completing a request."""

    def test_accepted_volunteer_can_complete(
        self, client_logged_in_volunteer, help_request, volunteer
    ):
        """Accepted volunteer can mark a request as completed."""
        help_request.status = HelpRequest.Status.IN_PROGRESS
        help_request.save()
        ResponseFactory(
            help_request=help_request,
            volunteer=volunteer,
            status=Response.Status.ACCEPTED,
        )
        response = client_logged_in_volunteer.post(
            f"/requests/{help_request.pk}/complete/"
        )
        assert response.status_code == 302
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.COMPLETED

    def test_non_accepted_volunteer_cannot_complete(
        self, client_logged_in_volunteer, help_request
    ):
        """Volunteer without accepted response cannot complete request."""
        help_request.status = HelpRequest.Status.IN_PROGRESS
        help_request.save()
        response = client_logged_in_volunteer.post(
            f"/requests/{help_request.pk}/complete/"
        )
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.IN_PROGRESS

    def test_recipient_cannot_complete(self, client_logged_in_recipient, help_request):
        """Recipient cannot mark request as completed."""
        help_request.status = HelpRequest.Status.IN_PROGRESS
        help_request.save()
        response = client_logged_in_recipient.post(
            f"/requests/{help_request.pk}/complete/"
        )
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.IN_PROGRESS


@pytest.mark.django_db
class TestCancelRequest:
    """Tests for cancelling a request."""

    def test_owner_can_cancel_active(self, client_logged_in_recipient, help_request):
        """Recipient can cancel their active request."""
        response = client_logged_in_recipient.post(
            f"/requests/{help_request.pk}/cancel/"
        )
        assert response.status_code == 302
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.CANCELLED

    def test_owner_can_cancel_in_progress(
        self, client_logged_in_recipient, help_request
    ):
        """Recipient can cancel an in_progress request."""
        help_request.status = HelpRequest.Status.IN_PROGRESS
        help_request.save()
        client_logged_in_recipient.post(f"/requests/{help_request.pk}/cancel/")
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.CANCELLED

    def test_cannot_cancel_completed(self, client_logged_in_recipient, help_request):
        """Cannot cancel a completed request."""
        help_request.status = HelpRequest.Status.COMPLETED
        help_request.save()
        client_logged_in_recipient.post(f"/requests/{help_request.pk}/cancel/")
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.COMPLETED

    def test_non_owner_cannot_cancel(self, client_logged_in_volunteer, help_request):
        """Volunteer cannot cancel someone else's request."""
        response = client_logged_in_volunteer.post(
            f"/requests/{help_request.pk}/cancel/"
        )
        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.ACTIVE


@pytest.mark.django_db
class TestMyRequestsView:
    """Tests for the recipient's own requests view."""

    def test_my_requests_requires_recipient(self, client_logged_in_volunteer):
        """Volunteer cannot access my-requests view."""
        response = client_logged_in_volunteer.get("/requests/my/")
        assert response.status_code == 302

    def test_my_requests_shows_own_requests(
        self, client_logged_in_recipient, help_request
    ):
        """Recipient sees their own requests."""
        response = client_logged_in_recipient.get("/requests/my/")
        assert response.status_code == 200
        assert help_request.title.encode() in response.content

    def test_my_requests_excludes_others(self, client_logged_in_recipient, db):
        """Recipient does not see other users' requests."""
        other_hr = HelpRequestFactory()
        response = client_logged_in_recipient.get("/requests/my/")
        assert other_hr.title.encode() not in response.content


# ===================================================================
# MANAGEMENT COMMAND TESTS
# ===================================================================


@pytest.mark.django_db
class TestExpireRequestsCommand:
    """Tests for the expire_requests management command."""

    def test_expires_overdue_active_requests(self, db):
        """Command marks overdue active requests as expired."""
        overdue = HelpRequestFactory(
            needed_date=timezone.now() - timedelta(days=1),
            status=HelpRequest.Status.ACTIVE,
        )
        call_command("expire_requests")
        overdue.refresh_from_db()
        assert overdue.status == HelpRequest.Status.EXPIRED

    def test_does_not_expire_future_requests(self, db):
        """Command does not touch requests with future needed_date."""
        future = HelpRequestFactory(
            needed_date=timezone.now() + timedelta(days=2),
            status=HelpRequest.Status.ACTIVE,
        )
        call_command("expire_requests")
        future.refresh_from_db()
        assert future.status == HelpRequest.Status.ACTIVE

    def test_does_not_expire_in_progress(self, db):
        """Command does not change in_progress requests."""
        hr = HelpRequestFactory(
            needed_date=timezone.now() - timedelta(hours=1),
            status=HelpRequest.Status.IN_PROGRESS,
        )
        call_command("expire_requests")
        hr.refresh_from_db()
        assert hr.status == HelpRequest.Status.IN_PROGRESS

    def test_dry_run_makes_no_changes(self, db):
        """--dry-run flag does not change any statuses."""
        overdue = HelpRequestFactory(
            needed_date=timezone.now() - timedelta(days=1),
            status=HelpRequest.Status.ACTIVE,
        )
        call_command("expire_requests", dry_run=True)
        overdue.refresh_from_db()
        assert overdue.status == HelpRequest.Status.ACTIVE

    def test_expires_multiple_requests(self, db):
        """Command handles multiple overdue requests at once."""
        overdue_list = [
            HelpRequestFactory(
                needed_date=timezone.now() - timedelta(days=i + 1),
                status=HelpRequest.Status.ACTIVE,
            )
            for i in range(3)
        ]
        call_command("expire_requests")
        for hr in overdue_list:
            hr.refresh_from_db()
            assert hr.status == HelpRequest.Status.EXPIRED


# ===================================================================
# MAP DATA ENDPOINT TESTS
# ===================================================================


@pytest.mark.django_db
class TestMapDataView:
    """Tests for the map_data JSON endpoint."""

    def test_map_data_requires_login(self, client):
        """Unauthenticated request is redirected."""
        response = client.get("/requests/map/data/")
        assert response.status_code == 302

    def test_map_data_returns_json(self, client_logged_in_volunteer, help_request):
        """Returns valid JSON with active requests."""
        # Give the request coordinates
        help_request.latitude = 50.4501
        help_request.longitude = 30.5234
        help_request.save()

        response = client_logged_in_volunteer.get("/requests/map/data/")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == help_request.pk

    def test_map_data_excludes_requests_without_coordinates(
        self, client_logged_in_volunteer, db
    ):
        """Requests without lat/lon are excluded from map data."""
        HelpRequestFactory(latitude=None, longitude=None)
        response = client_logged_in_volunteer.get("/requests/map/data/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
