"""
Tests for the reviews app.

Covers: Review model, constraints, validation.
"""
import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError

from apps.reviews.models import Review

from conftest import ReviewFactory, VolunteerFactory, RecipientFactory, HelpRequestFactory


# ===================================================================
# REVIEW MODEL TESTS
# ===================================================================


class TestReviewModel:
    """Tests for the Review model."""

    def test_review_str(self, review):
        """Review __str__ returns author → target: rating/5."""
        result = str(review)
        assert '5' in result
        assert '→' in result

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
                comment='Duplicate review',
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
