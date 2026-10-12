from datetime import timedelta

from django.utils import timezone

from delivery_partner.geo_utils import haversine_km
from delivery_partner.models import DeliveryPartner


ACTIVE_DP_STATUSES = [
    "accepted",
    "arrived_at_shop",
    "picked_up",
    "arrived_at_buyer",
]


def find_nearby_delivery_partners(
    vendor,
    radius_km=5,
    max_location_age_minutes=5,
):
    """
    Return eligible (DeliveryPartner, distance_km) tuples,
    sorted nearest first.
    """
    if vendor.latitude is None or vendor.longitude is None:
        return []

    try:
        haversine_km(
            vendor.latitude,
            vendor.longitude,
            vendor.latitude,
            vendor.longitude,
        )
    except (ValueError, TypeError):
        return []

    cutoff = timezone.now() - timedelta(
        minutes=max_location_age_minutes
    )

    candidates = (
        DeliveryPartner.objects
        .select_related("user")
        .filter(
            status="approved",
            is_online=True,
            user__user_type="delivery_partner",
            current_latitude__isnull=False,
            current_longitude__isnull=False,
            location_updated_at__gte=cutoff,
        )
    )

    results = []

    for dp in candidates:
        # Check active deliveries separately to avoid excluding
        # partners merely because they have completed past orders.
        has_active_delivery = dp.user.deliveries.filter(
            dp_status__in=ACTIVE_DP_STATUSES,
        ).exclude(
            status__in=["cancelled", "rejected", "delivered"]
        ).exists()

        if has_active_delivery:
            continue

        try:
            distance = haversine_km(
                vendor.latitude,
                vendor.longitude,
                dp.current_latitude,
                dp.current_longitude,
            )
        except (ValueError, TypeError):
            continue

        if distance <= radius_km:
            results.append((dp, distance))

    results.sort(key=lambda item: (item[1], str(item[0].id)))

    return results
