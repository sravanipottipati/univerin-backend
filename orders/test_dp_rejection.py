from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.models import Order, DeliveryOffer
from orders.dp_views import DPOrderRejectView
from orders.dispatch_service import create_next_delivery_offer

from delivery_partner.test_matching import NearbyDeliveryPartnerMatchingTests


class DeliveryPartnerRejectionTests(TestCase):

    def setUp(self):
        # Reuse the existing GPS-matching test fixtures.
        NearbyDeliveryPartnerMatchingTests.setUp(self)
        self.factory = APIRequestFactory()

        from django.contrib.auth import get_user_model
        User = get_user_model()

        self.buyer = User.objects.create_user(
            phone_number="9000000881",
            full_name="Rejection Test Buyer",
            user_type="buyer",
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

    def test_rejection_offers_order_to_next_partner(self):
        first_offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(first_offer)

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/reject/"
        )
        force_authenticate(
            request,
            user=first_offer.delivery_partner,
        )

        response = DPOrderRejectView.as_view()(
            request,
            order_id=self.order.id,
        )

        self.assertEqual(response.status_code, 200)

        first_offer.refresh_from_db()
        self.assertEqual(first_offer.status, "rejected")
        self.assertIsNotNone(first_offer.responded_at)

        next_offer = DeliveryOffer.objects.get(
            order=self.order,
            status="pending",
        )

        self.assertNotEqual(
            next_offer.delivery_partner_id,
            first_offer.delivery_partner_id,
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "offered")
        self.assertIsNone(self.order.delivery_partner_id)

    def test_other_partner_cannot_reject_offer(self):
        first_offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(first_offer)

        # Find a different registered delivery partner.
        from delivery_partner.models import DeliveryPartner

        other_dp = (
            DeliveryPartner.objects
            .exclude(user_id=first_offer.delivery_partner_id)
            .filter(status="approved", is_online=True)
            .first()
        )
        self.assertIsNotNone(other_dp)

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/reject/"
        )
        force_authenticate(request, user=other_dp.user)

        response = DPOrderRejectView.as_view()(
            request,
            order_id=self.order.id,
        )

        self.assertEqual(response.status_code, 409)

        first_offer.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(first_offer.status, "pending")
        self.assertEqual(self.order.dp_status, "offered")
        self.assertIsNone(self.order.delivery_partner_id)

        self.assertEqual(
            DeliveryOffer.objects.filter(
                order=self.order,
                status="pending",
            ).count(),
            1,
        )

    def test_repeated_rejection_does_not_create_duplicate_offers(self):
        first_offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(first_offer)

        def reject():
            request = self.factory.post(
                f"/dp/orders/{self.order.id}/reject/"
            )
            force_authenticate(
                request,
                user=first_offer.delivery_partner,
            )
            return DPOrderRejectView.as_view()(
                request,
                order_id=self.order.id,
            )

        # First rejection succeeds.
        first_response = reject()
        self.assertEqual(first_response.status_code, 200)

        # The same partner cannot reject the same offer twice.
        second_response = reject()
        self.assertEqual(second_response.status_code, 409)

        first_offer.refresh_from_db()
        self.assertEqual(first_offer.status, "rejected")

        # Only one replacement offer should exist.
        self.assertEqual(
            DeliveryOffer.objects.filter(
                order=self.order,
                status="pending",
            ).count(),
            1,
        )

        # Exactly two offers: original + replacement.
        self.assertEqual(
            DeliveryOffer.objects.filter(
                order=self.order,
            ).count(),
            2,
        )

    def test_expired_offer_rejection_triggers_next_partner(self):
        from datetime import timedelta

        first_offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(first_offer)

        # Simulate the 30-second deadline having passed.
        first_offer.expires_at = timezone.now() - timedelta(seconds=1)
        first_offer.save(update_fields=["expires_at"])

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/reject/"
        )
        force_authenticate(
            request,
            user=first_offer.delivery_partner,
        )

        response = DPOrderRejectView.as_view()(
            request,
            order_id=self.order.id,
        )

        # An expired offer cannot be rejected successfully.
        self.assertEqual(response.status_code, 409)

        first_offer.refresh_from_db()
        self.assertEqual(first_offer.status, "expired")
        self.assertIsNotNone(first_offer.responded_at)

        # The next eligible partner should receive a pending offer.
        next_offer = DeliveryOffer.objects.get(
            order=self.order,
            status="pending",
        )

        self.assertNotEqual(
            next_offer.delivery_partner_id,
            first_offer.delivery_partner_id,
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "offered")
        self.assertIsNone(self.order.delivery_partner_id)

    def test_cannot_reject_already_assigned_order(self):
        offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(offer)

        # Simulate an order assigned while an old offer remains pending.
        self.order.delivery_partner = offer.delivery_partner
        self.order.dp_status = "accepted"
        self.order.save(update_fields=["delivery_partner", "dp_status"])

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/reject/"
        )
        force_authenticate(request, user=offer.delivery_partner)

        response = DPOrderRejectView.as_view()(
            request, order_id=self.order.id
        )

        self.assertEqual(response.status_code, 409)

        offer.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(offer.status, "pending")
        self.assertEqual(self.order.dp_status, "accepted")
        self.assertEqual(
            self.order.delivery_partner_id,
            offer.delivery_partner_id,
        )
        self.assertEqual(
            DeliveryOffer.objects.filter(order=self.order).count(),
            1,
        )

    def test_cannot_reject_cancelled_order(self):
        offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(offer)

        self.order.status = "cancelled"
        self.order.save(update_fields=["status"])

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/reject/"
        )
        force_authenticate(request, user=offer.delivery_partner)

        response = DPOrderRejectView.as_view()(
            request, order_id=self.order.id
        )

        self.assertEqual(response.status_code, 409)

        offer.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(offer.status, "pending")
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.dp_status, "offered")
        self.assertEqual(
            DeliveryOffer.objects.filter(order=self.order).count(),
            1,
        )
