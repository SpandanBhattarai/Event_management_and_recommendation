import logging
import math
from collections import Counter
from django.utils import timezone
from .models import Event, TicketPurchase, UserPreference

# module logger
logger = logging.getLogger(__name__)

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


def calculate_final_score(category_score, budget_score, distance_score, popularity_score, recency_score):
    return (
        (category_score * 0.30)
        + (budget_score * 0.20)
        + (distance_score * 0.15)
        + (popularity_score * 0.15)
        + (recency_score * 0.20)
    )

# MAIN FUNCTION
def get_recommended_events(request):

    events = Event.objects.filter(
        is_active=True,
        approval_status=Event.APPROVAL_APPROVED,
    ).select_related("category", "venue")
    scored_events = []

    user_lat = request.session.get("user_lat")
    user_lng = request.session.get("user_lng")
    # Use saved profile preferences as primary source.
    # Session values are kept as fallback for older flows.
    user_budget = None
    user_category = None
    user_category_id = None
    user_category_name = None

    # Learn user category preference from purchased ticket history.
    category_counts = Counter()
    max_category_count = 0
    if request.user.is_authenticated:
        # Always read latest preferences from DB to avoid stale relation cache.
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
        # coerce session value to float and handle bad data
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
    has_explicit_category_preference = bool(user_category_id or user_category_name)

    print(
        f"[reco] user={request.user.username if request.user.is_authenticated else 'anon'} "
        f"budget={user_budget} category_id={user_category_id} category_name={user_category_name} "
        f"lat={user_lat} lng={user_lng}",
        flush=True,
    )

    for event in events:

        category_score = get_category_score(
            event,
            user_category_id=user_category_id,
            user_category_name=user_category_name,
            has_explicit_category_preference=has_explicit_category_preference,
            category_counts=category_counts,
            max_category_count=max_category_count,
        )

        #Budget Match
        budget_score = get_budget_score(event.price, user_budget)

        #Distance Score
        distance_score = 0
        if user_lat and user_lng:
            distance = calculate_distance(
                float(user_lat),
                float(user_lng),
                event.venue.latitude,
                event.venue.longitude,
            )
            distance_score = get_distance_score(distance)

        #Popularity Score
        popularity_score = normalize(event.popularity, 5)

        #Upcoming Events Boost
        recency_score = get_recency_score(event)

        #Weighted Final Score
        final_score = calculate_final_score(
            category_score,
            budget_score,
            distance_score,
            popularity_score,
            recency_score,
        )

        scored_events.append((event, final_score))

    # Sort descending
    scored_events.sort(key=lambda x: x[1], reverse=True)

    # show the calculated score in the terminal for debugging
    for event, score in scored_events:
        category_score = get_category_score(
            event,
            user_category_id=user_category_id,
            user_category_name=user_category_name,
            has_explicit_category_preference=has_explicit_category_preference,
            category_counts=category_counts,
            max_category_count=max_category_count,
        )

        budget_score = get_budget_score(event.price, user_budget)

        distance_score = 0
        if user_lat and user_lng:
            distance = calculate_distance(
                float(user_lat),
                float(user_lng),
                event.venue.latitude,
                event.venue.longitude,
            )
            distance_score = get_distance_score(distance)

        popularity_score = normalize(event.popularity, 5)
        recency_score = get_recency_score(event)

        print(
            f"Event: {event.title} | "
            f"cat={category_score:.4f}({category_score * 0.30:.4f}) "
            f"budget={budget_score:.4f}({budget_score * 0.20:.4f}) "
            f"dist={distance_score:.4f}({distance_score * 0.15:.4f}) "
            f"pop={popularity_score:.4f}({popularity_score * 0.15:.4f}) "
            f"recency={recency_score:.4f}({recency_score * 0.20:.4f}) "
            f"total={score:.4f}",
            flush=True,
        )
    
    return [event[0] for event in scored_events]


def get_event_final_score(request, event):
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
                user_budget = None

    if not user_category_id:
        user_category = request.session.get("preferred_category")

    if user_category:
        if str(user_category).isdigit():
            user_category_id = int(user_category)
        else:
            user_category_name = str(user_category).strip().lower()
    has_explicit_category_preference = bool(user_category_id or user_category_name)

    category_score = get_category_score(
        event,
        user_category_id=user_category_id,
        user_category_name=user_category_name,
        has_explicit_category_preference=has_explicit_category_preference,
        category_counts=category_counts,
        max_category_count=max_category_count,
    )
    budget_score = get_budget_score(event.price, user_budget)

    distance_score = 0
    if user_lat and user_lng:
        distance = calculate_distance(
            float(user_lat),
            float(user_lng),
            event.venue.latitude,
            event.venue.longitude,
        )
        distance_score = get_distance_score(distance)

    popularity_score = normalize(event.popularity, 5)
    recency_score = get_recency_score(event)

    final_score = calculate_final_score(
        category_score,
        budget_score,
        distance_score,
        popularity_score,
        recency_score,
    )
    return final_score
