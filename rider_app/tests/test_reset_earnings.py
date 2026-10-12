import io
from datetime import datetime
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from rider_app.management.commands import reset_earnings as reset_module
from rider_app.models import OrderAssignment, RiderEarning

from .test_assignment_flow import make_order, make_rider, make_user


FIXED_NOW = timezone.make_aware(datetime(2026, 3, 15, 12, 0))
YESTERDAY = datetime(2026, 3, 14).date()
SECONDS_TO_MIDNIGHT = 43200.0


class StopLoop(Exception):
    pass


class ResetEarningsCommandTests(TestCase):
    def start_scheduler(self):
        captured = {}

        def fake_thread(target=None, daemon=None, **kwargs):
            captured['target'] = target
            captured['daemon'] = daemon
            return mock.MagicMock()

        output = io.StringIO()
        with mock.patch.object(
            reset_module, 'Thread', side_effect=fake_thread
        ):
            call_command('reset_earnings', stdout=output)
        captured['stdout'] = output.getvalue()
        return captured

    def run_scheduler(self, captured):
        with mock.patch.object(reset_module, 'time') as time_mock, \
                mock.patch.object(
                    reset_module.timezone,
                    'localtime',
                    return_value=FIXED_NOW,
                ):
            time_mock.sleep.side_effect = [
                None,
                StopLoop('reset done'),
                StopLoop('retry'),
            ]
            with self.assertRaises(StopLoop):
                captured['target']()
        return time_mock

    def test_command_starts_scheduler_thread_and_reports_success(self):
        captured = self.start_scheduler()

        self.assertIn(
            'Started earnings reset scheduler', captured['stdout']
        )
        self.assertTrue(callable(captured['target']))
        self.assertIs(captured['daemon'], True)

    def test_scheduler_sleeps_until_midnight_then_retries_after_error(self):
        captured = self.start_scheduler()
        time_mock = self.run_scheduler(captured)

        self.assertEqual(
            time_mock.sleep.call_args_list,
            [
                mock.call(SECONDS_TO_MIDNIGHT),
                mock.call(SECONDS_TO_MIDNIGHT),
                mock.call(60),
            ],
        )

    def test_positive_earnings_are_recorded_zeroed_and_balanced(self):
        rider = make_rider(
            'reset_rich',
            today_earnings=Decimal('40.00'),
            current_balance=Decimal('100.00'),
        )
        captured = self.start_scheduler()
        self.run_scheduler(captured)

        rider.refresh_from_db()
        self.assertEqual(rider.today_earnings, Decimal('0.00'))
        self.assertEqual(rider.current_balance, Decimal('140.00'))

        earning = RiderEarning.objects.get(rider=rider)
        self.assertEqual(earning.date, YESTERDAY)
        self.assertEqual(earning.total_earnings, Decimal('40.00'))
        self.assertEqual(earning.orders_completed, 0)
        self.assertEqual(earning.distance_km, Decimal('0.00'))
        self.assertEqual(earning.distance_earning, Decimal('0.00'))
        self.assertEqual(earning.commission_earning, Decimal('0.00'))

    def test_riders_without_earnings_are_skipped(self):
        rich = make_rider('reset_ok', today_earnings=Decimal('25.00'))
        empty = make_rider('reset_empty')

        captured = self.start_scheduler()
        self.run_scheduler(captured)

        self.assertEqual(
            RiderEarning.objects.filter(rider=rich).count(), 1
        )
        self.assertEqual(
            RiderEarning.objects.filter(rider=empty).count(), 0
        )
        empty.refresh_from_db()
        self.assertEqual(empty.today_earnings, Decimal('0.00'))
        self.assertEqual(empty.current_balance, Decimal('0.00'))

    def test_recorded_row_uses_completed_delivery_count(self):
        rider = make_rider('reset_deliveries', today_earnings=Decimal('60.00'))
        for index in range(2):
            order = make_order(make_user(f'reset_cust_{index}'))
            OrderAssignment.objects.create(
                order=order, rider=rider, status='delivered'
            )

        captured = self.start_scheduler()
        self.run_scheduler(captured)

        earning = RiderEarning.objects.get(rider=rider)
        self.assertEqual(earning.orders_completed, 2)
        self.assertEqual(earning.total_earnings, Decimal('60.00'))
