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

        #Category Match
        category_score = 0
        if event.category:
            if user_category_id and event.category_id == user_category_id:
                category_score = 1
            elif user_category_name and event.category.name.lower() == user_category_name:
                category_score = 1

        # History category boost is fallback only when explicit preference is not set.
        if (not has_explicit_category_preference) and event.category and max_category_count > 0:
            category_score = category_counts.get(event.category_id, 0) / max_category_count

        #Budget Match
        budget_score = 0
        if user_budget is not None:
            # user_budget is guaranteed to be numeric (float) or None
            budget_difference = abs(float(event.price) - user_budget)
            budget_score = 1 / (1 + budget_difference)

        #Distance Score
        distance_score = 0
        if user_lat and user_lng:
            distance = calculate_distance(
                float(user_lat),
                float(user_lng),
                event.venue.latitude,
                event.venue.longitude,
            )
            distance_score = 1 / (1 + distance)

        #Popularity Score
        popularity_score = normalize(event.popularity, 5)

        #Upcoming Events Boost
        recency_score = 1 if event.start_date > timezone.now() else 0

        #Weighted Final Score
        final_score = (
            (category_score * 0.3)
            + (budget_score * 0.2)
            + (distance_score * 0.25)
            + (popularity_score * 0.15)
            + (recency_score * 0.1)
        )

        scored_events.append((event, final_score))

    # Sort descending
    scored_events.sort(key=lambda x: x[1], reverse=True)

    # show the calculated score in the terminal for debugging
    for event, score in scored_events:
        category_score = 0
        if event.category:
            if user_category_id and event.category_id == user_category_id:
                category_score = 1
            elif user_category_name and event.category.name.lower() == user_category_name:
                category_score = 1
            elif (not has_explicit_category_preference) and max_category_count > 0:
                category_score = category_counts.get(event.category_id, 0) / max_category_count

        budget_score = 0
        if user_budget is not None:
            budget_difference = abs(float(event.price) - user_budget)
            budget_score = 1 / (1 + budget_difference)

        distance_score = 0
        if user_lat and user_lng:
            distance = calculate_distance(
                float(user_lat),
                float(user_lng),
                event.venue.latitude,
                event.venue.longitude,
            )
            distance_score = 1 / (1 + distance)

        popularity_score = normalize(event.popularity, 5)
        recency_score = 1 if event.start_date > timezone.now() else 0

        print(
            f"Event: {event.title} | "
            f"cat={category_score:.4f}({category_score * 0.3:.4f}) "
            f"budget={budget_score:.4f}({budget_score * 0.2:.4f}) "
            f"dist={distance_score:.4f}({distance_score * 0.25:.4f}) "
            f"pop={popularity_score:.4f}({popularity_score * 0.15:.4f}) "
            f"recency={recency_score:.4f}({recency_score * 0.1:.4f}) "
            f"total={score:.4f}",
            flush=True,
        )
    
    return [event[0] for event in scored_events]
