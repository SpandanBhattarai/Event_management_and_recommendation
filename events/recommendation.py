import math
from collections import Counter
from django.utils import timezone
from .models import Event, TicketPurchase


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

    events = Event.objects.filter(is_active=True).select_related("category", "venue")
    scored_events = []

    user_lat = request.session.get("user_lat")
    user_lng = request.session.get("user_lng")
    user_budget = request.session.get("budget")
    user_category = request.session.get("preferred_category")

    # Learn user category preference from purchased ticket history.
    category_counts = Counter()
    max_category_count = 0
    if request.user.is_authenticated:
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

    for event in events:

        #Category Match
        category_score = 0
        if user_category and event.category:
            if event.category.name == user_category:
                category_score = 1

        # History category boost based on user's completed purchases.
        history_category_score = 0
        if event.category and max_category_count > 0:
            history_category_score = (
                category_counts.get(event.category_id, 0) / max_category_count
            )

        # Keeping the explicit preference strongest, but include purchase behavior.
        category_score = max(category_score, history_category_score)

        #Budget Match
        budget_score = 0
        if user_budget:
            budget_difference = abs(float(event.price) - float(user_budget))
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
    
# to show scores in the terminal for testing purposes
    for event, score in scored_events:
        print(f"Event: {event.title}, Score: {score:.4f}")

    return [event[0] for event in scored_events]
