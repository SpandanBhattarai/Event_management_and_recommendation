import json
import uuid
import csv
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, IntegerField, Q, Sum, Value
from django.db.models.functions import TruncMonth
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils import timezone
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_POST
from .models import AuditLog, Category, Event, TicketPurchase, UserPreference, UserRole, Venue
from .recommendation import get_recommended_events
from .roles import get_user_role, role_required
from .forms import OrganizerEventForm


def log_admin_action(actor, action, target_user=None, event=None, ticket_purchase=None, details=""):
    AuditLog.objects.create(
        actor=actor,
        action=action,
        target_user=target_user,
        event=event,
        ticket_purchase=ticket_purchase,
        details=details,
    )


def home(request):
    events = (
        Event.objects.filter(is_active=True, approval_status=Event.APPROVAL_APPROVED)
        .select_related("venue", "category")
        .order_by("start_date")[:3]
    )
    recommended_events = []
    if request.user.is_authenticated:
        get_user_role(request.user)
        recommended_events = get_recommended_events(request)[:3]
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
        UserRole.objects.get_or_create(user=user, defaults={"role": UserRole.ROLE_USER})

        login(request, user)
        return redirect("home")

    return render(request, "register.html")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            default_role = (
                UserRole.ROLE_ADMIN
                if user.is_superuser or user.username.lower() == "spandan"
                else UserRole.ROLE_USER
            )
            UserRole.objects.get_or_create(user=user, defaults={"role": default_role})
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
        Event.objects.filter(is_active=True, approval_status=Event.APPROVAL_APPROVED)
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


def event_detail(request, event_id):
    event = get_object_or_404(
        Event,
        id=event_id,
        is_active=True,
        approval_status=Event.APPROVAL_APPROVED,
    )
    return render(request, "event_detail.html", {"event": event})


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
def profile_preferences_view(request):
    categories = Category.objects.order_by("name")
    preferences, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        if request.POST.get("action") == "clear_preferences":
            preferences.favorite_category = None
            preferences.budget = None
            preferences.save(update_fields=["favorite_category", "budget", "updated_at"])
            request.session.pop("preferred_category", None)
            request.session.pop("budget", None)
            request.session.modified = True
            
            return redirect("profile_preferences")

        request.user.first_name = request.POST.get("first_name", "").strip()
        request.user.last_name = request.POST.get("last_name", "").strip()
        request.user.email = request.POST.get("email", "").strip()
        request.user.save(update_fields=["first_name", "last_name", "email"])

        category_id = request.POST.get("favorite_category", "").strip()
        budget_raw = request.POST.get("budget", "").strip()

        preferences.favorite_category = None
        if category_id:
            preferences.favorite_category = Category.objects.filter(id=category_id).first()

        preferences.budget = None
        if budget_raw:
            try:
                budget_value = Decimal(budget_raw)
                if budget_value < 0:
                    raise InvalidOperation
                preferences.budget = budget_value
            except (InvalidOperation, TypeError):
                messages.error(request, "Budget must be a valid non-negative number.")
                return redirect("profile_preferences")

        preferences.save()

        if preferences.favorite_category:
            request.session["preferred_category"] = str(preferences.favorite_category.id)
        else:
            request.session.pop("preferred_category", None)

        if preferences.budget is not None:
            request.session["budget"] = float(preferences.budget)
        else:
            request.session.pop("budget", None)
        request.session.modified = True

        messages.success(request, "Profile and preferences updated.")
        return redirect("profile_preferences")

    return render(
        request,
        "profile_preferences.html",
        {"categories": categories, "preferences": preferences},
    )


@login_required
def buy_ticket(request, event_id):
    if request.method != "POST":
        return redirect("event_detail", event_id=event_id)

    event = get_object_or_404(
        Event,
        id=event_id,
        is_active=True,
        approval_status=Event.APPROVAL_APPROVED,
    )
    payment_method = request.POST.get("payment_method", "khalti").strip().lower()
    quantity_raw = request.POST.get("ticket_quantity", "1")

    try:
        quantity = int(quantity_raw)
    except ValueError:
        messages.error(request, "Invalid ticket quantity.")
        return redirect("event_detail", event_id=event_id)

    if quantity < 1 or quantity > 10:
        messages.error(request, "Please select between 1 and 10 tickets.")
        return redirect("event_detail", event_id=event_id)

    if payment_method and payment_method != "khalti":
        messages.error(request, "Selected payment method is not available.")
        return redirect("event_detail", event_id=event_id)

    try:
        total_rupees = Decimal(event.price) * Decimal(quantity)
    except (InvalidOperation, TypeError):
        messages.error(request, "Unable to calculate ticket price.")
        return redirect("event_detail", event_id=event_id)

    total_paisa = int(total_rupees * 100)
    khalti_secret_key = getattr(settings, "KHALTI_SECRET_KEY", "")
    if not khalti_secret_key:
        messages.error(request, "Khalti is not configured. Add KHALTI_SECRET_KEY in settings.")
        return redirect("event_detail", event_id=event_id)

    return_url = request.build_absolute_uri(reverse("khalti_return"))
    website_url = request.build_absolute_uri(reverse("event_detail", args=[event.id]))

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
        return redirect("event_detail", event_id=event_id)
    except Exception:
        messages.error(request, "Could not connect to Khalti right now.")
        return redirect("event_detail", event_id=event_id)

    payment_url = response_data.get("payment_url")
    if not payment_url:
        messages.error(request, "Khalti did not return a payment URL.")
        return redirect("event_detail", event_id=event_id)

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

    if ticket:
        return redirect("event_detail", event_id=ticket.event_id)
    return redirect("events")


@login_required
def tickets_view(request):
    tickets = (
        TicketPurchase.objects.filter(user=request.user, status=TicketPurchase.STATUS_COMPLETED)
        .select_related("event", "event__venue")
        .order_by("-created_at")
    )
    return render(request, "tickets.html", {"tickets": tickets})


@login_required
@role_required(UserRole.ROLE_ADMIN)
def admin_dashboard(request):
    total_events = Event.objects.count()
    active_events = Event.objects.filter(is_active=True).count()
    pending_events_count = Event.objects.filter(approval_status=Event.APPROVAL_PENDING).count()
    total_venues = Venue.objects.count()
    total_users = User.objects.count()
    total_sales = (
        TicketPurchase.objects.filter(status=TicketPurchase.STATUS_COMPLETED)
        .aggregate(total=Sum("total_amount"))
        .get("total")
        or Decimal("0.00")
    )
    total_transactions = TicketPurchase.objects.count()
    failed_transactions = TicketPurchase.objects.filter(status=TicketPurchase.STATUS_FAILED).count()
    top_earning_event = (
        Event.objects.filter(ticket_purchases__status=TicketPurchase.STATUS_COMPLETED)
        .annotate(
            total_revenue=Coalesce(
                Sum("ticket_purchases__total_amount"),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=10, decimal_places=2)),
            )
        )
        .order_by("-total_revenue")
        .first()
    )

    payment_status_filter = request.GET.get("payment_status", "").strip()
    payment_user_filter = request.GET.get("payment_user", "").strip()
    payment_event_filter = request.GET.get("payment_event", "").strip()
    payment_date_from = request.GET.get("payment_date_from", "").strip()
    payment_date_to = request.GET.get("payment_date_to", "").strip()

    payment_qs = TicketPurchase.objects.select_related("event", "user").order_by("-created_at")
    if payment_status_filter:
        payment_qs = payment_qs.filter(status=payment_status_filter)
    if payment_user_filter and payment_user_filter.isdigit():
        payment_qs = payment_qs.filter(user_id=int(payment_user_filter))
    if payment_event_filter and payment_event_filter.isdigit():
        payment_qs = payment_qs.filter(event_id=int(payment_event_filter))
    if payment_date_from:
        payment_qs = payment_qs.filter(created_at__date__gte=payment_date_from)
    if payment_date_to:
        payment_qs = payment_qs.filter(created_at__date__lte=payment_date_to)

    payment_rows = payment_qs[:50]

    users = (
        User.objects.all()
        .annotate(
            purchase_count=Count("ticket_purchases"),
            completed_purchase_count=Count(
                "ticket_purchases",
                filter=Q(ticket_purchases__status=TicketPurchase.STATUS_COMPLETED),
            ),
        )
        .order_by("username")
    )
    user_roles = {r.user_id: r.role for r in UserRole.objects.filter(user_id__in=users.values_list("id", flat=True))}
    user_rows = [{"account": u, "role": user_roles.get(u.id, UserRole.ROLE_USER)} for u in users]

    purchases = TicketPurchase.objects.select_related("event", "user").order_by("-created_at")[:10]
    pending_events = (
        Event.objects.filter(approval_status=Event.APPROVAL_PENDING)
        .select_related("venue", "category", "organizer")
        .order_by("start_date")
    )[:20]
    audit_logs = AuditLog.objects.select_related("actor", "target_user", "event", "ticket_purchase")[:30]
    payment_filter_users = User.objects.order_by("username")
    payment_filter_events = Event.objects.order_by("title")
    return render(
        request,
        "admin_dashboard.html",
        {
            "total_events": total_events,
            "active_events": active_events,
            "pending_events_count": pending_events_count,
            "total_venues": total_venues,
            "total_users": total_users,
            "total_sales": total_sales,
            "total_transactions": total_transactions,
            "failed_transactions": failed_transactions,
            "top_earning_event": top_earning_event,
            "recent_purchases": purchases,
            "pending_events": pending_events,
            "user_rows": user_rows,
            "payment_rows": payment_rows,
            "payment_filter_users": payment_filter_users,
            "payment_filter_events": payment_filter_events,
            "selected_payment_status": payment_status_filter,
            "selected_payment_user": payment_user_filter,
            "selected_payment_event": payment_event_filter,
            "selected_payment_date_from": payment_date_from,
            "selected_payment_date_to": payment_date_to,
            "audit_logs": audit_logs,
        },
    )


@login_required
@role_required(UserRole.ROLE_ADMIN)
@require_POST
def admin_event_approval_action(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    action = request.POST.get("action", "").strip().lower()

    if action == "approve":
        event.approval_status = Event.APPROVAL_APPROVED
        event.approved_by = request.user
        event.approved_at = timezone.now()
        event.save(update_fields=["approval_status", "approved_by", "approved_at"])
        log_admin_action(
            request.user,
            AuditLog.ACTION_EVENT_APPROVED,
            target_user=event.organizer,
            event=event,
            details=f"Event approved by admin dashboard: {event.title}",
        )
        messages.success(request, f"Approved event: {event.title}")
    elif action == "reject":
        event.approval_status = Event.APPROVAL_REJECTED
        event.approved_by = request.user
        event.approved_at = timezone.now()
        event.save(update_fields=["approval_status", "approved_by", "approved_at"])
        log_admin_action(
            request.user,
            AuditLog.ACTION_EVENT_REJECTED,
            target_user=event.organizer,
            event=event,
            details=f"Event rejected by admin dashboard: {event.title}",
        )
        messages.warning(request, f"Rejected event: {event.title}")
    else:
        messages.error(request, "Invalid action.")

    return redirect("admin_dashboard")


@login_required
@require_POST
@role_required(UserRole.ROLE_ADMIN)
def admin_user_role_action(request, user_id):
    target = get_object_or_404(User, id=user_id)
    new_role = request.POST.get("role", "").strip().lower()
    allowed_roles = {UserRole.ROLE_ADMIN, UserRole.ROLE_ORGANIZER, UserRole.ROLE_USER}
    if new_role not in allowed_roles:
        messages.error(request, "Invalid role selected.")
        return redirect("admin_dashboard")

    role_profile, _ = UserRole.objects.get_or_create(user=target)
    old_role = role_profile.role
    role_profile.role = new_role
    role_profile.save(update_fields=["role", "updated_at"])
    log_admin_action(
        request.user,
        AuditLog.ACTION_ROLE_CHANGED,
        target_user=target,
        details=f"Role changed from {old_role} to {new_role}.",
    )
    messages.success(request, f"Updated role for {target.username} to {new_role}.")
    return redirect("admin_dashboard")


@login_required
@require_POST
@role_required(UserRole.ROLE_ADMIN)
def admin_user_activation_action(request, user_id):
    target = get_object_or_404(User, id=user_id)
    action = request.POST.get("action", "").strip().lower()

    if action == "activate":
        target.is_active = True
        target.save(update_fields=["is_active"])
        log_admin_action(
            request.user,
            AuditLog.ACTION_USER_ACTIVATED,
            target_user=target,
            details=f"User activated: {target.username}",
        )
        messages.success(request, f"Activated user: {target.username}")
    elif action == "deactivate":
        if target.id == request.user.id:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect("admin_dashboard")
        target.is_active = False
        target.save(update_fields=["is_active"])
        log_admin_action(
            request.user,
            AuditLog.ACTION_USER_DEACTIVATED,
            target_user=target,
            details=f"User deactivated: {target.username}",
        )
        messages.warning(request, f"Deactivated user: {target.username}")
    else:
        messages.error(request, "Invalid activation action.")

    return redirect("admin_dashboard")


@login_required
@role_required(UserRole.ROLE_ADMIN, UserRole.ROLE_ORGANIZER)
def organizer_dashboard(request):
    now = timezone.now()
    today = now.date()
    week_start = today - timedelta(days=6)

    base_events = Event.objects.select_related("venue", "category", "organizer")
    if get_user_role(request.user) != UserRole.ROLE_ADMIN:
        base_events = base_events.filter(organizer=request.user)

    purchases = TicketPurchase.objects.filter(
        status=TicketPurchase.STATUS_COMPLETED,
        event__in=base_events,
    )
    today_sales = purchases.filter(created_at__date=today).aggregate(total=Sum("total_amount")).get("total") or Decimal("0.00")
    weekly_sales = (
        purchases.filter(created_at__date__gte=week_start)
        .aggregate(total=Sum("total_amount"))
        .get("total")
        or Decimal("0.00")
    )
    my_events_count = base_events.count()
    my_total_revenue = purchases.aggregate(total=Sum("total_amount")).get("total") or Decimal("0.00")
    total_tickets_sold = purchases.aggregate(total=Sum("quantity")).get("total") or 0
    upcoming_events_count = base_events.filter(start_date__gte=now, is_active=True).count()

    event_rows = (
        base_events.annotate(
            sold_tickets=Coalesce(
                Sum(
                    "ticket_purchases__quantity",
                    filter=Q(ticket_purchases__status=TicketPurchase.STATUS_COMPLETED),
                ),
                Value(0, output_field=IntegerField()),
            ),
            revenue=Coalesce(
                Sum(
                    "ticket_purchases__total_amount",
                    filter=Q(ticket_purchases__status=TicketPurchase.STATUS_COMPLETED),
                ),
                Value(
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                ),
            ),
        )
        .order_by("start_date")
    )
    event_query = request.GET.get("event_q", "").strip()
    if event_query:
        event_rows = event_rows.filter(
            Q(title__icontains=event_query)
            | Q(venue__name__icontains=event_query)
            | Q(venue__city__icontains=event_query)
            | Q(category__name__icontains=event_query)
        )
    event_paginator = Paginator(event_rows, 8)
    event_page_obj = event_paginator.get_page(request.GET.get("event_page"))

    monthly_raw = (
        purchases.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("total_amount"))
        .order_by("month")
    )
    monthly_labels = [row["month"].strftime("%b %Y") for row in monthly_raw if row.get("month")]
    monthly_revenue = [float(row["total"] or 0) for row in monthly_raw]

    attendee_rows = purchases.select_related("event", "user").order_by("-created_at")
    attendee_query = request.GET.get("attendee_q", "").strip()
    if attendee_query:
        attendee_rows = attendee_rows.filter(
            Q(user__username__icontains=attendee_query)
            | Q(user__email__icontains=attendee_query)
            | Q(event__title__icontains=attendee_query)
            | Q(purchase_order_id__icontains=attendee_query)
        )
    attendee_paginator = Paginator(attendee_rows, 12)
    attendee_page_obj = attendee_paginator.get_page(request.GET.get("attendee_page"))

    return render(
        request,
        "organizer_dashboard.html",
        {
            "events": event_page_obj,
            "my_events_count": my_events_count,
            "my_total_revenue": my_total_revenue,
            "today_sales": today_sales,
            "weekly_sales": weekly_sales,
            "total_tickets_sold": total_tickets_sold,
            "upcoming_events_count": upcoming_events_count,
            "monthly_labels": monthly_labels,
            "monthly_revenue": monthly_revenue,
            "monthly_labels_json": json.dumps(monthly_labels),
            "monthly_revenue_json": json.dumps(monthly_revenue),
            "attendees": attendee_page_obj,
            "event_q": event_query,
            "attendee_q": attendee_query,
        },
    )


def _organizer_event_queryset(request):
    qs = Event.objects.select_related("venue", "category", "organizer")
    if get_user_role(request.user) != UserRole.ROLE_ADMIN:
        qs = qs.filter(organizer=request.user)
    return qs


@login_required
@role_required(UserRole.ROLE_ADMIN, UserRole.ROLE_ORGANIZER)
def organizer_event_create(request):
    if request.method == "POST":
        form = OrganizerEventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            if get_user_role(request.user) != UserRole.ROLE_ADMIN:
                event.organizer = request.user
                event.approval_status = Event.APPROVAL_PENDING
                event.approved_by = None
                event.approved_at = None
            else:
                if not event.organizer:
                    event.organizer = request.user
            event.save()
            if get_user_role(request.user) != UserRole.ROLE_ADMIN:
                messages.info(request, "Event submitted for admin review.")
            else:
                messages.success(request, "Event created successfully.")
            return redirect("organizer_dashboard")
    else:
        form = OrganizerEventForm()

    return render(
        request,
        "organizer_event_form.html",
        {"form": form, "page_title": "Create Event", "submit_label": "Create Event"},
    )


@login_required
@role_required(UserRole.ROLE_ADMIN, UserRole.ROLE_ORGANIZER)
def organizer_event_edit(request, event_id):
    event = get_object_or_404(_organizer_event_queryset(request), id=event_id)
    if request.method == "POST":
        form = OrganizerEventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save(commit=False)
            if get_user_role(request.user) != UserRole.ROLE_ADMIN and not event.organizer:
                event.organizer = request.user
            event.save()
            messages.success(request, "Event updated.")
            return redirect("organizer_dashboard")
    else:
        initial = {
            "start_date": event.start_date.strftime("%Y-%m-%dT%H:%M") if event.start_date else "",
            "end_date": event.end_date.strftime("%Y-%m-%dT%H:%M") if event.end_date else "",
        }
        form = OrganizerEventForm(instance=event, initial=initial)

    return render(
        request,
        "organizer_event_form.html",
        {"form": form, "page_title": "Edit Event", "submit_label": "Save Changes", "event": event},
    )


@login_required
@require_POST
@role_required(UserRole.ROLE_ADMIN, UserRole.ROLE_ORGANIZER)
def organizer_event_delete(request, event_id):
    event = get_object_or_404(_organizer_event_queryset(request), id=event_id)
    event_title = event.title
    event.delete()
    messages.warning(request, f"Deleted event: {event_title}")
    return redirect("organizer_dashboard")


@login_required
@role_required(UserRole.ROLE_ADMIN, UserRole.ROLE_ORGANIZER)
def organizer_event_attendees_csv(request, event_id):
    event = get_object_or_404(_organizer_event_queryset(request), id=event_id)
    rows = (
        TicketPurchase.objects.filter(event=event, status=TicketPurchase.STATUS_COMPLETED)
        .select_related("user")
        .order_by("-created_at")
    )

    response = HttpResponse(content_type="text/csv")
    safe_title = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in event.title.lower())
    response["Content-Disposition"] = f'attachment; filename="attendees-{safe_title}.csv"'

    writer = csv.writer(response)
    writer.writerow(["username", "email", "quantity", "amount", "purchase_date", "order_id", "khalti_txn_id"])
    for purchase in rows:
        writer.writerow(
            [
                purchase.user.username,
                purchase.user.email,
                purchase.quantity,
                purchase.total_amount,
                purchase.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                purchase.purchase_order_id,
                purchase.khalti_txn_id or "",
            ]
        )
    return response
