from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from merchant_app.models import (
    MerchantEarning,
    MerchantPayment,
    Restaurant,
)
from rider_app.models import OrderAssignment, RiderEarning
from rider_app.tests.test_assignment_flow import (
    make_order,
    make_rider,
    make_user,
)
from user_app.models import Order

from .helpers import make_merchant_restaurant


class DeliveryEarningBase(TestCase):
    def setUp(self):
        self.customer = make_user('money_customer')
        self.rider = make_rider('money_rider')
        self.order = make_order(self.customer, status='confirmed')
        self.assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider, status='accepted'
        )
        self.order.refresh_from_db()
        self.ajax = {'X-Requested-With': 'XMLHttpRequest'}

    def set_total(self, value):
        Order.objects.filter(pk=self.order.pk).update(total=value)
        self.order.refresh_from_db()

    def deliver(self, order=None, rider=None, pin=None):
        order = order or self.order
        rider = rider or self.rider
        self.client.force_login(rider.user)
        return self.client.post(
            reverse('rider:mark_delivered', args=[order.pk]),
            {'otp': pin or order.delivery_pin},
            headers=self.ajax,
        )

    @staticmethod
    def money(value):
        return Decimal(value).quantize(Decimal('0.01'))


class RiderCommissionTierTests(DeliveryEarningBase):
    TIERS = [
        ('100.00', '0.10'),
        ('199.99', '0.10'),
        ('200.00', '0.10'),
        ('200.01', '0.06'),
        ('400.00', '0.06'),
        ('400.01', '0.04'),
        ('1000.00', '0.04'),
        ('1000.01', '0.02'),
        ('2000.00', '0.02'),
        ('2000.01', '0.01'),
        ('4000.00', '0.01'),
        ('4000.01', '0.00'),
    ]

    def test_commission_tier_boundaries(self):
        for index, (total_value, rate) in enumerate(self.TIERS):
            with self.subTest(total=total_value, rate=rate):
                customer = make_user(f'tc{index}')
                order = make_order(customer, status='confirmed')
                rider = make_rider(f'tr{index}')
                OrderAssignment.objects.create(
                    order=order, rider=rider, status='accepted'
                )
                self.set_total_for(order, total_value)

                resp = self.deliver(order=order, rider=rider)
                self.assertEqual(resp.status_code, 200)

                order.refresh_from_db()
                expected_commission = (
                    Decimal(total_value) * Decimal(rate)
                ).quantize(Decimal('0.01'))
                expected_total = (
                    Decimal('40.00') + expected_commission
                ).quantize(Decimal('0.01'))
                self.assertEqual(order.commission, expected_commission)
                self.assertEqual(order.total_earning, expected_total)

                rider.refresh_from_db()
                self.assertEqual(rider.today_earnings, expected_total)

    def set_total_for(self, order, value):
        Order.objects.filter(pk=order.pk).update(total=value)
        order.refresh_from_db()

    def test_commission_rounds_half_even_at_two_places(self):
        self.set_total('199.99')
        resp = self.deliver()
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.commission, Decimal('20.00'))
        self.assertEqual(self.order.total_earning, Decimal('60.00'))

    def test_distance_earning_is_added_to_commission(self):
        self.set_total('300.00')
        self.deliver()
        self.order.refresh_from_db()
        self.assertEqual(self.order.commission, Decimal('18.00'))
        self.assertEqual(self.order.total_earning, Decimal('58.00'))
        self.assertEqual(
            self.order.total_earning,
            self.order.distance_earning + self.order.commission,
        )

    def test_delivery_marks_order_and_clears_pin(self):
        self.set_total('150.00')
        self.deliver()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertIsNone(self.order.delivery_pin)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'delivered')

    def test_redelivery_is_rejected_and_earns_nothing(self):
        self.set_total('150.00')
        first = self.deliver()
        self.assertEqual(first.status_code, 200)

        second = self.deliver()
        self.assertEqual(second.status_code, 404)

        self.order.refresh_from_db()
        self.rider.refresh_from_db()
        self.assertEqual(self.order.commission, Decimal('15.00'))
        self.assertEqual(self.rider.today_earnings, Decimal('55.00'))

    def test_two_deliveries_accumulate_into_one_daily_row(self):
        self.set_total('150.00')
        self.deliver()

        second_customer = make_user('money_customer_2')
        second_order = make_order(second_customer, status='confirmed')
        OrderAssignment.objects.create(
            order=second_order, rider=self.rider, status='accepted'
        )
        Order.objects.filter(pk=second_order.pk).update(total='300.00')
        second_order.refresh_from_db()

        resp = self.deliver(order=second_order)
        self.assertEqual(resp.status_code, 200)

        rows = RiderEarning.objects.filter(rider=self.rider)
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.orders_completed, 2)
        self.assertEqual(row.total_earnings, Decimal('113.00'))
        self.assertEqual(row.commission_earning, Decimal('33.00'))
        self.assertEqual(row.distance_earning, Decimal('80.00'))
        self.assertEqual(row.distance_km, Decimal('8.00'))

        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, Decimal('113.00'))

    def test_assignment_stats_updated_on_create(self):
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.total_assignments, 1)

    def test_delivery_requires_accepted_assignment(self):
        customer = make_user('no_accept_customer')
        order = make_order(customer, status='confirmed')
        OrderAssignment.objects.create(
            order=order, rider=self.rider, status='pending'
        )
        order.refresh_from_db()
        self.client.force_login(self.rider.user)
        resp = self.client.post(
            reverse('rider:mark_delivered', args=[order.pk]),
            {'otp': order.delivery_pin or '0000'},
            headers=self.ajax,
        )
        self.assertEqual(resp.status_code, 404)


class AcceptanceScoreTests(TestCase):
    def setUp(self):
        self.rider = make_rider('score_rider')
        self._seq = 0

    def score_for_age(self, seconds):
        self._seq += 1
        customer = make_user(f'sc{self._seq}')
        order = make_order(customer, status='confirmed')
        assignment = OrderAssignment.objects.create(
            order=order, rider=self.rider, status='accepted'
        )
        OrderAssignment.objects.filter(pk=assignment.pk).update(
            response_time=None,
            assigned_at=timezone.now() - timedelta(seconds=seconds),
        )
        assignment.refresh_from_db()
        assignment.save()
        assignment.refresh_from_db()
        return assignment.acceptance_score

    def test_response_time_scoring_tiers(self):
        cases = [
            (30, 100), (90, 90), (150, 80),
            (210, 70), (270, 50), (330, 0),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(
                    Decimal(self.score_for_age(seconds)),
                    Decimal(expected),
                )

    def test_score_not_recomputed_when_already_set(self):
        customer = make_user('score_freeze')
        order = make_order(customer, status='confirmed')
        assignment = OrderAssignment.objects.create(
            order=order, rider=self.rider, status='accepted'
        )
        original = assignment.acceptance_score
        OrderAssignment.objects.filter(pk=assignment.pk).update(
            assigned_at=timezone.now() - timedelta(seconds=999)
        )
        assignment.refresh_from_db()
        assignment.save()
        assignment.refresh_from_db()
        self.assertEqual(assignment.acceptance_score, original)


class MerchantMoneyBase(TestCase):
    def setUp(self):
        self.merchant = make_user('money_merchant')
        self.restaurant = make_merchant_restaurant(
            self.merchant, 'Money Kitchen'
        )
        self.client.force_login(self.merchant)
        self._seq = 0

    def next_customer(self):
        self._seq += 1
        return make_user(f'money_cust_{self._seq}')

    def delivered_order(self, total, age_days=0):
        order = make_order(self.next_customer(), status='delivered')
        Order.objects.filter(pk=order.pk).update(
            restaurant=self.restaurant,
            total=total,
            created_at=timezone.now() - timedelta(days=age_days),
        )
        order.refresh_from_db()
        return order


class MerchantEarningSyncTests(MerchantMoneyBase):
    def test_payment_section_syncs_earning_record(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)
        MerchantPayment.objects.create(
            merchant=self.merchant, restaurant=self.restaurant,
            amount_paid=Decimal('300.00'),
            payment_screenshot='payment_screenshots/a.jpg',
        )

        resp = self.client.get(reverse('merchant_payment_section'))
        self.assertEqual(resp.status_code, 200)

        earning = MerchantEarning.objects.get(
            merchant=self.merchant, restaurant=self.restaurant
        )
        self.assertEqual(earning.net_sales, Decimal('1500.00'))
        self.assertEqual(earning.weekly_sales, Decimal('1000.00'))
        self.assertEqual(earning.amount_paid, Decimal('300.00'))
        self.assertEqual(earning.amount_pending, Decimal('960.00'))

    def test_payment_section_context_values(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)
        MerchantPayment.objects.create(
            merchant=self.merchant, restaurant=self.restaurant,
            amount_paid=Decimal('300.00'),
            payment_screenshot='payment_screenshots/a.jpg',
        )

        resp = self.client.get(reverse('merchant_payment_section'))
        context = resp.context
        self.assertEqual(context['total_revenues'], Decimal('1500.00'))
        self.assertEqual(context['weekly_revenue'], Decimal('1000.00'))
        self.assertEqual(context['merchant_share'], Decimal('1260.00'))
        self.assertEqual(
            context['weekly_merchant_share'], Decimal('840.00')
        )
        self.assertEqual(
            context['weekly_platform_share'], Decimal('160.00')
        )
        self.assertEqual(context['paid_amount'], Decimal('300.00'))
        self.assertEqual(context['pending_amount'], Decimal('960.00'))
        self.assertEqual(context['subscription_fee'], 1000)
        self.assertEqual(len(context['payments']), 1)

    def test_undelivered_orders_are_excluded(self):
        self.delivered_order('1000.00', age_days=0)
        pending = make_order(self.next_customer(), status='pending')
        Order.objects.filter(pk=pending.pk).update(
            restaurant=self.restaurant, total='9999.00'
        )

        self.client.get(reverse('merchant_payment_section'))

        earning = MerchantEarning.objects.get(
            merchant=self.merchant, restaurant=self.restaurant
        )
        self.assertEqual(earning.net_sales, Decimal('1000.00'))

    def test_repeat_visits_update_single_row(self):
        self.delivered_order('1000.00', age_days=0)
        self.client.get(reverse('merchant_payment_section'))
        MerchantPayment.objects.create(
            merchant=self.merchant, restaurant=self.restaurant,
            amount_paid=Decimal('200.00'),
            payment_screenshot='payment_screenshots/b.jpg',
        )
        self.client.get(reverse('merchant_payment_section'))

        self.assertEqual(
            MerchantEarning.objects.filter(
                merchant=self.merchant
            ).count(),
            1,
        )
        earning = MerchantEarning.objects.get(merchant=self.merchant)
        self.assertEqual(earning.amount_paid, Decimal('200.00'))
        self.assertEqual(earning.amount_pending, Decimal('640.00'))

    def test_overpayment_produces_negative_pending(self):
        self.delivered_order('100.00', age_days=0)
        MerchantPayment.objects.create(
            merchant=self.merchant, restaurant=self.restaurant,
            amount_paid=Decimal('500.00'),
            payment_screenshot='payment_screenshots/c.jpg',
        )
        self.client.get(reverse('merchant_payment_section'))

        earning = MerchantEarning.objects.get(merchant=self.merchant)
        self.assertEqual(earning.amount_pending, Decimal('-416.00'))


class RevenueReportMathTests(MerchantMoneyBase):
    def test_report_context_math(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)

        resp = self.client.get(reverse('merchant_revenue_report'))
        self.assertEqual(resp.status_code, 200)
        context = resp.context

        self.assertEqual(context['total_revenue'], Decimal('1260.00'))
        self.assertEqual(
            context['week_revenue'], context['total_revenue']
        )
        self.assertEqual(
            context['month_revenue'], context['total_revenue']
        )

    def test_today_revenue_counts_only_delivered_orders_created_today(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)

        resp = self.client.get(reverse('merchant_revenue_report'))
        context = resp.context

        today_total = Order.objects.filter(
            restaurant=self.restaurant,
            status='delivered',
            created_at__date=datetime.today().date(),
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        self.assertEqual(
            context['today_revenue'], today_total * Decimal('0.84')
        )

    def test_chart_series_covers_thirty_days(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)

        resp = self.client.get(reverse('merchant_revenue_report'))
        context = resp.context

        import json
        labels = json.loads(context['chart_labels'])
        data = json.loads(context['chart_data'])
        self.assertEqual(len(labels), 30)
        self.assertEqual(len(data), 30)
        self.assertEqual(sum(data), 1500.0)
        self.assertEqual(data[29], 1000.0)
        self.assertEqual(data[19], 500.0)

    def test_report_ignores_pending_orders(self):
        self.delivered_order('1000.00', age_days=0)
        pending = make_order(self.next_customer(), status='pending')
        Order.objects.filter(pk=pending.pk).update(
            restaurant=self.restaurant, total='9999.00'
        )

        resp = self.client.get(reverse('merchant_revenue_report'))
        self.assertEqual(resp.context['total_revenue'], Decimal('840.00'))


class OrderReportMathTests(MerchantMoneyBase):
    def test_report_counts_all_statuses_but_today_only_delivered(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)
        pending = make_order(self.next_customer(), status='pending')
        Order.objects.filter(pk=pending.pk).update(
            restaurant=self.restaurant, total='9999.00'
        )

        resp = self.client.get(reverse('order_report'))
        self.assertEqual(resp.status_code, 200)
        context = resp.context

        self.assertEqual(context['total_orders'], 3)
        self.assertEqual(context['total_revenue'], Decimal('11499.00'))
        self.assertEqual(context['thirty_day_orders'], 3)
        self.assertEqual(context['thirty_day_revenue'], Decimal('11499.00'))
        self.assertEqual(context['seven_day_orders'], 2)
        self.assertEqual(context['seven_day_revenue'], Decimal('10999.00'))
        self.assertEqual(context['today_orders'], 1)
        self.assertEqual(context['today_revenue'], Decimal('1000.00'))

    def test_order_chart_counts_by_day(self):
        self.delivered_order('1000.00', age_days=0)
        self.delivered_order('500.00', age_days=10)
        pending = make_order(self.next_customer(), status='pending')
        Order.objects.filter(pk=pending.pk).update(
            restaurant=self.restaurant, total='9999.00'
        )

        resp = self.client.get(reverse('order_report'))
        import json
        labels = json.loads(resp.context['order_chart_labels'])
        data = json.loads(resp.context['order_chart_data'])
        self.assertEqual(len(labels), 30)
        self.assertEqual(len(data), 30)
        self.assertEqual(sum(data), 3)
        self.assertEqual(data[29], 2)
        self.assertEqual(data[19], 1)

    def test_report_is_per_merchant_restaurants(self):
        self.delivered_order('1000.00', age_days=0)
        other_owner = make_user('other_report_owner')
        other_restaurant = make_merchant_restaurant(
            other_owner, 'Other Kitchen'
        )
        other_order = make_order(
            make_user('other_report_customer'), status='delivered'
        )
        Order.objects.filter(pk=other_order.pk).update(
            restaurant=other_restaurant, total='777.00'
        )

        resp = self.client.get(reverse('order_report'))
        self.assertEqual(resp.context['total_orders'], 1)
        self.assertEqual(resp.context['total_revenue'], Decimal('1000.00'))


class FinalTotalInvariantTests(TestCase):
    def setUp(self):
        self.customer = make_user('final_total_customer')
        self.order = make_order(self.customer, status='pending')

    def save_with(self, **fields):
        for name, value in fields.items():
            setattr(self.order, name, Decimal(value))
        self.order.save()
        self.order.refresh_from_db()

    def test_final_total_sums_all_components(self):
        self.save_with(
            total='100.00', item_gst='5.00',
            packaging_charges='10.00', distance_earning='40.00',
        )
        self.assertEqual(self.order.final_total, Decimal('155.00'))

    def test_default_packaging_is_ten_rupees(self):
        self.save_with(total='200.00', distance_earning='0.00')
        self.assertEqual(self.order.packaging_charges, Decimal('10.00'))
        self.assertEqual(
            self.order.final_total,
            Decimal('210.00') + self.order.item_gst,
        )

    def test_final_total_recomputes_when_total_changes(self):
        self.save_with(total='100.00')
        self.assertEqual(self.order.final_total, Decimal('150.00'))
        self.save_with(total='250.00')
        self.assertEqual(self.order.final_total, Decimal('300.00'))

    def test_final_total_is_quantised_to_two_places(self):
        self.save_with(
            total='99.99', item_gst='0.01',
            packaging_charges='10.00', distance_earning='0.00',
        )
        self.assertEqual(self.order.final_total, Decimal('110.00'))
        self.assertEqual(
            self.order.final_total.as_tuple().exponent, -2
        )

    def test_update_fields_save_does_not_persist_final_total(self):
        self.save_with(total='100.00')
        stale_final = self.order.final_total

        self.order.total = Decimal('999.00')
        self.order.commission = Decimal('5.00')
        self.order.save(update_fields=['commission'])

        self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, stale_final)
        self.assertEqual(self.order.commission, Decimal('5.00'))

    def test_zero_distance_keeps_packaging_and_gst(self):
        self.save_with(
            total='500.00', item_gst='25.00',
            packaging_charges='10.00', distance_earning='0.00',
        )
        self.assertEqual(self.order.final_total, Decimal('535.00'))
