from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.dp_views import DPAvailableOrdersView
from orders.models import DeliveryOffer

from orders.test_dp_acceptance import DeliveryPartnerAcceptanceTests


class DeliveryPartnerAvailableOfferTests(TestCase):

    def setUp(self):
        DeliveryPartnerAcceptanceTests.setUp(self)
        self.factory = APIRequestFactory()

    def available_orders(self, user):
        request = self.factory.get("/dp/orders/available/")
        force_authenticate(request, user=user)
        return DPAvailableOrdersView.as_view()(request)

    def test_only_target_partner_sees_offer(self):
        DeliveryOffer.objects.create(
            order=self.order,
            delivery_partner=self.dp_a,
            status="pending",
            expires_at=timezone.now() + timedelta(seconds=30),
        )

        self.order.dp_status = "offered"
        self.order.save(update_fields=["dp_status", "updated_at"])

        response_a = self.available_orders(self.dp_a)
        response_b = self.available_orders(self.dp_b)

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)

        self.assertEqual(len(response_a.data), 1)
        self.assertEqual(len(response_b.data), 0)

        self.assertEqual(
            response_a.data[0]["id"],
            str(self.order.id),
        )

    def test_expired_offer_is_hidden(self):
        DeliveryOffer.objects.create(
            order=self.order,
            delivery_partner=self.dp_a,
            status="pending",
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.order.dp_status = "offered"
        self.order.save(update_fields=["dp_status", "updated_at"])

        response = self.available_orders(self.dp_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)
