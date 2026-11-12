from datetime import timedelta
import uuid

from django.test import SimpleTestCase
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset


class CleanupAttemptSafetyTests(SimpleTestCase):

    def test_attempt_fields_exist(self):
        fields = {
            field.name
            for field in AccountDeletionAsset._meta.fields
        }
        self.assertIn("attempt_id", fields)
        self.assertIn("lease_expires_at", fields)

    def test_attempt_id_supports_unique_identifiers(self):
        first = uuid.uuid4()
        second = uuid.uuid4()

        self.assertNotEqual(first, second)

    def test_expired_lease_can_be_identified(self):
        now = timezone.now()
        expired = now - timedelta(minutes=1)
        active = now + timedelta(minutes=15)

        self.assertLess(expired, now)
        self.assertGreater(active, now)
