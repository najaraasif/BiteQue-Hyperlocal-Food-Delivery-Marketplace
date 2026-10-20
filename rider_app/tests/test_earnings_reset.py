"""Tests for the hardened daily earnings reset.

The reset moves the money a rider earned during a business day from the
running accumulator into the running balance. These tests pin down the
financial rules:

* a rider is credited exactly once per business day;
* a business day can only be closed once;
* a failed run leaves nothing behind and can be repeated;
* a missed run is caught up, without crediting more than the accumulator;
* the ledger keeps one row per rider per business day, so a day's earnings
  are not counted twice;
* the database lock is used when the backend supports it, and the weaker
  guarantee is stated when it does not.
"""
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, connection
from django.test import TestCase
from django.utils import timezone

from rider_app import earnings
from rider_app.earnings import (
    business_date,
    close_business_date,
    due_business_dates,
    next_business_date_to_close,
)
from rider_app.models import EarningsResetRun, OrderAssignment, RiderEarning

from .test_assignment_flow import make_order, make_rider, make_user

# 00:05 IST on the 15th: the moment the scheduled run fires.
RUN_MOMENT = timezone.make_aware(datetime(2026, 3, 15, 0, 5))
YESTERDAY = date(2026, 3, 14)
TODAY = date(2026, 3, 15)


@contextmanager
def frozen_now(moment=RUN_MOMENT):
    with mock.patch('django.utils.timezone.now', return_value=moment):
        yield


class BusinessDateTests(TestCase):
    def test_business_date_uses_local_time_not_utc(self):
        # 00:30 IST on the 15th is still the 14th in UTC. The business day
        # must be the local one, otherwise evening deliveries are filed
        # under the wrong day and the reset cannot find the day's row.
        moment = timezone.make_aware(datetime(2026, 3, 15, 0, 30))
        with mock.patch('django.utils.timezone.now', return_value=moment):
            self.assertEqual(business_date(), date(2026, 3, 15))

    def test_business_date_before_local_midnight(self):
        moment = timezone.make_aware(datetime(2026, 3, 14, 23, 59))
        with mock.patch('django.utils.timezone.now', return_value=moment):
            self.assertEqual(business_date(), date(2026, 3, 14))

    def test_business_date_is_the_local_day_of_a_given_moment(self):
        moment = timezone.make_aware(datetime(2026, 3, 16, 9, 0))
        self.assertEqual(business_date(moment), date(2026, 3, 16))


class ResetCreditTests(TestCase):
    def test_credit_moves_the_accumulator_into_the_balance(self):
        rider = make_rider('credit_rider', today_earnings=Decimal('40.00'),
                           current_balance=Decimal('100.00'))

        with frozen_now():
            summary = close_business_date(YESTERDAY)

        rider.refresh_from_db()
        self.assertEqual(summary['status'], 'closed')
        self.assertEqual(summary['business_date'], YESTERDAY)
        self.assertEqual(summary['riders_processed'], 1)
        self.assertEqual(summary['total_credited'], Decimal('40.00'))
        self.assertEqual(rider.current_balance, Decimal('140.00'))
        self.assertEqual(rider.today_earnings, Decimal('0.00'))

    def test_rider_without_earnings_is_skipped(self):
        rider = make_rider('no_earnings_rider')

        with frozen_now():
            summary = close_business_date(YESTERDAY)

        rider.refresh_from_db()
        self.assertEqual(summary['riders_processed'], 0)
        self.assertEqual(summary['total_credited'], Decimal('0.00'))
        self.assertEqual(rider.current_balance, Decimal('0.00'))
        self.assertEqual(rider.today_earnings, Decimal('0.00'))
        self.assertEqual(RiderEarning.objects.count(), 0)

    def test_ledger_row_keeps_the_completed_delivery_count(self):
        rider = make_rider('deliveries_rider', today_earnings=Decimal('60.00'))
        order = make_order(make_user('deliveries_customer'))
        OrderAssignment.objects.create(
            order=order, rider=rider, status='delivered'
        )

        with frozen_now():
            close_business_date(YESTERDAY)

        earning = RiderEarning.objects.get(rider=rider, date=YESTERDAY)
        self.assertEqual(earning.total_earnings, Decimal('60.00'))
        self.assertEqual(earning.orders_completed, 1)

    def test_run_ledger_records_the_business_date_and_totals(self):
        make_rider('run_rider', today_earnings=Decimal('15.00'))

        with frozen_now():
            close_business_date(YESTERDAY, source='cron')

        run = EarningsResetRun.objects.get(business_date=YESTERDAY)
        self.assertEqual(run.riders_processed, 1)
        self.assertEqual(run.total_credited, Decimal('15.00'))
        self.assertEqual(run.source, 'cron')
        self.assertIsNotNone(run.completed_at)

    def test_a_day_already_in_the_ledger_is_not_credited_twice(self):
        # The delivery path already recorded the day. The reset must reuse
        # that row instead of adding a second one, otherwise the day's
        # earnings are counted twice by Rider.get_total_earnings().
        rider = make_rider('ledger_rider', today_earnings=Decimal('40.00'))
        RiderEarning.objects.create(
            rider=rider,
            date=YESTERDAY,
            total_earnings=Decimal('40.00'),
            orders_completed=1,
        )

        with frozen_now():
            summary = close_business_date(YESTERDAY)

        rows = RiderEarning.objects.filter(rider=rider)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(summary['ledger_rows_created'], 0)
        rider.refresh_from_db()
        self.assertEqual(rider.get_total_earnings(), Decimal('40.00'))
        self.assertEqual(rider.get_current_balance(), Decimal('40.00'))
        self.assertEqual(rider.current_balance, Decimal('40.00'))

    def test_ledger_row_is_created_when_the_day_has_none(self):
        rider = make_rider('no_ledger_rider', today_earnings=Decimal('12.00'))

        with frozen_now():
            summary = close_business_date(YESTERDAY)

        self.assertEqual(summary['ledger_rows_created'], 1)
        self.assertEqual(
            RiderEarning.objects.filter(rider=rider, date=YESTERDAY).count(), 1
        )


class IdempotencyTests(TestCase):
    def test_second_run_for_the_same_business_date_credits_nothing(self):
        rider = make_rider('idem_rider', today_earnings=Decimal('25.00'))

        with frozen_now():
            first = close_business_date(YESTERDAY)
            second = close_business_date(YESTERDAY)

        rider.refresh_from_db()
        self.assertEqual(first['status'], 'closed')
        self.assertEqual(second['status'], 'already_closed')
        self.assertEqual(rider.current_balance, Decimal('25.00'))
        self.assertEqual(rider.today_earnings, Decimal('0.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 1)

    def test_repeated_runs_never_double_credit(self):
        rider = make_rider('repeat_rider', today_earnings=Decimal('30.00'))

        with frozen_now():
            for _ in range(3):
                close_business_date(YESTERDAY)

        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('30.00'))
        self.assertEqual(RiderEarning.objects.filter(rider=rider).count(), 1)

    def test_unique_constraint_rejects_a_second_run_row(self):
        EarningsResetRun.objects.create(business_date=YESTERDAY)

        with self.assertRaises(IntegrityError):
            EarningsResetRun.objects.create(business_date=YESTERDAY)

    def test_unique_constraint_rejects_two_daily_earning_rows(self):
        rider = make_rider('dup_rider')
        RiderEarning.objects.create(
            rider=rider, date=YESTERDAY, total_earnings=Decimal('1.00'),
            orders_completed=1,
        )

        with self.assertRaises(IntegrityError):
            RiderEarning.objects.create(
                rider=rider, date=YESTERDAY, total_earnings=Decimal('2.00'),
                orders_completed=1,
            )


class LockingTests(TestCase):
    def test_busy_lock_skips_the_reset(self):
        rider = make_rider('busy_rider', today_earnings=Decimal('50.00'))

        with mock.patch.dict(
            earnings.reset_lock.__globals__, {'__name__': 'x'}
        ):  # keep the patch target simple and explicit
            with mock.patch.object(
                earnings, 'reset_lock'
            ) as lock:
                lock.return_value.__enter__.return_value = {
                    'state': 'busy',
                    'detail': 'another reset already holds the advisory lock',
                }
                lock.return_value.__exit__.return_value = False
                summary = close_business_date(YESTERDAY)

        rider.refresh_from_db()
        self.assertEqual(summary['status'], 'locked')
        self.assertEqual(rider.current_balance, Decimal('0.00'))
        self.assertEqual(rider.today_earnings, Decimal('50.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 0)

    def test_sqlite_states_that_advisory_locks_are_unavailable(self):
        if connection.vendor == 'postgresql':
            self.skipTest('PostgreSQL provides advisory locks')

        make_rider('sqlite_rider', today_earnings=Decimal('5.00'))

        with self.assertLogs('rider_app.earnings', level='WARNING') as logs:
            with frozen_now():
                summary = close_business_date(YESTERDAY)

        self.assertEqual(summary.get('lock'), 'unavailable')
        self.assertTrue(
            any('advisory locks are not available' in line for line in logs.output)
        )

    def test_reset_lock_reports_the_backend_it_used(self):
        with earnings.reset_lock() as lock:
            if connection.vendor == 'postgresql':
                self.assertEqual(lock['state'], 'locked')
            else:
                self.assertEqual(lock['state'], 'unavailable')
                self.assertIn('advisory locks are not available', lock['detail'])


class FailureHandlingTests(TestCase):
    def test_failure_mid_reset_rolls_everything_back(self):
        good = make_rider('rollback_ok', today_earnings=Decimal('10.00'))
        bad = make_rider('rollback_bad', today_earnings=Decimal('20.00'))

        original = earnings._ensure_daily_ledger_row
        calls = {'n': 0}

        def exploding(rider, day, amount):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('boom')
            return original(rider, day, amount)

        with mock.patch.object(earnings, '_ensure_daily_ledger_row', exploding):
            with self.assertRaises(RuntimeError):
                close_business_date(YESTERDAY)

        good.refresh_from_db()
        bad.refresh_from_db()
        self.assertEqual(good.current_balance, Decimal('0.00'))
        self.assertEqual(good.today_earnings, Decimal('10.00'))
        self.assertEqual(bad.current_balance, Decimal('0.00'))
        self.assertEqual(bad.today_earnings, Decimal('20.00'))
        self.assertEqual(RiderEarning.objects.count(), 0)
        self.assertEqual(EarningsResetRun.objects.count(), 0)

    def test_a_failed_day_can_be_retried(self):
        rider = make_rider('retry_rider', today_earnings=Decimal('20.00'))

        with mock.patch.object(
            earnings, '_ensure_daily_ledger_row',
            side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                close_business_date(YESTERDAY)

        with frozen_now():
            summary = close_business_date(YESTERDAY)

        rider.refresh_from_db()
        self.assertEqual(summary['status'], 'closed')
        self.assertEqual(rider.current_balance, Decimal('20.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 1)


class CatchUpTests(TestCase):
    def test_nothing_is_due_on_a_day_that_was_just_closed(self):
        with frozen_now():
            close_business_date(YESTERDAY)

        with frozen_now():
            self.assertEqual(due_business_dates(), [])

    def test_due_dates_start_after_the_last_closed_date(self):
        EarningsResetRun.objects.create(business_date=YESTERDAY)

        with frozen_now():
            due = due_business_dates()

        self.assertEqual(due, [])

    def test_a_missed_run_is_caught_up_by_the_next_run(self):
        rider = make_rider('catchup_rider', today_earnings=Decimal('18.00'))

        with frozen_now():
            summary = close_business_date(next_business_date_to_close())

        rider.refresh_from_db()
        self.assertEqual(summary['business_date'], YESTERDAY)
        self.assertEqual(rider.current_balance, Decimal('18.00'))
        self.assertEqual(rider.today_earnings, Decimal('0.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 1)

    def test_catch_up_never_credits_more_than_the_accumulator(self):
        rider = make_rider('catchup_amount_rider', today_earnings=Decimal('18.00'))

        with frozen_now():
            close_business_date(YESTERDAY)
            close_business_date(YESTERDAY)  # a retry must not credit again

        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('18.00'))

    def test_overdue_days_are_reported_and_only_the_oldest_is_closed(self):
        make_rider('overdue_rider', today_earnings=Decimal('7.00'))
        # Nothing was ever closed, so several days are outstanding.
        EarningsResetRun.objects.create(business_date=date(2026, 3, 10))

        with frozen_now():
            due = due_business_dates()

        self.assertEqual(due[0], date(2026, 3, 11))
        self.assertEqual(len(due), 4)


class CommandTests(TestCase):
    def run_command(self, *args, **kwargs):
        from django.core.management import call_command

        out = mock.MagicMock()
        with frozen_now():
            call_command('reset_earnings', *args, stdout=out, **kwargs)
        return out

    def test_once_closes_the_due_business_date(self):
        rider = make_rider('cmd_rider', today_earnings=Decimal('11.00'))

        self.run_command('--once')

        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('11.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 1)

    def test_once_is_safe_to_repeat(self):
        rider = make_rider('cmd_repeat_rider', today_earnings=Decimal('11.00'))

        self.run_command('--once')
        self.run_command('--once')

        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('11.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 1)

    def test_explicit_date_closes_that_business_date(self):
        rider = make_rider('cmd_date_rider', today_earnings=Decimal('9.00'))

        self.run_command('--date', '2026-03-10')

        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('9.00'))
        self.assertEqual(
            EarningsResetRun.objects.get().business_date, date(2026, 3, 10)
        )

    def test_explicit_date_rejects_a_bogus_value(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command('--date', 'not-a-date')

    def test_explicit_date_refuses_to_close_a_future_day(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command('--date', '2030-01-01')


class DeliveryPathTests(TestCase):
    def deliver(self, rider, order, moment=RUN_MOMENT):
        from django.urls import reverse

        self.client.force_login(rider.user)
        order.refresh_from_db()
        with frozen_now(moment):
            return self.client.post(
                reverse('rider:mark_delivered', args=[order.pk]),
                {'otp': order.delivery_pin},
            )

    def test_delivery_files_the_earning_under_the_local_business_day(self):
        rider = make_rider('delivery_day_rider')
        order = make_order(make_user('delivery_day_customer'))
        OrderAssignment.objects.create(
            order=order, rider=rider, status='accepted'
        )

        # 00:30 IST on the 15th is still the 14th in UTC.
        self.deliver(
            rider, order, timezone.make_aware(datetime(2026, 3, 15, 0, 30))
        )

        rows = RiderEarning.objects.filter(rider=rider)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().date, date(2026, 3, 15))

    def test_delivery_and_reset_share_the_same_ledger_row(self):
        rider = make_rider('delivery_reset_rider')
        order = make_order(make_user('delivery_reset_customer'))
        OrderAssignment.objects.create(
            order=order, rider=rider, status='accepted'
        )

        # The delivery happens late on the 14th, the scheduled run fires
        # shortly after midnight and closes the 14th.
        self.deliver(
            rider, order, timezone.make_aware(datetime(2026, 3, 14, 23, 0))
        )

        rider.refresh_from_db()
        earned = rider.today_earnings
        self.assertGreater(earned, Decimal('0'))
        self.assertEqual(
            RiderEarning.objects.get(rider=rider).date, date(2026, 3, 14)
        )

        # The reset closes the day the delivery happened in; the delivery row
        # must not be duplicated.
        with frozen_now():
            summary = close_business_date(YESTERDAY)

        self.assertEqual(summary['status'], 'closed')
        self.assertEqual(summary['ledger_rows_created'], 0)
        self.assertEqual(RiderEarning.objects.filter(rider=rider).count(), 1)
        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, earned)
        self.assertEqual(rider.get_total_earnings(), earned)


class MigrationGuardTests(TestCase):
    """The migration must refuse to add the unique constraint over bad data."""

    def setUp(self):
        import importlib

        self.module = importlib.import_module(
            'rider_app.migrations.0003_earnings_reset_integrity'
        )

    def _duplicate_model(self, rows):
        """A throwaway model over a table with the same shape.

        The table is created with the schema editor so the test works on
        every backend, not only on SQLite.
        """
        from django.db import models

        table = 'rider_app_dup_earnings_test'
        model = type(
            'DuplicateEarning',
            (models.Model,),
            {
                '__module__': __name__,
                'rider_id': models.IntegerField(),
                'date': models.DateField(),
                'total_earnings': models.DecimalField(
                    max_digits=10, decimal_places=2
                ),
                'Meta': type('Meta', (), {
                    'db_table': table,
                    'managed': False,
                    'app_label': 'rider_app',
                }),
            },
        )
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
        # The DDL is collected and executed directly: the schema editor
        # cannot run inside the transaction a TestCase wraps around the
        # test on SQLite, and this keeps the test portable.
        editor = connection.schema_editor(collect_sql=True)
        editor.deferred_sql = []
        editor.create_model(model)
        statements = list(editor.collected_sql) + list(editor.deferred_sql)
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        with connection.cursor() as cursor:
            for rider_id, day in rows:
                cursor.execute(
                    f'INSERT INTO "{table}" (rider_id, date, total_earnings) '
                    'VALUES (%s, %s, %s)',
                    [rider_id, day, Decimal('10.00')],
                )
        return model

    def test_clean_data_passes_the_guard(self):
        model = self._duplicate_model([(1, YESTERDAY), (1, date(2026, 3, 13))])

        self.module.assert_model_has_no_duplicate_daily_earnings(model)

    def test_duplicate_rows_are_detected_and_nothing_is_deleted(self):
        model = self._duplicate_model([
            (1, YESTERDAY), (1, YESTERDAY), (2, YESTERDAY),
        ])

        with self.assertRaises(RuntimeError) as ctx:
            self.module.assert_model_has_no_duplicate_daily_earnings(model)

        message = str(ctx.exception)
        self.assertIn('duplicate', message.lower())
        self.assertIn('No data was changed', message)
        self.assertIn('rider=1', message)
        # the guard never deletes anything
        self.assertEqual(
            model.objects.count(), 3
        )

    def test_constraint_is_present_after_the_migration(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, 'rider_app_riderearning'
            )
        self.assertIn('unique_earning_per_rider_and_date', constraints)


class SchedulerGateTests(TestCase):
    def test_scheduler_thread_is_not_started_when_disabled(self):
        from rider_app.apps import RiderAppConfig

        config = RiderAppConfig.create('rider_app')
        with mock.patch('threading.Thread') as thread:
            with mock.patch(
                'django.conf.settings.EARNINGS_RESET_SCHEDULER_ENABLED', False
            ):
                config.ready()

        self.assertFalse(thread.called)

    def test_scheduler_thread_is_started_when_enabled(self):
        from rider_app.apps import RiderAppConfig

        config = RiderAppConfig.create('rider_app')
        with mock.patch('threading.Thread') as thread:
            with mock.patch(
                'django.conf.settings.EARNINGS_RESET_SCHEDULER_ENABLED', True
            ):
                with mock.patch('sys.argv', ['gunicorn', 'BITEQUE.wsgi']):
                    config.ready()

        self.assertTrue(thread.called)
