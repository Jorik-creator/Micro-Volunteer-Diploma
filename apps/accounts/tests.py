"""
Tests for the accounts app.

Covers: models, signals, forms, views, decorators.
"""
import pytest
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage

from apps.accounts.models import User, VolunteerProfile, RecipientProfile
from apps.accounts.forms import RegisterForm, UserProfileForm
from apps.accounts.decorators import volunteer_required, recipient_required

from conftest import VolunteerFactory, RecipientFactory


# ===================================================================
# MODEL TESTS
# ===================================================================


class TestUserModel:
    """Tests for the custom User model."""

    def test_user_str_representation(self, volunteer):
        """User __str__ returns full name with role display."""
        expected = f"{volunteer.get_full_name()} (Волонтер)"
        assert str(volunteer) == expected

    def test_is_volunteer_property(self, volunteer):
        """is_volunteer returns True for volunteer users."""
        assert volunteer.is_volunteer is True
        assert volunteer.is_recipient is False

    def test_is_recipient_property(self, recipient):
        """is_recipient returns True for recipient users."""
        assert recipient.is_recipient is True
        assert recipient.is_volunteer is False

    def test_email_is_unique(self, volunteer, db):
        """Cannot create two users with the same email."""
        with pytest.raises(Exception):
            User.objects.create_user(
                username='duplicate',
                email=volunteer.email,
                password='TestPass123!',
                user_type=User.UserType.VOLUNTEER,
            )

    def test_user_ordering(self, db):
        """Users are ordered by -created_at (newest first)."""
        u1 = VolunteerFactory(username='first_user')
        u2 = VolunteerFactory(username='second_user')
        users = list(User.objects.filter(username__in=['first_user', 'second_user']))
        assert users[0] == u2  # second created → first in queryset


# ===================================================================
# SIGNAL TESTS
# ===================================================================


class TestProfileSignals:
    """Tests for automatic profile creation via post_save signal."""

    def test_volunteer_profile_created_on_registration(self, volunteer):
        """VolunteerProfile is auto-created when a volunteer user is saved."""
        assert VolunteerProfile.objects.filter(user=volunteer).exists()
        assert volunteer.volunteer_profile is not None

    def test_recipient_profile_created_on_registration(self, recipient):
        """RecipientProfile is auto-created when a recipient user is saved."""
        assert RecipientProfile.objects.filter(user=recipient).exists()
        assert recipient.recipient_profile is not None

    def test_volunteer_profile_defaults(self, volunteer):
        """VolunteerProfile has correct default values."""
        profile = volunteer.volunteer_profile
        assert profile.radius_km == VolunteerProfile.RadiusChoices.MEDIUM
        assert profile.is_available is True
        assert profile.bio == ''


# ===================================================================
# FORM TESTS
# ===================================================================


class TestRegisterForm:
    """Tests for the user registration form."""

    def test_valid_registration_data(self, db):
        """Form is valid with correct data."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Тест',
            'last_name': 'Тестовий',
            'user_type': User.UserType.VOLUNTEER,
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }
        form = RegisterForm(data=data)
        assert form.is_valid(), form.errors

    def test_duplicate_email_rejected(self, volunteer):
        """Form rejects registration with an existing email."""
        data = {
            'username': 'another',
            'email': volunteer.email,
            'first_name': 'Тест',
            'last_name': 'Тестовий',
            'user_type': User.UserType.VOLUNTEER,
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }
        form = RegisterForm(data=data)
        assert not form.is_valid()
        assert 'email' in form.errors

    def test_password_mismatch_rejected(self, db):
        """Form rejects when passwords don't match."""
        data = {
            'username': 'mismatch',
            'email': 'mismatch@example.com',
            'first_name': 'Тест',
            'last_name': 'Тестовий',
            'user_type': User.UserType.RECIPIENT,
            'password1': 'SecurePass123!',
            'password2': 'DifferentPass456!',
        }
        form = RegisterForm(data=data)
        assert not form.is_valid()
        assert 'password2' in form.errors

    def test_missing_required_fields(self, db):
        """Form rejects when required fields are missing."""
        form = RegisterForm(data={})
        assert not form.is_valid()
        required_fields = ['username', 'email', 'first_name', 'last_name', 'user_type']
        for field in required_fields:
            assert field in form.errors


class TestUserProfileForm:
    """Tests for the profile editing form."""

    def test_avatar_size_validation(self, volunteer):
        """Form rejects avatar files larger than 2 MB."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Create a fake file > 2 MB
        large_file = SimpleUploadedFile(
            'big_avatar.jpg',
            b'\x00' * (3 * 1024 * 1024),  # 3 MB
            content_type='image/jpeg',
        )
        form = UserProfileForm(
            data={
                'first_name': volunteer.first_name,
                'last_name': volunteer.last_name,
                'email': volunteer.email,
            },
            files={'avatar': large_file},
            instance=volunteer,
        )
        assert not form.is_valid()
        assert 'avatar' in form.errors


# ===================================================================
# VIEW TESTS
# ===================================================================


class TestHomeView:
    """Tests for the landing page."""

    def test_home_page_returns_200(self, client, db):
        """Home page is accessible and returns HTTP 200."""
        response = client.get('/')
        assert response.status_code == 200

    def test_home_page_contains_stats(self, client, volunteer, recipient):
        """Home page context includes platform statistics."""
        response = client.get('/')
        assert response.context['total_users'] >= 2
        assert response.context['total_volunteers'] >= 1
        assert response.context['total_recipients'] >= 1


class TestRegisterView:
    """Tests for user registration view."""

    def test_register_page_returns_200(self, client, db):
        """Registration page is accessible."""
        response = client.get('/accounts/register/')
        assert response.status_code == 200

    def test_successful_registration_redirects(self, client, db):
        """Successful registration redirects to home and logs user in."""
        data = {
            'username': 'newvolunteer',
            'email': 'newvol@example.com',
            'first_name': 'Новий',
            'last_name': 'Волонтер',
            'user_type': User.UserType.VOLUNTEER,
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }
        response = client.post('/accounts/register/', data)
        assert response.status_code == 302  # redirect
        assert User.objects.filter(username='newvolunteer').exists()

    def test_authenticated_user_redirected_from_register(self, client_logged_in_volunteer):
        """Authenticated users are redirected away from registration page."""
        response = client_logged_in_volunteer.get('/accounts/register/')
        assert response.status_code == 302


class TestLoginView:
    """Tests for user login view."""

    def test_login_page_returns_200(self, client, db):
        """Login page is accessible."""
        response = client.get('/accounts/login/')
        assert response.status_code == 200

    def test_successful_login(self, client, volunteer):
        """User can log in with valid credentials."""
        response = client.post('/accounts/login/', {
            'username': volunteer.username,
            'password': 'TestPass123!',
        })
        assert response.status_code == 302  # redirect on success


class TestProfileView:
    """Tests for profile view (requires authentication)."""

    def test_profile_requires_login(self, client, db):
        """Unauthenticated users are redirected to login."""
        response = client.get('/accounts/profile/')
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_profile_accessible_when_logged_in(self, client_logged_in_volunteer):
        """Authenticated users can access their profile."""
        response = client_logged_in_volunteer.get('/accounts/profile/')
        assert response.status_code == 200


# ===================================================================
# DECORATOR TESTS
# ===================================================================


def _build_request(user=None):
    """Helper: build a fake request with session and messages support."""
    rf = RequestFactory()
    request = rf.get('/fake-url/')

    # Add session
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()

    # Add messages
    messages_middleware = MessageMiddleware(lambda req: None)
    messages_middleware.process_request(request)
    setattr(request, '_messages', FallbackStorage(request))

    if user:
        request.user = user
    return request


class TestDecorators:
    """Tests for volunteer_required and recipient_required decorators."""

    def test_volunteer_required_allows_volunteer(self, volunteer):
        """volunteer_required allows access for volunteer users."""
        @volunteer_required
        def dummy_view(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        request = _build_request(user=volunteer)
        response = dummy_view(request)
        assert response.status_code == 200

    def test_volunteer_required_blocks_recipient(self, recipient):
        """volunteer_required redirects recipient users."""
        @volunteer_required
        def dummy_view(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        request = _build_request(user=recipient)
        response = dummy_view(request)
        assert response.status_code == 302  # redirect

    def test_recipient_required_allows_recipient(self, recipient):
        """recipient_required allows access for recipient users."""
        @recipient_required
        def dummy_view(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        request = _build_request(user=recipient)
        response = dummy_view(request)
        assert response.status_code == 200

    def test_recipient_required_blocks_volunteer(self, volunteer):
        """recipient_required redirects volunteer users."""
        @recipient_required
        def dummy_view(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        request = _build_request(user=volunteer)
        response = dummy_view(request)
        assert response.status_code == 302  # redirect
