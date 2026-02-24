import json
import uuid
from decimal import Decimal, InvalidOperation
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .models import Category, Event, TicketPurchase, Venue
from .recommendation import get_recommended_events


def home(request):
    events = (
        Event.objects.filter(is_active=True)
        .select_related("venue", "category")
        .order_by("start_date")[:6]
    )
    recommended_events = []
    if request.user.is_authenticated:
        recommended_events = get_recommended_events(request)[:6]
    return render(
        request,
        "home.html",
        {"events": events, "recommended_events": recommended_events},
    )

def register_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if not username:
            messages.error(request, "Username is required")
            return redirect("register")

        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect("register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect("register")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        login(request, user)
        return redirect("home")

    return render(request, "register.html")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)  # creates session
            return redirect("home")
        else:
            messages.error(request, "Invalid credentials")
            return redirect("login")

    return render(request, "login.html")

def logout_view(request):
    logout(request)  # destroys session
    return redirect("login")

def events_view(request):
    selected_category = request.GET.get("category")
    selected_city = request.GET.get("city", "").strip()
    selected_max_price = request.GET.get("max_price", "").strip()
    categories = Category.objects.order_by("name")
    cities = Venue.objects.values_list("city", flat=True).distinct().order_by("city")

    events = (
        Event.objects.filter(is_active=True)
        .select_related("venue", "category")
        .order_by("start_date")
    )
    recommended = get_recommended_events(request)

    if selected_category:
        if selected_category.isdigit():
            events = events.filter(category_id=selected_category)
        else:
            selected_category = ""

    if selected_city:
        events = events.filter(venue__city__iexact=selected_city)

    if selected_max_price:
        try:
            max_price = Decimal(selected_max_price)
            if max_price >= 0:
                events = events.filter(price__lte=max_price)
            else:
                selected_max_price = ""
        except (InvalidOperation, TypeError):
            selected_max_price = ""

    recommended = recommended[:3]

    return render(
        request,
        "events.html",
        {
            "events": events,
            "recommended_events": recommended,
            "categories": categories,
            "selected_category": selected_category,
            "cities": cities,
            "selected_city": selected_city,
            "selected_max_price": selected_max_price,
        },
    )


def venues_view(request):
    venues = Venue.objects.all()
    return render(request, "venues.html", {"venues": venues})


def contact_view(request):
    return render(request, "contact.html")


def save_location(request):
    lat = request.GET.get("lat")
    lng = request.GET.get("lng")

    request.session["user_lat"] = float(lat)
    request.session["user_lng"] = float(lng)

    return JsonResponse({"status": "Location saved"})

@login_required
def recommended_events(request):

    events = get_recommended_events(request)

    return render(request, "recommended.html", {"events": events})


@login_required
def buy_ticket(request, event_id):
    if request.method != "POST":
        return redirect("events")

    event = get_object_or_404(Event, id=event_id, is_active=True)
    quantity_raw = request.POST.get("ticket_quantity", "1")

    try:
        quantity = int(quantity_raw)
    except ValueError:
        messages.error(request, "Invalid ticket quantity.")
        return redirect("events")

    if quantity < 1 or quantity > 10:
        messages.error(request, "Please select between 1 and 10 tickets.")
        return redirect("events")

    try:
        total_rupees = Decimal(event.price) * Decimal(quantity)
    except (InvalidOperation, TypeError):
        messages.error(request, "Unable to calculate ticket price.")
        return redirect("events")

    total_paisa = int(total_rupees * 100)
    khalti_secret_key = getattr(settings, "KHALTI_SECRET_KEY", "")
    if not khalti_secret_key:
        messages.error(request, "Khalti is not configured. Add KHALTI_SECRET_KEY in settings.")
        return redirect("events")

    return_url = request.build_absolute_uri(reverse("khalti_return"))
    website_url = request.build_absolute_uri(reverse("events"))

    payload = {
        "return_url": return_url,
        "website_url": website_url,
        "amount": total_paisa,
        "purchase_order_id": f"event-{event.id}-user-{request.user.id}-{uuid.uuid4().hex[:10]}",
        "purchase_order_name": f"{event.title} x {quantity}",
    }

    khalti_request = urllib_request.Request(
        "https://dev.khalti.com/api/v2/epayment/initiate/",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Key {khalti_secret_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(khalti_request, timeout=20) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        messages.error(request, f"Khalti request failed: {error_body or exc.reason}")
        return redirect("events")
    except Exception:
        messages.error(request, "Could not connect to Khalti right now.")
        return redirect("events")

    payment_url = response_data.get("payment_url")
    if not payment_url:
        messages.error(request, "Khalti did not return a payment URL.")
        return redirect("events")

    TicketPurchase.objects.create(
        user=request.user,
        event=event,
        quantity=quantity,
        total_amount=total_rupees,
        status=TicketPurchase.STATUS_INITIATED,
        khalti_pidx=response_data.get("pidx"),
        purchase_order_id=payload["purchase_order_id"],
    )

    return redirect(payment_url)


def khalti_return(request):
    status = request.GET.get("status")
    pidx = request.GET.get("pidx")
    txn_id = request.GET.get("transaction_id")

    ticket = None
    if pidx and request.user.is_authenticated:
        ticket = (
            TicketPurchase.objects.filter(user=request.user, khalti_pidx=pidx)
            .order_by("-created_at")
            .first()
        )

    if status == "Completed":
        if ticket:
            ticket.status = TicketPurchase.STATUS_COMPLETED
            ticket.khalti_txn_id = txn_id or ticket.khalti_txn_id
            ticket.save(update_fields=["status", "khalti_txn_id"])
        messages.success(request, "Payment completed successfully.")
    elif status == "User canceled":
        if ticket:
            ticket.status = TicketPurchase.STATUS_CANCELED
            ticket.khalti_txn_id = txn_id or ticket.khalti_txn_id
            ticket.save(update_fields=["status", "khalti_txn_id"])
        messages.warning(request, "Payment was canceled.")
    else:
        if ticket:
            ticket.status = TicketPurchase.STATUS_FAILED
            ticket.khalti_txn_id = txn_id or ticket.khalti_txn_id
            ticket.save(update_fields=["status", "khalti_txn_id"])
        messages.info(request, "Payment response received from Khalti.")

    return redirect("events")


@login_required
def tickets_view(request):
    tickets = (
        TicketPurchase.objects.filter(user=request.user, status=TicketPurchase.STATUS_COMPLETED)
        .select_related("event", "event__venue")
        .order_by("-created_at")
    )
    return render(request, "tickets.html", {"tickets": tickets})
