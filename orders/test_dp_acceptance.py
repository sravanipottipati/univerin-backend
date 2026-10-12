from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.models import Order, DeliveryOffer
from orders.dp_views import DPOrderAcceptView
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner


class DeliveryPartnerAcceptanceTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.buyer = User.objects.create_user(
            phone_number="9000000001",
            full_name="Test Buyer",
            user_type="buyer",
        )

        seller = User.objects.create_user(
            phone_number="9000000002",
            full_name="Test Seller",
            user_type="vendor",
        )

        self.dp_a = User.objects.create_user(
            phone_number="9000000003",
            full_name="Delivery Partner A",
            user_type="delivery_partner",
        )

        self.dp_b = User.objects.create_user(
            phone_number="9000000004",
            full_name="Delivery Partner B",
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

        self.vendor = Vendor.objects.create(
            user=seller,
            shop_name="Test Shop",
            category="grocery",
            phone_number="9000000002",
            address="Test Shop Address",
            town="Test Town",
        )

        self.order = Order.objects.create(
            order_number="UNI-TEST-001",
            buyer=self.buyer,
            vendor=self.vendor,
            status="preparing",
            total_amount=Decimal("250.00"),
            delivery_address="Test Delivery Address",
            dp_status="unassigned",
        )

        self.factory = APIRequestFactory()

    def accept_order(self, user):
        self.order.refresh_from_db()

        # Create an offer only when this order has no pending offer.
        # The database allows only one pending offer per order.
        if (
            self.order.delivery_partner_id is None
            and self.order.dp_status in ["unassigned", "offered"]
            and not DeliveryOffer.objects.filter(
                order=self.order,
                status="pending",
            ).exists()
        ):
            DeliveryOffer.objects.create(
                order=self.order,
                delivery_partner=user,
                status="pending",
                expires_at=timezone.now() + timedelta(minutes=1),
            )
            self.order.dp_status = "offered"
            self.order.save(update_fields=["dp_status", "updated_at"])

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/accept/"
        )
        force_authenticate(request, user=user)

        return DPOrderAcceptView.as_view()(
            request,
            order_id=self.order.id,
        )

    def test_second_partner_cannot_accept_taken_order(self):
        response_a = self.accept_order(self.dp_a)
        self.assertEqual(response_a.status_code, 200)

        response_b = self.accept_order(self.dp_b)
        self.assertEqual(response_b.status_code, 409)

        self.order.refresh_from_db()

        self.assertEqual(
            self.order.delivery_partner_id,
            self.dp_a.id,
        )
        self.assertEqual(self.order.dp_status, "accepted")

    def test_offline_partner_cannot_accept(self):
        profile = self.dp_a.delivery_partner
        profile.is_online = False
        profile.save(update_fields=["is_online"])

        response = self.accept_order(self.dp_a)
        self.assertEqual(response.status_code, 403)

    def test_pending_partner_cannot_accept(self):
        profile = self.dp_a.delivery_partner
        profile.status = "pending_verification"
        profile.save(update_fields=["status"])

        response = self.accept_order(self.dp_a)
        self.assertEqual(response.status_code, 403)

    def test_rejected_partner_cannot_accept(self):
        profile = self.dp_a.delivery_partner
        profile.status = "rejected"
        profile.save(update_fields=["status"])

        response = self.accept_order(self.dp_a)
        self.assertEqual(response.status_code, 403)

    def test_partner_without_profile_cannot_accept(self):
        self.dp_a.delivery_partner.delete()

        response = self.accept_order(self.dp_a)
        self.assertEqual(response.status_code, 400)

    def test_expired_offer_cannot_be_accepted(self):
        offer = DeliveryOffer.objects.create(
            order=self.order,
            delivery_partner=self.dp_a,
            status="pending",
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.order.dp_status = "offered"
        self.order.save(update_fields=["dp_status", "updated_at"])

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/accept/"
        )
        force_authenticate(request, user=self.dp_a)

        response = DPOrderAcceptView.as_view()(
            request,
            order_id=self.order.id,
        )

        self.assertEqual(response.status_code, 409)

        offer.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(offer.status, "expired")
        self.assertIsNotNone(offer.responded_at)
        self.assertIsNone(self.order.delivery_partner_id)
        self.assertEqual(self.order.dp_status, "unassigned")

    def test_partner_cannot_accept_another_partners_offer(self):
        offer = DeliveryOffer.objects.create(
            order=self.order,
            delivery_partner=self.dp_a,
            status="pending",
            expires_at=timezone.now() + timedelta(minutes=1),
        )
        self.order.dp_status = "offered"
        self.order.save(update_fields=["dp_status", "updated_at"])

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/accept/"
        )
        force_authenticate(request, user=self.dp_b)

        response = DPOrderAcceptView.as_view()(
            request,
            order_id=self.order.id,
        )

        self.assertEqual(response.status_code, 409)

        offer.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(offer.status, "pending")
        self.assertIsNone(self.order.delivery_partner_id)
        self.assertEqual(self.order.dp_status, "offered")


class OneActiveDeliveryTests(DeliveryPartnerAcceptanceTests):
    def test_partner_cannot_accept_second_active_order(self):
        from orders.models import Order

        second_order = Order.objects.get(pk=self.order.pk)
        second_order.pk = None
        second_order.order_number = "UNI-TEST-SECOND"
        second_order.delivery_partner = None
        second_order.dp_status = "unassigned"
        second_order.save()

        first_response = self.accept_order(self.dp_a)
        self.order = second_order
        second_response = self.accept_order(self.dp_a)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)

        second_order.refresh_from_db()
        self.assertIsNone(second_order.delivery_partner)
        self.assertEqual(second_order.dp_status, "offered")
        self.assertTrue(
            second_order.delivery_offers.filter(
                status="pending",
                delivery_partner=self.dp_a,
            ).exists()
        )

    def test_partner_can_accept_after_delivery_completed(self):
        from orders.models import Order

        second_order = Order.objects.get(pk=self.order.pk)
        second_order.pk = None
        second_order.order_number = "UNI-TEST-COMPLETED"
        second_order.delivery_partner = None
        second_order.dp_status = "unassigned"
        second_order.save()

        first_response = self.accept_order(self.dp_a)
        self.assertEqual(first_response.status_code, 200)

        self.order.refresh_from_db()
        self.order.dp_status = "delivered"
        self.order.status = "delivered"
        self.order.save(update_fields=["dp_status", "status"])

        self.order = second_order
        second_response = self.accept_order(self.dp_a)

        self.assertEqual(second_response.status_code, 200)

        second_order.refresh_from_db()
        self.assertEqual(second_order.delivery_partner, self.dp_a)
        self.assertEqual(second_order.dp_status, "accepted")
