from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.dp_views import DPOrderAcceptView
from orders.models import Order, DeliveryOffer
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner


class DeliveryPartnerConcurrencyTests(TransactionTestCase):

    def setUp(self):
        User = get_user_model()

        buyer = User.objects.create_user(
            phone_number="9000000101",
            full_name="Concurrency Test Buyer",
            user_type="buyer",
        )

        seller = User.objects.create_user(
            phone_number="9000000102",
            full_name="Concurrency Test Seller",
            user_type="vendor",
        )

        self.dp_a = User.objects.create_user(
            phone_number="9000000103",
            full_name="Concurrency Partner A",
            user_type="delivery_partner",
        )

        self.dp_b = User.objects.create_user(
            phone_number="9000000104",
            full_name="Concurrency Partner B",
            user_type="delivery_partner",
        )

        DeliveryPartner.objects.create(
            user=self.dp_a,
            status="approved",
            is_online=True,
        )
        DeliveryPartner.objects.create(
            user=self.dp_b,
            status="approved",
            is_online=True,
        )

        vendor = Vendor.objects.create(
            user=seller,
            shop_name="Concurrency Test Shop",
            category="grocery",
            phone_number="9000000102",
            address="Test Shop Address",
            town="Test Town",
        )

        self.order = Order.objects.create(
            order_number="UNI-TEST-002",
            buyer=buyer,
            vendor=vendor,
            status="preparing",
            total_amount=Decimal("250.00"),
            delivery_address="Test Delivery Address",
            dp_status="offered",
        )

        # Only Partner A has the active offer for this order.
        DeliveryOffer.objects.create(
            order=self.order,
            delivery_partner=self.dp_a,
            status="pending",
            expires_at=timezone.now() + timedelta(minutes=1),
        )

    def test_two_partners_accept_simultaneously(self):
        barrier = Barrier(2)

        def accept_order(user):
            close_old_connections()
            try:
                factory = APIRequestFactory()
                request = factory.post(
                    f"/dp/orders/{self.order.id}/accept/"
                )
                force_authenticate(request, user=user)

                barrier.wait(timeout=10)

                response = DPOrderAcceptView.as_view()(
                    request,
                    order_id=self.order.id,
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(accept_order, self.dp_a)
            future_b = executor.submit(accept_order, self.dp_b)

            results = [
                future_a.result(timeout=20),
                future_b.result(timeout=20),
            ]

        self.assertEqual(sorted(results), [200, 409])

        self.order.refresh_from_db()

        self.assertEqual(self.order.dp_status, "accepted")
        self.assertIn(
            self.order.delivery_partner_id,
            [self.dp_a.id, self.dp_b.id],
        )

    def test_same_partner_cannot_accept_two_orders_simultaneously(self):
        second_order = Order.objects.get(pk=self.order.pk)
        second_order.pk = None
        second_order.order_number = "UNI-TEST-003"
        second_order.delivery_partner = None
        second_order.dp_status = "offered"
        second_order.save()

        DeliveryOffer.objects.create(
            order=second_order,
            delivery_partner=self.dp_a,
            status="pending",
            expires_at=timezone.now() + timedelta(minutes=1),
        )

        order_ids = [self.order.id, second_order.id]
        barrier = Barrier(2)

        def accept_order(order_id):
            close_old_connections()
            try:
                factory = APIRequestFactory()
                request = factory.post(
                    f"/dp/orders/{order_id}/accept/"
                )
                force_authenticate(request, user=self.dp_a)

                barrier.wait(timeout=10)

                response = DPOrderAcceptView.as_view()(
                    request,
                    order_id=order_id,
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(accept_order, order_id)
                for order_id in order_ids
            ]
            results = [
                future.result(timeout=20)
                for future in futures
            ]

        self.assertEqual(sorted(results), [200, 409])

        assigned_orders = Order.objects.filter(
            id__in=order_ids,
            delivery_partner=self.dp_a,
            dp_status="accepted",
        )

        self.assertEqual(assigned_orders.count(), 1)
