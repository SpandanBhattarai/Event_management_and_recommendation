from .roles import get_user_role


def user_role(request):
    role = None
    if request.user.is_authenticated:
        role = get_user_role(request.user)
    return {"user_role": role}
