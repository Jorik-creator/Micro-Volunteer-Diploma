"""
Tests for the requests app.

Covers: models (Category, HelpRequest, Response), utils (haversine), constraints.
"""
import pytest
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
        c_b = CategoryFactory(name='Бета', slug='beta')
        c_a = CategoryFactory(name='Альфа', slug='alpha')
        categories = list(Category.objects.filter(slug__in=['alpha', 'beta']))
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
        hr1 = HelpRequestFactory(title='First')
        hr2 = HelpRequestFactory(title='Second')
        requests = list(HelpRequest.objects.filter(title__in=['First', 'Second']))
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
        # Kyiv: 50.4501, 30.5234
        # Lviv: 49.8397, 24.0297
        distance = haversine_distance(50.4501, 30.5234, 49.8397, 24.0297)
        assert 460 < distance < 480  # ~470 km

    def test_known_distance_short(self):
        """Short distance (~1 km) is calculated correctly."""
        # Two points ~1 km apart in Kyiv
        distance = haversine_distance(50.4501, 30.5234, 50.4591, 30.5234)
        assert 0.5 < distance < 1.5

    def test_antipodal_points(self):
        """Distance between antipodal points is approximately half Earth circumference."""
        distance = haversine_distance(0, 0, 0, 180)
        assert 20000 < distance < 20100  # ~20015 km


class TestOffsetCoordinates:
    """Tests for the offset_coordinates privacy function."""

    def test_offset_returns_different_coordinates(self):
        """Offset coordinates differ from original."""
        lat, lon = 50.4501, 30.5234
        new_lat, new_lon = offset_coordinates(lat, lon, offset_meters=100)
        # They should be different (extremely unlikely to be identical)
        assert (new_lat, new_lon) != (lat, lon)

    def test_offset_stays_within_range(self):
        """Offset coordinates stay within expected range (~100m)."""
        lat, lon = 50.4501, 30.5234
        new_lat, new_lon = offset_coordinates(lat, lon, offset_meters=100)
        # 100m ≈ 0.0009 degrees latitude
        assert abs(new_lat - lat) < 0.002
        assert abs(new_lon - lon) < 0.002
