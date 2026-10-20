"""PostgreSQL specific tests for the reset lock and concurrent execution.

These tests are skipped unless the default database is PostgreSQL, because
SQLite cannot provide the guarantees the production database gives:

* SQLite has no advisory locks, so a concurrent reset is only excluded by the
  unique business date constraint;
* SQLite serialises writers with a database wide lock, so it cannot reproduce
  two genuinely concurrent sessions.

Run them against a real PostgreSQL with::

    $env:DATABASE_URL = 'postgresql://user:password@host:5432/dbname'
    .\.venv\Scripts\python.exe manage.py test rider_app.tests.test_earnings_reset_postgres

The database must be a scratch database: these tests write rows.
"""
import threading
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.db import connection, connections, transaction
from django.utils import timezone

from rider_app import earnings
from rider_app.models import EarningsResetRun, RiderEarning
from rider_app.tests.postgres_base import PostgresTransactionTestCase

from .test_assignment_flow import make_rider

RUN_MOMENT = timezone.make_aware(datetime(2026, 3, 15, 0, 5))
YESTERDAY = date(2026, 3, 14)

requires_postgres = unittest.skipUnless(
    connection.vendor == 'postgresql',
    'these guarantees only exist on PostgreSQL',
)


@requires_postgres
class PostgresAdvisoryLockTests(PostgresTransactionTestCase):
    def test_lock_is_acquired_and_released_with_the_transaction(self):
        with transaction.atomic():
            with earnings.reset_lock() as lock:
                self.assertEqual(lock['state'], 'locked')
                self.assertIn('advisory lock', lock['detail'])

        # The lock is transaction scoped, so it is free again afterwards.
        with transaction.atomic():
            with earnings.reset_lock() as lock:
                self.assertEqual(lock['state'], 'locked')

    def test_reset_is_skipped_while_another_session_holds_the_lock(self):
        import psycopg2

        rider = make_rider('pg_locked_rider', today_earnings=Decimal('42.00'))

        settings_dict = connection.settings_dict
        other = psycopg2.connect(
            host=settings_dict['HOST'],
            port=settings_dict['PORT'],
            dbname=settings_dict['NAME'],
            user=settings_dict['USER'],
            password=settings_dict['PASSWORD'],
        )
        other.autocommit = False
        try:
            with other.cursor() as cursor:
                cursor.execute(
                    'SELECT pg_try_advisory_xact_lock(%s)',
                    [earnings.RESET_ADVISORY_LOCK_KEY],
                )
                self.assertTrue(cursor.fetchone()[0])

            with mock.patch('django.utils.timezone.now', return_value=RUN_MOMENT):
                summary = earnings.close_business_date(YESTERDAY)
        finally:
            other.rollback()
            other.close()

        self.assertEqual(summary['status'], 'locked')
        self.assertIn('lock', summary['message'])
        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('0.00'))
        self.assertEqual(rider.today_earnings, Decimal('42.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 0)
        self.assertEqual(RiderEarning.objects.count(), 0)

    def test_two_concurrent_resets_credit_the_rider_once(self):
        rider = make_rider('pg_concurrent_rider', today_earnings=Decimal('100.00'))

        results = []
        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=10)
                with mock.patch(
                    'django.utils.timezone.now', return_value=RUN_MOMENT
                ):
                    results.append(earnings.close_business_date(YESTERDAY))
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                # a worker thread keeps its own database connection; leaving
                # it open would block the test database cleanup
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        statuses = [result['status'] for result in results]
        # exactly one run closes the business date, the other one does not
        self.assertEqual(statuses.count('closed'), 1)
        skipped = [status for status in statuses if status != 'closed']
        self.assertEqual(len(skipped), 1)
        self.assertIn(skipped[0], ('already_closed', 'locked'))

        rider.refresh_from_db()
        self.assertEqual(rider.current_balance, Decimal('100.00'))
        self.assertEqual(rider.today_earnings, Decimal('0.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 1)
        self.assertEqual(RiderEarning.objects.filter(rider=rider).count(), 1)

    def test_concurrent_resets_of_different_dates_do_not_block_each_other(self):
        first = make_rider('pg_multi_a', today_earnings=Decimal('10.00'))
        second = make_rider('pg_multi_b', today_earnings=Decimal('20.00'))

        with mock.patch('django.utils.timezone.now', return_value=RUN_MOMENT):
            earnings.close_business_date(YESTERDAY)
            earnings.close_business_date(YESTERDAY - timedelta(days=1))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.current_balance, Decimal('10.00'))
        self.assertEqual(second.current_balance, Decimal('20.00'))
        self.assertEqual(EarningsResetRun.objects.count(), 2)
