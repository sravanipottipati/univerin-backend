from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.dp_views import DPOrderAcceptView
from orders.models import DeliveryOffer, Order
from orders.dispatch_service import create_next_delivery_offer
from orders.test_delivery_offers import DeliveryOfferConstraintTests


class ExpiredAcceptanceRetryTests(TestCase):

    def setUp(self):
        DeliveryOfferConstraintTests.setUp(self)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000799",
            full_name="Expired Acceptance Buyer",
            user_type="buyer",
        )

        self.order = Order.objects.create(
            buyer=buyer,
            vendor=self.vendor,
            status="accepted",
            total_amount=250,
            delivery_address="Test Delivery Address",
        )

    def test_expired_acceptance_offers_next_partner(self):
        first_offer = create_next_delivery_offer(self.order.id)
        self.assertIsNotNone(first_offer)

        first_partner = first_offer.delivery_partner

        DeliveryOffer.objects.filter(
            pk=first_offer.pk
        ).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        request = APIRequestFactory().post(
            f"/dp/orders/{self.order.id}/accept/"
        )
        force_authenticate(request, user=first_partner)

        with self.captureOnCommitCallbacks(execute=True):
            response = DPOrderAcceptView.as_view()(
                request, order_id=self.order.id
            )

        self.assertEqual(response.status_code, 409)

        first_offer.refresh_from_db()
        self.assertEqual(first_offer.status, "expired")

        next_offer = DeliveryOffer.objects.get(
            order=self.order,
            status="pending",
        )

        self.assertNotEqual(
            next_offer.delivery_partner_id,
            first_partner.id,
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "offered")
