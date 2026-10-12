from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from books.models import Book
from exchanges.models import Exchange, Message

from common.throttle import throttle

from .forms import ReportForm, VoteForm
from .models import Report, Vote
from .services import can_edit_vote


@login_required
@require_POST
def vote(request, exchange_id):
    ex = get_object_or_404(Exchange, pk=exchange_id)
    if not ex.is_party(request.user):
        return redirect("home")
    if ex.status != Exchange.Status.COMPLETED:
        messages.error(request, "رأی فقط بعد از مبادله‌ی کامل‌شده ثبت می‌شه.")
        return redirect("exchanges:detail", ex.pk)
    existing = Vote.objects.filter(exchange=ex, voter=request.user).first()
    if existing and not can_edit_vote(existing):
        messages.error(request, "مهلت ویرایش رأی تموم شده.")
        return redirect("exchanges:detail", ex.pk)
    form = VoteForm(request.POST, instance=existing)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.exchange, obj.voter, obj.target = ex, request.user, ex.other_party(request.user)
        obj.save()
        messages.success(request, "رأیت ثبت شد.")
    else:
        messages.error(request, "رأی نامعتبره؛ دوباره امتحان کن.")
    return redirect("exchanges:detail", ex.pk)


@login_required
@throttle("report", 10, 86400, by="user")
def report(request, kind, pk):
    """kind: user | book | message"""
    if kind == "user":
        target = get_object_or_404(User, pk=pk)
        fields, own = {"target_user": target}, target.pk == request.user.pk
    elif kind == "book":
        target = get_object_or_404(Book, pk=pk)
        fields, own = {"target_book": target}, target.owner_id == request.user.pk
    elif kind == "message":
        target = get_object_or_404(Message.objects.select_related("exchange"), pk=pk)
        # فقط دو طرف مبادله پیام رو می‌بینن و می‌تونن گزارش بدن
        if not target.exchange.is_party(request.user):
            return redirect("home")
        fields, own = {"target_message": target}, target.sender_id == request.user.pk
    else:
        return redirect("home")
    if own:
        messages.error(request, "خودت رو نمی‌تونی گزارش بدی.")
        return redirect("home")
    if Report.objects.filter(reporter=request.user, **fields).exists():
        messages.info(request, "قبلاً برای این مورد گزارش دادی.")
        return redirect("home")
    form = ReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        rep = form.save(commit=False)
        rep.reporter = request.user
        for k, v in fields.items():
            setattr(rep, k, v)
        try:
            with transaction.atomic():
                rep.save()
        except IntegrityError:
            messages.info(request, "قبلاً برای این مورد گزارش دادی.")
        else:
            messages.success(request, "گزارشت ثبت شد؛ از نتیجه باخبرت می‌کنیم.")
        return redirect("home")
    return render(request, "trust/report.html", {"form": form, "target": target, "kind": kind})
