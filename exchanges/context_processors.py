from .chat import total_unread


def unread_chat(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_messages": total_unread(user)}
