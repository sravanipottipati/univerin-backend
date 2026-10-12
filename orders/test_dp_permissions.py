from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from orders.dp_views import DPOrderAcceptView
import uuid


class DeliveryPartnerPermissionTests(SimpleTestCase):

    def test_buyer_cannot_accept_delivery(self):
        User = get_user_model()

        buyer = User(
            phone_number="9000000001",
            full_name="Test Buyer",
            user_type="buyer",
        )

        request = APIRequestFactory().post(
            f"/dp/orders/{uuid.uuid4()}/accept/"
        )
        force_authenticate(request, user=buyer)

        response = DPOrderAcceptView.as_view()(
            request,
            order_id=uuid.uuid4(),
        )

        self.assertEqual(response.status_code, 403)
