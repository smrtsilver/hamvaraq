from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from common.throttle import throttle

from .forms import TicketForm
from .models import Ticket


@throttle("ticket", 5, 3600, by="auto")
def ticket_new(request):
    initial = {"page_url": request.GET.get("from", "")}
    if request.GET.get("type") in Ticket.Category.values:
        initial["category"] = request.GET["type"]
    form = TicketForm(request.POST or None, initial=initial, user=request.user)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.user = request.user if request.user.is_authenticated else None
        ticket.save()
        messages.success(request, "گزارشت ثبت شد؛ ممنون که کمک می‌کنی. هر خبری شد همین‌جا و تو اعلان‌ها می‌گیری.")
        return redirect("support:mine" if request.user.is_authenticated else "home")
    return render(request, "support/new.html", {"form": form})


@login_required
def my_tickets(request):
    page = Paginator(request.user.tickets.all(), 15).get_page(request.GET.get("page"))
    return render(request, "support/mine.html", {"page": page})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, user=request.user)
    return render(request, "support/detail.html", {"t": ticket})
