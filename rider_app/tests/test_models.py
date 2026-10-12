from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from rider_app.models import (
    OrderAssignment,
    Rider,
    RiderBankAccount,
    RiderEarning,
    Transaction,
)

from .test_assignment_flow import make_order, make_rider, make_user


class RiderStrTests(TestCase):
    def test_str_reports_approval_state(self):
        pending = make_rider('str_pending', approved=False)
        approved = make_rider('str_approved')

        self.assertEqual(str(pending), 'str_pending (Pending)')
        self.assertEqual(str(approved), 'str_approved (Approved)')


class RiderAggregateTests(TestCase):
    def setUp(self):
        self.rider = make_rider('agg_rider')

    def test_total_earnings_starts_empty_then_sums_rows(self):
        self.assertEqual(self.rider.get_total_earnings(), 0)

        RiderEarning.objects.create(
            rider=self.rider,
            date=date(2026, 3, 1),
            total_earnings=Decimal('100.00'),
            orders_completed=1,
        )
        RiderEarning.objects.create(
            rider=self.rider,
            date=date(2026, 3, 2),
            total_earnings=Decimal('40.50'),
            orders_completed=2,
        )

        self.assertEqual(self.rider.get_total_earnings(), Decimal('140.50'))

    def test_total_orders_completed_counts_delivered_only(self):
        statuses = ['pending', 'accepted', 'rejected', 'delivered']
        for index, status in enumerate(statuses):
            order = make_order(make_user(f'agg_cust_{index}'))
            OrderAssignment.objects.create(
                order=order, rider=self.rider, status=status
            )

        self.assertEqual(self.rider.get_total_orders_completed(), 1)

    def test_acceptance_rate_zero_without_decided_assignments(self):
        self.assertEqual(self.rider.get_acceptance_rate(), 0.0)

        order = make_order(make_user('agg_pending_cust'))
        OrderAssignment.objects.create(
            order=order, rider=self.rider, status='pending'
        )

        self.assertEqual(self.rider.get_acceptance_rate(), 0.0)

    def test_acceptance_rate_averages_mixed_outcomes(self):
        scores = [('accepted', 100), ('accepted', 50), ('rejected', 0)]
        for index, (status, score) in enumerate(scores):
            order = make_order(make_user(f'agg_rate_{index}'))
            OrderAssignment.objects.create(
                order=order,
                rider=self.rider,
                status=status,
                response_time=timedelta(seconds=30),
                acceptance_score=score,
            )

        self.assertAlmostEqual(float(self.rider.get_acceptance_rate()), 50.0)

    def test_acceptance_rate_rounds_to_one_decimal(self):
        outcomes = ['accepted', 'rejected', 'rejected']
        for index, status in enumerate(outcomes):
            order = make_order(make_user(f'agg_round_{index}'))
            OrderAssignment.objects.create(
                order=order,
                rider=self.rider,
                status=status,
                response_time=timedelta(seconds=30),
                acceptance_score=80 if status == 'accepted' else 0,
            )

        self.assertAlmostEqual(float(self.rider.get_acceptance_rate()), 26.7)

    def test_current_balance_subtracts_processed_payments_only(self):
        self.assertEqual(self.rider.get_current_balance(), 0)

        RiderEarning.objects.create(
            rider=self.rider,
            date=date(2026, 3, 1),
            total_earnings=Decimal('100.00'),
            orders_completed=1,
        )
        RiderEarning.objects.create(
            rider=self.rider,
            date=date(2026, 3, 2),
            total_earnings=Decimal('100.00'),
            orders_completed=1,
        )
        Transaction.objects.create(
            rider=self.rider,
            amount=Decimal('50.00'),
            transaction_type='payment',
            description='processed payout',
            processed=True,
        )
        Transaction.objects.create(
            rider=self.rider,
            amount=Decimal('30.00'),
            transaction_type='payment',
            description='unprocessed payout',
        )
        Transaction.objects.create(
            rider=self.rider,
            amount=Decimal('20.00'),
            transaction_type='pending',
            description='pending balance',
            processed=True,
        )

        self.assertEqual(
            self.rider.get_current_balance(), Decimal('150.00')
        )

    def test_transaction_history_newest_first(self):
        older = Transaction.objects.create(
            rider=self.rider,
            amount=Decimal('10.00'),
            transaction_type='payment',
            description='oldest',
        )
        middle = Transaction.objects.create(
            rider=self.rider,
            amount=Decimal('20.00'),
            transaction_type='pending',
            description='middle',
        )
        newest = Transaction.objects.create(
            rider=self.rider,
            amount=Decimal('30.00'),
            transaction_type='payment',
            description='newest',
        )
        Transaction.objects.filter(pk=older.pk).update(
            transaction_date=timezone.now() - timedelta(days=2)
        )
        Transaction.objects.filter(pk=middle.pk).update(
            transaction_date=timezone.now() - timedelta(days=1)
        )

        expected = [newest.pk, middle.pk, older.pk]
        history = list(self.rider.get_transaction_history())
        default_order = list(
            Transaction.objects.filter(rider=self.rider)
        )
        self.assertEqual([row.pk for row in history], expected)
        self.assertEqual([row.pk for row in default_order], expected)


class RiderEarningTests(TestCase):
    def test_str_and_default_ordering(self):
        rider = make_rider('earning_str')
        older = RiderEarning.objects.create(
            rider=rider,
            date=date(2026, 3, 1),
            total_earnings=Decimal('100.00'),
            orders_completed=2,
        )
        newer = RiderEarning.objects.create(
            rider=rider,
            date=date(2026, 3, 5),
            total_earnings=Decimal('50.00'),
            orders_completed=1,
        )

        self.assertEqual(
            str(older), 'Earnings on 2026-03-01 - ₹100.00'
        )
        rows = list(RiderEarning.objects.filter(rider=rider))
        self.assertEqual([row.pk for row in rows], [newer.pk, older.pk])


class OrderAssignmentTests(TestCase):
    def test_str_and_default_ordering(self):
        rider = make_rider('assign_str')
        older = make_order(make_user('assign_cust_1'))
        newer = make_order(make_user('assign_cust_2'))
        first = OrderAssignment.objects.create(
            order=older,
            rider=rider,
            status='pending',
            assigned_at=timezone.now() - timedelta(hours=2),
        )
        second = OrderAssignment.objects.create(
            order=newer,
            rider=rider,
            status='rejected',
            assigned_at=timezone.now(),
        )

        self.assertEqual(
            str(second),
            f'Order #{newer.id} → assign_str [rejected]',
        )
        rows = list(OrderAssignment.objects.filter(rider=rider))
        self.assertEqual([row.pk for row in rows], [second.pk, first.pk])

    def test_only_one_accepted_assignment_allowed_per_order(self):
        order = make_order(make_user('assign_unique'))
        rider_a = make_rider('assign_a')
        rider_b = make_rider('assign_b')
        rider_c = make_rider('assign_c')

        OrderAssignment.objects.create(
            order=order, rider=rider_a, status='pending'
        )
        OrderAssignment.objects.create(
            order=order, rider=rider_b, status='pending'
        )
        OrderAssignment.objects.create(
            order=order, rider=rider_c, status='accepted'
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderAssignment.objects.create(
                    order=order, rider=rider_a, status='accepted'
                )

        self.assertEqual(
            OrderAssignment.objects.filter(
                order=order, status='accepted'
            ).count(),
            1,
        )


class RiderBankAccountTests(TestCase):
    def test_saving_new_primary_demotes_previous_primary(self):
        rider = make_rider('bank_rider')
        first = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='First Holder',
            account_number='111111111111',
            bank_name='First Bank',
            ifsc_code='FIRST000001',
            is_primary=True,
        )
        second = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Second Holder',
            account_number='222222222222',
            bank_name='Second Bank',
            ifsc_code='SECO0000002',
            is_primary=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)
        self.assertEqual(
            RiderBankAccount.objects.filter(
                rider=rider, is_primary=True
            ).count(),
            1,
        )
        self.assertEqual(
            str(second),
            'bank_rider - 222222222222 (Primary)',
        )

    def test_second_primary_row_blocked_by_constraint(self):
        rider = make_rider('bank_unique')
        primary = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Primary Holder',
            account_number='333333333333',
            bank_name='Primary Bank',
            ifsc_code='PRIM0000003',
            is_primary=True,
        )
        secondary = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Secondary Holder',
            account_number='444444444444',
            bank_name='Secondary Bank',
            ifsc_code='SECU0000004',
        )
        self.assertIsNotNone(primary.pk)
        self.assertIsNotNone(secondary.pk)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RiderBankAccount.objects.filter(
                    pk=secondary.pk
                ).update(is_primary=True)


class TransactionTests(TestCase):
    def test_defaults_and_str(self):
        rider = make_rider('txn_rider')
        payment = Transaction.objects.create(
            rider=rider,
            amount=Decimal('50.00'),
            transaction_type='payment',
            description='weekly payout',
        )
        pending = Transaction.objects.create(
            rider=rider,
            amount=Decimal('20.00'),
            transaction_type='pending',
            description='held balance',
        )

        self.assertFalse(payment.processed)
        self.assertFalse(pending.processed)
        self.assertIsNotNone(payment.transaction_date)
        self.assertEqual(str(payment), 'Payment to Rider - ₹50.00')
        self.assertEqual(str(pending), 'Pending Balance - ₹20.00')
