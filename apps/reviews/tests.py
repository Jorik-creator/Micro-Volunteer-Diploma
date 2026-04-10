"""
Tests for the reviews app.

Covers: Review model, constraints, validation.
"""

import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError

from apps.reviews.models import Review
from apps.reviews.forms import ReviewForm

from apps.requests.models import HelpRequest, Response

from conftest import (
    ReviewFactory,
    VolunteerFactory,
    RecipientFactory,
    HelpRequestFactory,
    ResponseFactory,
)


# ===================================================================
# REVIEW MODEL TESTS
# ===================================================================


class TestReviewModel:
    """Tests for the Review model."""

    def test_review_str(self, review):
        """Review __str__ returns author → target: rating/5."""
        result = str(review)
        assert "5" in result
        assert "→" in result

    def test_review_ordering(self, db):
        """Reviews are ordered by -created_at (newest first)."""
        r1 = ReviewFactory(rating=3)
        r2 = ReviewFactory(rating=5)
        reviews = list(Review.objects.filter(pk__in=[r1.pk, r2.pk]))
        assert reviews[0] == r2  # Second created → first in queryset

    def test_unique_together_author_request(self, review, db):
        """Cannot create two reviews from the same author for the same request."""
        with pytest.raises(IntegrityError):
            Review.objects.create(
                author=review.author,
                target=review.target,
                help_request=review.help_request,
                rating=4,
                comment="Duplicate review",
            )

    def test_rating_min_value(self, db):
        """Rating below 1 fails validation."""
        review = ReviewFactory.build(rating=0)
        with pytest.raises(ValidationError):
            review.full_clean()

    def test_rating_max_value(self, db):
        """Rating above 5 fails validation."""
        review = ReviewFactory.build(rating=6)
        with pytest.raises(ValidationError):
            review.full_clean()

    def test_valid_rating_range(self, review):
        """Rating within 1-5 passes validation."""
        assert 1 <= review.rating <= 5
        review.full_clean()  # Should not raise


# ===================================================================
# REVIEW FORM TESTS
# ===================================================================


class TestReviewForm:
    """Tests for the ReviewForm."""

    def test_valid_form(self):
        """Valid rating (3) and non-empty comment produce a valid form."""
        # Arrange
        data = {"rating": 3, "comment": "Good work"}
        # Act
        form = ReviewForm(data=data)
        # Assert
        assert form.is_valid() is True

    def test_invalid_rating_zero(self):
        """Rating of 0 is below the allowed minimum (1) — form must be invalid."""
        # Arrange
        data = {"rating": 0, "comment": "Good work"}
        # Act
        form = ReviewForm(data=data)
        # Assert
        assert form.is_valid() is False
        assert "rating" in form.errors

    def test_invalid_rating_six(self):
        """Rating of 6 exceeds the allowed maximum (5) — form must be invalid."""
        # Arrange
        data = {"rating": 6, "comment": "Good work"}
        # Act
        form = ReviewForm(data=data)
        # Assert
        assert form.is_valid() is False
        assert "rating" in form.errors

    def test_missing_comment(self):
        """Empty comment is not allowed — form must be invalid with 'comment' error."""
        # Arrange
        data = {"rating": 3, "comment": ""}
        # Act
        form = ReviewForm(data=data)
        # Assert
        assert form.is_valid() is False
        assert "comment" in form.errors


# ===================================================================
# REVIEW VIEWS TESTS
# ===================================================================


class TestReviewViews:
    """Tests for CreateReviewView and ReviewListView."""

    @pytest.mark.django_db
    def test_create_review_as_recipient(
        self, client_logged_in_recipient, recipient, volunteer, category
    ):
        """Recipient can POST a review for a completed request — redirects and saves the review."""
        # Arrange: completed help request with an accepted volunteer response
        help_request = HelpRequestFactory(recipient=recipient, category=category)
        help_request.status = HelpRequest.Status.COMPLETED
        help_request.save()

        volunteer_response = ResponseFactory(
            help_request=help_request,
            volunteer=volunteer,
            status=Response.Status.ACCEPTED,
        )
        volunteer_response.save()

        # Act
        response = client_logged_in_recipient.post(
            f"/reviews/create/{help_request.pk}/",
            {"rating": 4, "comment": "Good"},
        )

        # Assert: redirect on success
        assert response.status_code == 302
        # Assert: review was persisted
        assert Review.objects.filter(help_request=help_request).exists()

    @pytest.mark.django_db
    def test_create_review_as_volunteer(
        self, client_logged_in_volunteer, recipient, volunteer, category
    ):
        """Volunteer POSTing a review for a request they are not the recipient of → 403 Forbidden."""
        # Arrange: completed help request owned by recipient (not the logged-in volunteer)
        help_request = HelpRequestFactory(recipient=recipient, category=category)
        help_request.status = HelpRequest.Status.COMPLETED
        help_request.save()

        ResponseFactory(
            help_request=help_request,
            volunteer=volunteer,
            status=Response.Status.ACCEPTED,
        )

        # Act
        response = client_logged_in_volunteer.post(
            f"/reviews/create/{help_request.pk}/",
            {"rating": 4, "comment": "Good"},
        )

        # Assert: permission denied
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_create_review_duplicate(
        self, client_logged_in_recipient, recipient, volunteer, category
    ):
        """Submitting a second review for the same request redirects without crashing and keeps only one review."""
        # Arrange: completed request with an existing review by the recipient
        help_request = HelpRequestFactory(recipient=recipient, category=category)
        help_request.status = HelpRequest.Status.COMPLETED
        help_request.save()

        ResponseFactory(
            help_request=help_request,
            volunteer=volunteer,
            status=Response.Status.ACCEPTED,
        )

        # Pre-existing review from the same author for the same request
        ReviewFactory(
            author=recipient,
            target=volunteer,
            help_request=help_request,
            rating=5,
        )

        # Act: attempt to submit a duplicate review
        response = client_logged_in_recipient.post(
            f"/reviews/create/{help_request.pk}/",
            {"rating": 3, "comment": "Trying again"},
        )

        # Assert: redirects (no 500 crash) and still only one review exists
        assert response.status_code == 302
        assert (
            Review.objects.filter(help_request=help_request, author=recipient).count()
            == 1
        )

    @pytest.mark.django_db
    def test_review_list_view(
        self, client_logged_in_volunteer, volunteer, recipient, category
    ):
        """ReviewListView returns 200 and exposes all reviews targeting the requested user."""
        # Arrange: two reviews where the volunteer is the target
        help_request_1 = HelpRequestFactory(recipient=recipient, category=category)
        help_request_2 = HelpRequestFactory(recipient=recipient, category=category)

        ReviewFactory(
            author=recipient, target=volunteer, help_request=help_request_1, rating=4
        )
        ReviewFactory(
            author=recipient, target=volunteer, help_request=help_request_2, rating=5
        )

        # Act
        response = client_logged_in_volunteer.get(f"/reviews/list/{volunteer.pk}/")

        # Assert
        assert response.status_code == 200
        assert len(response.context["reviews"]) == 2

    @pytest.mark.django_db
    def test_unauthenticated_redirect(self):
        """Unauthenticated GET to the create review URL redirects to the login page."""
        from django.test import Client

        # Arrange: anonymous client (not logged in)
        anon_client = Client()

        # Act
        response = anon_client.get("/reviews/create/1/")

        # Assert: redirect to login
        assert response.status_code == 302
        assert "login" in response.url
