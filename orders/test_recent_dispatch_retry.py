from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from orders.dispatch_service import retry_recent_unassigned_orders
from orders.models import Order


class RecentDispatchRetryTests(TestCase):

    @patch("orders.dispatch_service.create_next_delivery_offer")
    @patch("orders.dispatch_service.Order.objects.filter")
    def test_retry_filters_eligible_orders(self, mock_filter, mock_dispatch):
        mock_filter.return_value.order_by.return_value.values_list.return_value = []
        mock_dispatch.return_value = None

        result = retry_recent_unassigned_orders()

        self.assertEqual(result, 0)
        mock_dispatch.assert_not_called()

        filters = mock_filter.call_args.kwargs

        self.assertEqual(
            filters["status__in"],
            ["accepted", "preparing"],
        )
        self.assertEqual(filters["dp_status"], "unassigned")
        self.assertTrue(filters["delivery_partner__isnull"])

        cutoff = filters["created_at__gte"]
        self.assertLess(
            abs((timezone.now() - cutoff) - timedelta(minutes=30)),
            timedelta(seconds=5),
        )

    @patch("orders.dispatch_service.create_next_delivery_offer")
    @patch("orders.dispatch_service.Order.objects.filter")
    def test_retry_calls_existing_dispatch(self, mock_filter, mock_dispatch):
        mock_filter.return_value.order_by.return_value.values_list.return_value = [
            "test-order-1",
            "test-order-2",
        ]

        mock_dispatch.side_effect = [object(), None]

        result = retry_recent_unassigned_orders()

        self.assertEqual(result, 1)
        self.assertEqual(mock_dispatch.call_count, 2)
