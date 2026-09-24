"""
Tests for two-sided blind reviews (docs/adr/0006).
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.notifications.models import Notification
from apps.requests.models import HelpRequest, Response
from apps.reviews import services
from apps.reviews.forms import ReviewForm
from apps.reviews.models import Review
from apps.reviews.services import ReviewError
from conftest import (
    HelpRequestFactory,
    RecipientFactory,
    ResponseFactory,
    ReviewFactory,
    VolunteerFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def done(recipient, volunteer):
    """A request completed yesterday with one accepted volunteer."""
    help_request = HelpRequestFactory(
        recipient=recipient,
        status=HelpRequest.Status.COMPLETED,
        completed_at=timezone.now() - timedelta(days=1),
    )
    ResponseFactory(help_request=help_request, volunteer=volunteer, status=Response.Status.ACCEPTED)
    return help_request


class TestModel:
    def test_str(self, review):
        assert "5/5" in str(review)

    def test_one_review_per_pair(self, review):
        with pytest.raises(IntegrityError):
            ReviewFactory(
                author=review.author, target=review.target, help_request=review.help_request
            )

    def test_rating_constraint(self, help_request):
        with pytest.raises(IntegrityError):
            ReviewFactory(help_request=help_request, rating=6)

    def test_tag_labels(self, db):
        review = ReviewFactory(tags=["punctual", "unknown"])
        assert review.get_tags_display() == ["Пунктуальний(а)"]


class TestEligibility:
    def test_recipient_rates_each_accepted_volunteer(self, done, recipient, volunteer):
        second = VolunteerFactory()
        ResponseFactory(help_request=done, volunteer=second, status=Response.Status.ACCEPTED)

        assert set(services.counterparts(done, recipient)) == {volunteer, second}

    def test_volunteer_rates_recipient(self, done, recipient, volunteer):
        assert services.counterparts(done, volunteer) == [recipient]

    def test_rejected_volunteer_cannot_rate(self, done):
        outsider = VolunteerFactory()
        ResponseFactory(help_request=done, volunteer=outsider, status=Response.Status.REJECTED)

        assert services.counterparts(done, outsider) == []

    def test_not_before_completion(self, help_request, recipient, volunteer):
        ResponseFactory(
            help_request=help_request, volunteer=volunteer, status=Response.Status.ACCEPTED
        )
        assert services.review_error(recipient, help_request, volunteer)

    def test_window_closes_after_14_days(self, done, recipient, volunteer):
        later = done.completed_at + timedelta(days=15)
        assert "минув" in services.review_error(recipient, done, volunteer, now=later)

    def test_cannot_rate_twice(self, done, recipient, volunteer):
        services.submit_review(recipient, done, volunteer, 5)
        with pytest.raises(ReviewError):
            services.submit_review(recipient, done, volunteer, 4)


class TestBlindExchange:
    def test_first_review_stays_hidden_and_invites_counterpart(self, done, recipient, volunteer):
        review = services.submit_review(recipient, done, volunteer, 5, ["punctual"], "Дякую!")

        assert review.published_at is None
        assert Notification.objects.filter(user=volunteer, type="reminder").exists()
        assert not Notification.objects.filter(type=Notification.Type.NEW_REVIEW).exists()

    def test_second_review_publishes_both(self, done, recipient, volunteer):
        first = services.submit_review(recipient, done, volunteer, 5)
        second = services.submit_review(volunteer, done, recipient, 4)

        first.refresh_from_db()
        assert first.published_at and second.published_at
        for user in (recipient, volunteer):
            assert Notification.objects.filter(user=user, type="new_review").exists()

    def test_window_end_publishes_lonely_review(self, done, recipient, volunteer):
        review = services.submit_review(recipient, done, volunteer, 3)

        assert services.publish_due(now=timezone.now() + timedelta(days=15)) == 1

        review.refresh_from_db()
        assert review.published_at is not None

    def test_tags_are_limited_to_target_role(self, done, recipient, volunteer):
        review = services.submit_review(recipient, done, volunteer, 5, ["punctual", "welcoming"])
        assert review.tags == ["punctual"]


class TestSummaryAndReminders:
    def test_summary_counts_only_published(self, volunteer):
        ReviewFactory(target=volunteer, rating=4, tags=["polite"], published_at=timezone.now())
        ReviewFactory(target=volunteer, rating=2, tags=["late"], published_at=timezone.now())
        ReviewFactory(target=volunteer, rating=1, published_at=None)

        summary = services.rating_summary(volunteer)

        assert summary.average == 3.0
        assert summary.count == 2
        assert {t["label"] for t in summary.top_tags} == {"Ввічливий(а)", "Запізнився(лась)"}
        assert any(t["negative"] for t in summary.top_tags)

    def test_pending_reviews_lists_unrated_pairs(self, done, recipient, volunteer):
        assert services.pending_reviews(recipient) == [(done, volunteer)]
        services.submit_review(recipient, done, volunteer, 5)
        assert services.pending_reviews(recipient) == []

    def test_reminder_once_after_three_days(self, done, recipient, volunteer):
        done.completed_at = timezone.now() - timedelta(days=4)
        done.save()

        assert services.send_review_reminders() == 2
        assert services.send_review_reminders() == 0


class TestForm:
    def test_valid(self, volunteer):
        form = ReviewForm({"rating": "5", "tags": ["punctual"]}, target=volunteer)
        assert form.is_valid()

    def test_rating_required(self, volunteer):
        assert not ReviewForm({"comment": "ok"}, target=volunteer).is_valid()

    def test_recipient_tags_not_offered_for_volunteer(self, volunteer):
        form = ReviewForm({"rating": "5", "tags": ["welcoming"]}, target=volunteer)
        assert not form.is_valid()


class TestViews:
    def test_form_page(self, client_logged_in_recipient, done, volunteer):
        page = client_logged_in_recipient.get(f"/reviews/create/{done.pk}/{volunteer.pk}/")
        assert page.status_code == 200
        assert "Пунктуальний" in page.content.decode()

    def test_submit(self, client_logged_in_recipient, done, recipient, volunteer):
        page = client_logged_in_recipient.post(
            f"/reviews/create/{done.pk}/{volunteer.pk}/",
            {"rating": "5", "tags": ["polite"], "comment": "Дуже допоміг"},
        )
        assert page.status_code == 302
        assert Review.objects.filter(author=recipient, target=volunteer).exists()

    def test_outsider_is_redirected(self, client, done, volunteer):
        client.force_login(RecipientFactory())
        page = client.get(f"/reviews/create/{done.pk}/{volunteer.pk}/")
        assert page.status_code == 302
        assert page["Location"] == f"/requests/{done.pk}/"

    def test_anonymous_goes_to_login(self, client, done, volunteer):
        page = client.get(f"/reviews/create/{done.pk}/{volunteer.pk}/")
        assert "login" in page["Location"]

    def test_detail_offers_rating(self, client_logged_in_volunteer, done):
        page = client_logged_in_volunteer.get(f"/requests/{done.pk}/")
        assert "Оцінити" in page.content.decode()


class TestProfiles:
    def test_recipient_sees_profile_of_responding_volunteer(self, client, recipient, volunteer):
        ResponseFactory(help_request=HelpRequestFactory(recipient=recipient), volunteer=volunteer)
        client.force_login(recipient)

        page = client.get(f"/accounts/users/{volunteer.pk}/")

        assert page.status_code == 200
        body = page.content.decode()
        assert volunteer.email not in body
        assert volunteer.last_name not in body  # only the initial is shown

    def test_stranger_gets_404(self, client, volunteer):
        client.force_login(RecipientFactory())
        assert client.get(f"/accounts/users/{volunteer.pk}/").status_code == 404

    def test_own_public_profile_redirects_to_profile(self, client, volunteer):
        client.force_login(volunteer)
        assert client.get(f"/accounts/users/{volunteer.pk}/")["Location"] == "/accounts/profile/"

    def test_own_profile_prompts_pending_review(self, client, done, recipient):
        client.force_login(recipient)
        assert "Залиште оцінку" in client.get("/accounts/profile/").content.decode()
