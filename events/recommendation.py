import logging
import math
from collections import Counter
from datetime import timedelta
from django.db.models import IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Event, TicketPurchase, UserPreference

# module logger
logger = logging.getLogger(__name__)

NEARBY_REASON_DISTANCE_KM = 15
BUDGET_REASON_MIN_SCORE = 0.7

# Haversine Formula
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def normalize(value, max_value):
    if max_value == 0:
        return 0
    return value / max_value


def clamp_score(value):
    return max(0.0, min(1.0, value))


def get_distance_score(distance_km, max_distance_km=50):
    try:
        distance_value = float(distance_km)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, 1.0 - (distance_value / max_distance_km))


def get_category_score(
    event,
    user_category_id=None,
    user_category_name=None,
    has_explicit_category_preference=False,
    category_counts=None,
    max_category_count=0,
):
    category_counts = category_counts or Counter()
    if not event.category:
        return 0.0

    explicit_score = 0.0
    if user_category_id and event.category_id == user_category_id:
        explicit_score = 1.0
    elif user_category_name and event.category.name.lower() == user_category_name:
        explicit_score = 1.0

    history_score = 0.0
    if max_category_count > 0:
        history_score = category_counts.get(event.category_id, 0) / max_category_count

    # If user has explicit category preference, give it higher weight. Otherwise rely solely on history score.
    if has_explicit_category_preference:
        if max_category_count > 0:
            return (explicit_score * 0.8) + (history_score * 0.2)
        return explicit_score

    return history_score


def get_budget_score(event_price, user_budget):
    if user_budget is None:
        return 0.0

    try:
        event_price_value = float(event_price)
        budget_value = float(user_budget)
    except (TypeError, ValueError):
        return 0.0

    # Normalize price difference by budget so scores are comparable across cheap and expensive users.
    diff_ratio = abs(event_price_value - budget_value) / max(budget_value, 1.0)
    return max(0.0, 1.0 - diff_ratio)


def get_recency_score(event, now=None, horizon_days=30):
        now = now or timezone.now()
        if event.end_date <=  now:
         return 0.0

        if event.start_date <= now < event.end_date:
            return 1.0
        days_until_start= (event.start_date - now).total_seconds() / 86400
        return max(0.0, 1.0 - (days_until_start / horizon_days))

#calculating the final score by combining all the individual scores with their respective weights
def calculate_final_score(category_score, budget_score, distance_score, popularity_score, recency_score):
    return (
        (category_score * 0.30)
        + (budget_score * 0.20)
        + (distance_score * 0.15)
        + (popularity_score * 0.15)
        + (recency_score * 0.20)
    )


def _build_category_popularity_baselines():
    finished_events = (
        Event.objects.filter(
            is_finished=True,
            approval_status=Event.APPROVAL_APPROVED,
            category__isnull=False,
        )
        .select_related("venue")
        .annotate(
            sold_tickets=Coalesce(
                Sum(
                    "ticket_purchases__quantity",
                    filter=Q(ticket_purchases__status=TicketPurchase.STATUS_COMPLETED),
                ),
                Value(0, output_field=IntegerField()),
            )
        )
    )

    category_scores = {}
    for event in finished_events:
        capacity = max(getattr(event.venue, "capacity", 0) or 0, 1)
        fill_ratio = clamp_score(event.sold_tickets / capacity)
        category_scores.setdefault(event.category_id, []).append(fill_ratio)

    return {
        category_id: (sum(scores) / len(scores))
        for category_id, scores in category_scores.items()
        if scores
    }


def get_event_popularity_score(event, context=None, now=None):
    now = now or timezone.now()
    context = context or {}

    capacity = max(getattr(event.venue, "capacity", 0) or 0, 1)
    baseline_score = normalize(getattr(event, "popularity", 1) or 1, 5)
    category_baseline = context.get("category_popularity_baselines", {}).get(event.category_id, baseline_score)

    sold_tickets = (
        TicketPurchase.objects.filter(
            event=event,
            status=TicketPurchase.STATUS_COMPLETED,
        ).aggregate(total=Coalesce(Sum("quantity"), 0)).get("total")
        or 0
    )
    recent_tickets = (
        TicketPurchase.objects.filter(
            event=event,
            status=TicketPurchase.STATUS_COMPLETED,
            created_at__gte=now - timedelta(days=7),
        ).aggregate(total=Coalesce(Sum("quantity"), 0)).get("total")
        or 0
    )

    sold_ratio = clamp_score(sold_tickets / capacity)
    recent_demand_score = clamp_score(recent_tickets / max(capacity * 0.25, 1))

    if sold_tickets or recent_tickets:
        return clamp_score(
            (sold_ratio * 0.50)
            + (recent_demand_score * 0.25)
            + (category_baseline * 0.15)
            + (baseline_score * 0.10)
        )

    return clamp_score((category_baseline * 0.70) + (baseline_score * 0.30))


def _build_recommendation_context(request):
    user_lat = request.session.get("user_lat")
    user_lng = request.session.get("user_lng")
    user_budget = None
    user_category = None
    user_category_id = None
    user_category_name = None

    category_counts = Counter()
    max_category_count = 0
    if request.user.is_authenticated:
        preferences = (
            UserPreference.objects.filter(user_id=request.user.id)
            .only("budget", "favorite_category_id")
            .first()
        )
        if preferences:
            if preferences.budget is not None:
                user_budget = float(preferences.budget)
            if preferences.favorite_category_id:
                user_category_id = preferences.favorite_category_id
        purchased_tickets = (
            TicketPurchase.objects.filter(
                user=request.user,
                status=TicketPurchase.STATUS_COMPLETED,
                event__category__isnull=False,
            )
            .select_related("event__category")
        )
        category_counts = Counter(ticket.event.category_id for ticket in purchased_tickets)
        if category_counts:
            max_category_count = max(category_counts.values())

    if user_budget is None:
        user_budget = request.session.get("budget")
        if user_budget is not None:
            try:
                user_budget = float(user_budget)
            except (ValueError, TypeError):
                logger.warning("Invalid budget value in session: %r", user_budget)
                user_budget = None

    if not user_category_id:
        user_category = request.session.get("preferred_category")

    if user_category:
        if str(user_category).isdigit():
            user_category_id = int(user_category)
        else:
            user_category_name = str(user_category).strip().lower()

    return {
        "user_lat": user_lat,
        "user_lng": user_lng,
        "user_budget": user_budget,
        "user_category_id": user_category_id,
        "user_category_name": user_category_name,
        "has_explicit_category_preference": bool(user_category_id or user_category_name),
        "category_counts": category_counts,
        "max_category_count": max_category_count,
        "category_popularity_baselines": _build_category_popularity_baselines(),
    }


def _get_recommendation_data_for_event(event, context):
    category_score = get_category_score(
        event,
        user_category_id=context["user_category_id"],
        user_category_name=context["user_category_name"],
        has_explicit_category_preference=context["has_explicit_category_preference"],
        category_counts=context["category_counts"],
        max_category_count=context["max_category_count"],
    )
    budget_score = get_budget_score(event.price, context["user_budget"])

    distance = None
    distance_score = 0.0
    if context["user_lat"] and context["user_lng"]:
        distance = calculate_distance(
            float(context["user_lat"]),
            float(context["user_lng"]),
            event.venue.latitude,
            event.venue.longitude,
        )
        distance_score = get_distance_score(distance)

    popularity_score = get_event_popularity_score(event, context=context)
    recency_score = get_recency_score(event)
    final_score = calculate_final_score(
        category_score,
        budget_score,
        distance_score,
        popularity_score,
        recency_score,
    )

    reasons = []
    if context["has_explicit_category_preference"] and category_score >= 0.8:
        reasons.append("Matches your preferred category")
    if distance is not None and distance <= NEARBY_REASON_DISTANCE_KM:
        reasons.append("Near your location")
    if context["user_budget"] is not None and budget_score >= BUDGET_REASON_MIN_SCORE:
        reasons.append("Fits your budget")
    if not reasons and recency_score >= 0.75:
        reasons.append("Happening soon")
    if len(reasons) < 2 and popularity_score >= 0.8:
        reasons.append("Popular with attendees")

    return {
        "category_score": category_score,
        "budget_score": budget_score,
        "distance": distance,
        "distance_score": distance_score,
        "popularity_score": popularity_score,
        "recency_score": recency_score,
        "final_score": final_score,
        "reasons": reasons[:3],
    }

# MAIN FUNCTION
def get_recommended_events(request):

    events = Event.objects.filter(
        is_active=True,
        is_finished=False,
        approval_status=Event.APPROVAL_APPROVED,
    ).select_related("category", "venue")
    scored_events = []

    context = _build_recommendation_context(request)

    print(
        f"[reco] user={request.user.username if request.user.is_authenticated else 'anon'} "
        f"budget={context['user_budget']} category_id={context['user_category_id']} category_name={context['user_category_name']} "
        f"lat={context['user_lat']} lng={context['user_lng']}",
        flush=True,
    )

    for event in events:
        recommendation_data = _get_recommendation_data_for_event(event, context)
        event.recommendation_reasons = recommendation_data["reasons"]
        scored_events.append((event, recommendation_data["final_score"], recommendation_data))

    # Sort descending
    scored_events.sort(key=lambda x: x[1], reverse=True)

    # show the calculated score in the terminal for debugging
    for event, score, recommendation_data in scored_events:
        print(
            f"Event: {event.title} | "
            f"cat={recommendation_data['category_score']:.4f}({recommendation_data['category_score'] * 0.30:.4f}) "
            f"budget={recommendation_data['budget_score']:.4f}({recommendation_data['budget_score'] * 0.20:.4f}) "
            f"dist={recommendation_data['distance_score']:.4f}({recommendation_data['distance_score'] * 0.15:.4f}) "
            f"pop={recommendation_data['popularity_score']:.4f}({recommendation_data['popularity_score'] * 0.15:.4f}) "
            f"recency={recommendation_data['recency_score']:.4f}({recommendation_data['recency_score'] * 0.20:.4f}) "
            f"total={score:.4f}",
            flush=True,
        )
    
    return [event for event, _, _ in scored_events]


def get_event_final_score(request, event):
    return get_event_recommendation_data(request, event)["final_score"]


def get_event_recommendation_data(request, event):
    context = _build_recommendation_context(request)
    return _get_recommendation_data_for_event(event, context)
