from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from delivery_partner.models import DeliveryPartner
from delivery_partner.views import DPLocationUpdateView


class DPLocationValidationTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            phone_number="9000000201",
            full_name="GPS Test Partner",
            user_type="delivery_partner",
        )

        self.dp = DeliveryPartner.objects.create(
            user=self.user,
            status="approved",
            is_online=True,
        )

        self.factory = APIRequestFactory()

    def update_location(self, latitude, longitude):
        request = self.factory.post(
            "/dp/location/update/",
            {
                "latitude": latitude,
                "longitude": longitude,
            },
            format="json",
        )

        force_authenticate(request, user=self.user)
        return DPLocationUpdateView.as_view()(request)

    def test_valid_coordinates_are_saved(self):
        response = self.update_location(17.4123, 78.4567)

        self.assertEqual(response.status_code, 200)

        self.dp.refresh_from_db()
        self.assertAlmostEqual(self.dp.current_latitude, 17.4123)
        self.assertAlmostEqual(self.dp.current_longitude, 78.4567)
        self.assertIsNotNone(self.dp.location_updated_at)

    def test_invalid_latitude_is_rejected(self):
        response = self.update_location(200, 78.4567)

        self.assertEqual(response.status_code, 400)

        self.dp.refresh_from_db()
        self.assertIsNone(self.dp.current_latitude)

    def test_invalid_longitude_is_rejected(self):
        response = self.update_location(17.4123, -250)

        self.assertEqual(response.status_code, 400)

    def test_non_numeric_coordinates_are_rejected(self):
        response = self.update_location("invalid", 78.4567)

        self.assertEqual(response.status_code, 400)

    def test_invalid_update_preserves_previous_location(self):
        first_response = self.update_location(17.4123, 78.4567)
        self.assertEqual(first_response.status_code, 200)

        second_response = self.update_location(200, 78.4567)
        self.assertEqual(second_response.status_code, 400)

        self.dp.refresh_from_db()
        self.assertAlmostEqual(self.dp.current_latitude, 17.4123)
        self.assertAlmostEqual(self.dp.current_longitude, 78.4567)
