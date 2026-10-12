from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from delivery_partner.matching import find_nearby_delivery_partners
from delivery_partner.models import DeliveryPartner
from vendors.models import Vendor


class NearbyDeliveryPartnerMatchingTests(TestCase):

    def setUp(self):
        User = get_user_model()

        seller = User.objects.create_user(
            phone_number="9000000301",
            full_name="GPS Matching Seller",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=seller,
            shop_name="GPS Matching Shop",
            category="grocery",
            phone_number="9000000301",
            address="Test Shop Address",
            town="Test Town",
            latitude=17.4123,
            longitude=78.4567,
        )

        self.partners = []

        for index, latitude in enumerate([17.4323, 17.4173, 17.4223], start=2):
            user = User.objects.create_user(
                phone_number=f"900000030{index}",
                full_name=f"Matching Partner {index}",
                user_type="delivery_partner",
            )

            dp = DeliveryPartner.objects.create(
                user=user,
                status="approved",
                is_online=True,
                current_latitude=latitude,
                current_longitude=78.4567,
                location_updated_at=timezone.now(),
            )

            self.partners.append(dp)

    def test_nearest_partner_is_first(self):
        results = find_nearby_delivery_partners(self.vendor)

        self.assertEqual(len(results), 3)

        distances = [distance for dp, distance in results]
        self.assertEqual(distances, sorted(distances))

        self.assertEqual(results[0][0].id, self.partners[1].id)
        self.assertEqual(results[1][0].id, self.partners[2].id)
        self.assertEqual(results[2][0].id, self.partners[0].id)

    def test_offline_partner_is_excluded(self):
        self.partners[1].is_online = False
        self.partners[1].save(update_fields=["is_online"])

        results = find_nearby_delivery_partners(self.vendor)
        partner_ids = [dp.id for dp, distance in results]

        self.assertEqual(len(results), 2)
        self.assertNotIn(self.partners[1].id, partner_ids)

    def test_unapproved_partner_is_excluded(self):
        self.partners[1].status = "pending_verification"
        self.partners[1].save(update_fields=["status"])

        results = find_nearby_delivery_partners(self.vendor)
        partner_ids = [dp.id for dp, distance in results]

        self.assertEqual(len(results), 2)
        self.assertNotIn(self.partners[1].id, partner_ids)

    def test_stale_gps_partner_is_excluded(self):
        from datetime import timedelta

        # Make the nearest partner's GPS location 10 minutes old.
        self.partners[1].location_updated_at = (
            timezone.now() - timedelta(minutes=10)
        )
        self.partners[1].save(
            update_fields=["location_updated_at"]
        )

        results = find_nearby_delivery_partners(self.vendor)
        partner_ids = [dp.id for dp, distance in results]

        self.assertEqual(len(results), 2)
        self.assertNotIn(self.partners[1].id, partner_ids)

    def test_busy_partner_is_excluded(self):
        from decimal import Decimal

        from django.contrib.auth import get_user_model
        from orders.models import Order

        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000399",
            full_name="Matching Test Buyer",
            user_type="buyer",
        )

        busy_partner = self.partners[1]

        Order.objects.create(
            order_number="UNI-GPS-BUSY-001",
            buyer=buyer,
            vendor=self.vendor,
            status="preparing",
            total_amount=Decimal("250.00"),
            delivery_address="Test Delivery Address",
            dp_status="accepted",
            delivery_partner=busy_partner.user,
        )

        results = find_nearby_delivery_partners(self.vendor)
        partner_ids = [dp.id for dp, distance in results]

        self.assertEqual(len(results), 2)
        self.assertNotIn(busy_partner.id, partner_ids)

    def test_partner_outside_radius_is_excluded(self):
        # Move the nearest partner roughly 10 km from the shop.
        self.partners[1].current_latitude = 17.5023
        self.partners[1].save(
            update_fields=["current_latitude"]
        )

        results = find_nearby_delivery_partners(self.vendor)
        partner_ids = [dp.id for dp, distance in results]

        self.assertEqual(len(results), 2)
        self.assertNotIn(self.partners[1].id, partner_ids)
