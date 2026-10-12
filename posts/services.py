from django.conf import settings
from django.utils import timezone

from accounts.badges import check_badges
from notifications.services import notify

from .models import Post


def is_trusted(user):
    """نویسنده‌ی مورد اعتماد (staff یا چند نوشته‌ی تأییدشده) بدون صف تأیید منتشر می‌کنه."""
    if user.is_staff:
        return True
    return Post.objects.filter(author=user, status=Post.Status.PUBLISHED).count() >= settings.POST_TRUST_AFTER


def submit(post):
    """بعد از ذخیره‌ی نویسنده: یا مستقیم منتشر می‌شه یا میره صف تأیید."""
    if is_trusted(post.author):
        publish(post, notify_author=False)
    else:
        post.status, post.reject_reason = Post.Status.PENDING, ""
        post.save(update_fields=["status", "reject_reason", "updated_at"])
    return post


def publish(post, notify_author=True):
    post.status, post.reject_reason = Post.Status.PUBLISHED, ""
    if not post.published_at:
        post.published_at = timezone.now()
    post.save(update_fields=["status", "reject_reason", "published_at", "updated_at"])
    if notify_author:
        notify(post.author, f"معرفی «{post.title}» منتشر شد.", post.get_absolute_url(), kind="event")
    check_badges(post.author)


def reject(post, reason):
    post.status, post.reject_reason = Post.Status.REJECTED, reason[:300]
    post.save(update_fields=["status", "reject_reason", "updated_at"])
    notify(post.author, f"معرفی «{post.title}» منتشر نشد: {post.reject_reason}", "/posts/mine/", kind="event")
