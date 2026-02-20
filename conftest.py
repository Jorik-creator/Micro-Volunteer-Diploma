"""
Root conftest.py — shared fixtures and factory_boy factories for all apps.

Uses SQLite in-memory DB for fast, isolated test runs (no PostgreSQL needed).
"""
import pytest
import factory
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User, VolunteerProfile, RecipientProfile
from apps.requests.models import Category, HelpRequest, Response
from apps.reviews.models import Review
from apps.notifications.models import Notification


# ---------------------------------------------------------------------------
# Factory Boy — Model Factories
# ---------------------------------------------------------------------------

class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating User instances."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    password = factory.PostGenerationMethodCall('set_password', 'TestPass123!')
    user_type = User.UserType.VOLUNTEER

    @factory.post_generation
    def save_after_password(self, create, extracted, **kwargs):
        if create:
            self.save()


class VolunteerFactory(UserFactory):
    """Factory for creating volunteer users (profile created via signal)."""
    user_type = User.UserType.VOLUNTEER


class RecipientFactory(UserFactory):
    """Factory for creating recipient users (profile created via signal)."""
    user_type = User.UserType.RECIPIENT


class CategoryFactory(factory.django.DjangoModelFactory):
    """Factory for creating Category instances."""

    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f'Категорія {n}')
    slug = factory.Sequence(lambda n: f'category-{n}')
    icon = 'bi-heart'
    description = factory.Faker('sentence')


class HelpRequestFactory(factory.django.DjangoModelFactory):
    """Factory for creating HelpRequest instances."""

    class Meta:
        model = HelpRequest

    recipient = factory.SubFactory(RecipientFactory)
    title = factory.Faker('sentence', nb_words=5)
    description = factory.Faker('paragraph')
    category = factory.SubFactory(CategoryFactory)
    urgency = HelpRequest.Urgency.MEDIUM
    status = HelpRequest.Status.ACTIVE
    needed_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=2))
    duration = HelpRequest.Duration.ONE_HOUR
    volunteers_needed = 1
    address = factory.Faker('address')
    latitude = 50.4501
    longitude = 30.5234


class ResponseFactory(factory.django.DjangoModelFactory):
    """Factory for creating Response (volunteer response) instances."""

    class Meta:
        model = Response

    help_request = factory.SubFactory(HelpRequestFactory)
    volunteer = factory.SubFactory(VolunteerFactory)
    status = Response.Status.PENDING
    message = factory.Faker('sentence')


class ReviewFactory(factory.django.DjangoModelFactory):
    """Factory for creating Review instances."""

    class Meta:
        model = Review

    author = factory.SubFactory(VolunteerFactory)
    target = factory.SubFactory(RecipientFactory)
    help_request = factory.SubFactory(HelpRequestFactory)
    rating = 5
    comment = factory.Faker('paragraph')


class NotificationFactory(factory.django.DjangoModelFactory):
    """Factory for creating Notification instances."""

    class Meta:
        model = Notification

    user = factory.SubFactory(VolunteerFactory)
    type = Notification.Type.NEW_RESPONSE
    title = factory.Faker('sentence', nb_words=4)
    message = factory.Faker('sentence')
    is_read = False


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def volunteer(db):
    """Create and return a volunteer user."""
    return VolunteerFactory()


@pytest.fixture
def recipient(db):
    """Create and return a recipient user."""
    return RecipientFactory()


@pytest.fixture
def category(db):
    """Create and return a category."""
    return CategoryFactory(name='Покупка продуктів', slug='groceries')


@pytest.fixture
def help_request(db, recipient, category):
    """Create and return a help request."""
    return HelpRequestFactory(recipient=recipient, category=category)


@pytest.fixture
def volunteer_response(db, help_request, volunteer):
    """Create and return a volunteer response to a help request."""
    return ResponseFactory(help_request=help_request, volunteer=volunteer)


@pytest.fixture
def review(db, volunteer, recipient, help_request):
    """Create and return a review."""
    return ReviewFactory(
        author=recipient,
        target=volunteer,
        help_request=help_request,
    )


@pytest.fixture
def notification(db, recipient):
    """Create and return a notification."""
    return NotificationFactory(user=recipient)


@pytest.fixture
def client_logged_in_volunteer(client, volunteer):
    """Return a test client logged in as a volunteer."""
    client.login(username=volunteer.username, password='TestPass123!')
    return client


@pytest.fixture
def client_logged_in_recipient(client, recipient):
    """Return a test client logged in as a recipient."""
    client.login(username=recipient.username, password='TestPass123!')
    return client
