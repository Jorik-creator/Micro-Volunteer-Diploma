from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def volunteer_required(view_func):
    """Decorator that checks if the user is a volunteer."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_volunteer:
            messages.error(
                request, 'Ця сторінка доступна тільки для волонтерів.'
            )
            return redirect('home')
        return view_func(request, *args, **kwargs)

    return wrapper


def recipient_required(view_func):
    """Decorator that checks if the user is a help recipient."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_recipient:
            messages.error(
                request,
                'Ця сторінка доступна тільки для отримувачів допомоги.',
            )
            return redirect('home')
        return view_func(request, *args, **kwargs)

    return wrapper
