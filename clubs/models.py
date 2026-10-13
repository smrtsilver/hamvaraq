"""باشگاه کتاب و همخوانی: یه گروه، کتاب در حال خواندن، گفت‌وگو و جلسه‌ها (از ماژول رویدادها)."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from common.text import slugify_fa


class Club(models.Model):
    name = models.CharField(max_length=80, verbose_name="نام باشگاه")
    slug = models.SlugField(max_length=100, unique=True, allow_unicode=True, editable=False)
    description = models.TextField(max_length=1500, blank=True, verbose_name="درباره‌ی باشگاه")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_clubs", verbose_name="گرداننده")
    current_title = models.CharField(max_length=200, blank=True, verbose_name="کتاب در حال خواندن")
    current_author = models.CharField(max_length=150, blank=True, verbose_name="نویسنده‌ی کتاب")
    city = models.ForeignKey("common.City", null=True, blank=True, on_delete=models.SET_NULL, related_name="clubs", verbose_name="شهر")
    is_online = models.BooleanField(default=False, verbose_name="آنلاین")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "باشگاه کتاب"
        verbose_name_plural = "باشگاه‌های کتاب"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("clubs:detail", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify_fa(self.name, 90) or "club"
            slug, n = base, 1
            while Club.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)


class ClubMember(models.Model):
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="club_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["club", "user"], name="one_membership")]
        verbose_name = "عضو باشگاه"
        verbose_name_plural = "عضوهای باشگاه"


class ClubPost(models.Model):
    """گفت‌وگوی باشگاه؛ فقط عضوها می‌نویسن."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="posts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="club_posts")
    text = models.TextField(max_length=1500, verbose_name="متن")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "پیام باشگاه"
        verbose_name_plural = "پیام‌های باشگاه"


class ClubProposal(models.Model):
    """پیشنهاد «کتاب بعدی» در باشگاه؛ عضوها رأی می‌دن و گرداننده انتخاب می‌کنه."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="proposals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="club_proposals")
    title = models.CharField(max_length=200, verbose_name="عنوان کتاب")
    author = models.CharField(max_length=150, blank=True, verbose_name="نویسنده")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "پیشنهاد کتاب بعدی"
        verbose_name_plural = "پیشنهادهای کتاب بعدی"


class ClubVote(models.Model):
    """هر عضو در هر باشگاه یه رأی داره (عوض‌کردنش آزاده)."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="votes")
    proposal = models.ForeignKey(ClubProposal, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="club_votes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["club", "user"], name="one_vote_per_club")]
