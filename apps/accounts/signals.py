from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import RecipientProfile, User, VolunteerProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create the appropriate profile when a new user is registered."""
    if created:
        if instance.user_type == User.UserType.VOLUNTEER:
            VolunteerProfile.objects.create(user=instance)
        elif instance.user_type == User.UserType.RECIPIENT:
            RecipientProfile.objects.create(user=instance)
