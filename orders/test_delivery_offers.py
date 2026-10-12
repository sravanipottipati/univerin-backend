from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from orders.models import DeliveryOffer
from delivery_partner.models import DeliveryPartner
from vendors.models import Vendor


class DeliveryOfferConstraintTests(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()

        seller = User.objects.create_user(
            phone_number="9000000301",
            full_name="Offer Test Seller",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=seller,
            shop_name="Offer Test Shop",
            category="grocery",
            phone_number="9000000301",
            address="Test Shop Address",
            town="Test Town",
            latitude=17.4123,
            longitude=78.4567,
        )

        self.partners = []

        for index, latitude in enumerate(
            [17.4323, 17.4173, 17.4223], start=2
        ):
            user = User.objects.create_user(
                phone_number=f"900000030{index}",
                full_name=f"Offer Test Partner {index}",
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

    def test_only_one_pending_offer_per_order(self):
        from django.contrib.auth import get_user_model
        from orders.models import Order

        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000499",
            full_name="Offer Test Buyer",
            user_type="buyer",
        )

        order = Order.objects.create(
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

        expires_at = timezone.now() + timedelta(seconds=30)

        DeliveryOffer.objects.create(
            order=order,
            delivery_partner=self.partners[0].user,
            expires_at=expires_at,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeliveryOffer.objects.create(
                    order=order,
                    delivery_partner=self.partners[1].user,
                    expires_at=expires_at,
                )

        self.assertEqual(
            DeliveryOffer.objects.filter(
                order=order,
                status="pending",
            ).count(),
            1,
        )

    def test_dispatch_offers_nearest_partner_first(self):
        from django.contrib.auth import get_user_model
        from orders.models import Order
        from orders.dispatch_service import create_next_delivery_offer

        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000599",
            full_name="Dispatch Test Buyer",
            user_type="buyer",
        )

        order = Order.objects.create(
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

        before_dispatch = timezone.now()
        offer = create_next_delivery_offer(order.id)

        self.assertIsNotNone(offer)

        # Partner at index 1 is closest to the shop.
        self.assertEqual(
            offer.delivery_partner_id,
            self.partners[1].user_id,
        )

        self.assertEqual(offer.status, "pending")

        offer_duration = (
            offer.expires_at - before_dispatch
        ).total_seconds()

        self.assertGreaterEqual(offer_duration, 30)
        self.assertLess(offer_duration, 35)

        order.refresh_from_db()

        self.assertEqual(order.dp_status, "offered")
        self.assertIsNone(order.delivery_partner_id)

        self.assertEqual(
            DeliveryOffer.objects.filter(
                order=order,
                status="pending",
            ).count(),
            1,
        )

    def test_repeated_dispatch_does_not_create_duplicate_offer(self):
        from django.contrib.auth import get_user_model
        from orders.models import Order
        from orders.dispatch_service import create_next_delivery_offer

        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000699",
            full_name="Duplicate Dispatch Test Buyer",
            user_type="buyer",
        )

        order = Order.objects.create(
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

        first_offer = create_next_delivery_offer(order.id)
        second_offer = create_next_delivery_offer(order.id)

        self.assertIsNotNone(first_offer)
        self.assertIsNone(second_offer)

        self.assertEqual(
            DeliveryOffer.objects.filter(order=order).count(),
            1,
        )

        order.refresh_from_db()
        self.assertEqual(order.dp_status, "offered")
        self.assertIsNone(order.delivery_partner_id)

    def test_expired_offer_is_marked_and_next_partner_is_offered(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone
        from orders.dispatch_service import (
            create_next_delivery_offer,
            expire_delivery_offer,
        )
        from orders.models import Order

        buyer = self._create_dispatch_buyer("9000000781")
        order = Order.objects.create(
            order_number="UNI-EXP-0701",
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

        first_offer = create_next_delivery_offer(order.id)
        self.assertIsNotNone(first_offer)

        first_offer.expires_at = timezone.now() - timedelta(seconds=1)
        first_offer.save(update_fields=["expires_at"])

        with patch(
            "orders.dispatch_service.create_next_delivery_offer",
            wraps=create_next_delivery_offer,
        ) as mock_dispatch:
            expired = expire_delivery_offer(first_offer.id)

        self.assertTrue(expired)

        first_offer.refresh_from_db()
        self.assertEqual(first_offer.status, "expired")
        self.assertIsNotNone(first_offer.responded_at)

        order.refresh_from_db()
        self.assertIsNone(order.delivery_partner_id)
        mock_dispatch.assert_called_once_with(order.id)

        self.assertEqual(
            order.delivery_offers.filter(status="pending").count(),
            1,
        )

    def test_offer_cannot_expire_before_deadline(self):
        from datetime import timedelta

        from django.utils import timezone
        from orders.dispatch_service import expire_delivery_offer
        from orders.models import Order, DeliveryOffer

        buyer = self._create_dispatch_buyer("9000000782")
        order = Order.objects.create(
            order_number="UNI-EXP-0702",
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
            dp_status="offered",
        )

        offer = DeliveryOffer.objects.create(
            order=order,
            delivery_partner=self.partners[1].user,
            expires_at=timezone.now() + timedelta(seconds=30),
        )

        self.assertFalse(expire_delivery_offer(offer.id))

        offer.refresh_from_db()
        self.assertEqual(offer.status, "pending")

    def _create_dispatch_buyer(self, phone_number):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(
            phone_number=phone_number,
            full_name="Expiration Test Buyer",
            user_type="buyer",
        )


class DeliveryOfferExpirationIntegrationTests(DeliveryOfferConstraintTests):

    def test_expiration_command_reassigns_to_next_partner(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from orders.models import Order
        from orders.dispatch_service import create_next_delivery_offer

        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000699",
            full_name="Expiration Test Buyer",
            user_type="buyer",
        )

        order = Order.objects.create(
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

        first_offer = create_next_delivery_offer(order.id)

        self.assertIsNotNone(first_offer)

        first_partner_id = first_offer.delivery_partner_id

        DeliveryOffer.objects.filter(
            pk=first_offer.pk
        ).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        call_command("expire_delivery_offers")

        first_offer.refresh_from_db()

        self.assertEqual(first_offer.status, "expired")

        next_offer = DeliveryOffer.objects.get(
            order=order,
            status="pending",
        )

        self.assertNotEqual(
            next_offer.delivery_partner_id,
            first_partner_id,
        )

        self.assertGreater(
            next_offer.expires_at,
            timezone.now(),
        )

        order.refresh_from_db()
        self.assertEqual(order.dp_status, "offered")
