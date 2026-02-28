from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import UserRole


def get_user_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return UserRole.ROLE_ADMIN
    role_profile, _ = UserRole.objects.get_or_create(user=user)
    return role_profile.role


def has_any_role(user, *roles):
    role = get_user_role(user)
    return role in set(roles)


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if not has_any_role(request.user, *allowed_roles):
                messages.error(request, "You do not have permission to access this page.")
                return redirect("home")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
