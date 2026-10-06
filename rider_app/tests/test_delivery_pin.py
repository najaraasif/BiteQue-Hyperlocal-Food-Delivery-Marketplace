from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from user_app.models import DELIVERY_PIN_MAX_ATTEMPTS, Order

from rider_app.models import OrderAssignment, RiderEarning

from .test_assignment_flow import make_order, make_rider, make_user


class BasePinFlowTests(TestCase):
    """Shared setup: an accepted assignment with a freshly issued PIN."""

    def setUp(self):
        self.customer = make_user('pin_customer')
        self.rider = make_rider('pin_rider')
        self.order = make_order(self.customer, status='out_for_delivery')
        self.assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider, status='accepted'
        )
        self.order.generate_delivery_pin()
        self.order.save()
        self.pin = self.order.delivery_pin
        self.ajax = {'X-Requested-With': 'XMLHttpRequest'}

    def post_pin(self, pin, user=None):
        self.client.force_login(user or self.rider.user)
        return self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id]),
            {'otp': pin},
            headers=self.ajax,
        )

    def wrong_pins(self, count):
        pool = ['1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888']
        return [value for value in pool if value != self.pin][:count]

    def age_pin(self, minutes):
        Order.objects.filter(pk=self.order.pk).update(
            delivery_pin_generated_at=timezone.now() - timedelta(minutes=minutes)
        )
        self.order.refresh_from_db()


class DeliveryPinModelTests(TestCase):
    def setUp(self):
        self.customer = make_user('model_cust')
        self.order = make_order(self.customer, status='out_for_delivery')
        Order.objects.filter(pk=self.order.pk).update(
            delivery_pin='1357',
            delivery_pin_generated_at=timezone.now(),
        )
        self.order.refresh_from_db()

    def test_fresh_pin_validates(self):
        self.assertTrue(self.order.is_delivery_pin_valid('1357'))
        self.assertFalse(self.order.is_delivery_pin_valid('1358'))
        self.assertFalse(self.order.is_delivery_pin_valid(''))

    def test_expired_pin_is_invalid(self):
        ttl = getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30)
        Order.objects.filter(pk=self.order.pk).update(
            delivery_pin_generated_at=timezone.now() - timedelta(minutes=ttl + 1)
        )
        self.order.refresh_from_db()
        self.assertTrue(self.order.delivery_pin_is_expired())
        self.assertFalse(self.order.is_delivery_pin_valid('1357'))

    def test_pin_invalid_after_delivery_status(self):
        # Even if a row somehow still carries a PIN after the order was
        # delivered, it can no longer validate.
        Order.objects.filter(pk=self.order.pk).update(status='delivered')
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_delivery_pin_valid('1357'))

    def test_generate_resets_attempt_budget(self):
        Order.objects.filter(pk=self.order.pk).update(delivery_pin_attempts=4)
        self.order.refresh_from_db()
        self.order.generate_delivery_pin()
        self.assertEqual(self.order.delivery_pin_attempts, 0)

    def test_register_failure_invalidates_at_cap(self):
        for attempt in range(1, DELIVERY_PIN_MAX_ATTEMPTS):
            invalidated = self.order.register_delivery_pin_failure()
            self.order.refresh_from_db()
            self.assertFalse(invalidated)
            self.assertEqual(self.order.delivery_pin_attempts, attempt)
            self.assertIsNotNone(self.order.delivery_pin)

        invalidated = self.order.register_delivery_pin_failure()
        self.order.refresh_from_db()
        self.assertTrue(invalidated)
        self.assertIsNone(self.order.delivery_pin)
        self.assertIsNone(self.order.delivery_pin_generated_at)
        self.assertEqual(self.order.delivery_pin_attempts, 0)


class DeliveryPinExpiryTests(BasePinFlowTests):
    def ttl(self):
        return getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30)

    def test_correct_pin_past_ttl_is_rejected(self):
        self.age_pin(self.ttl() + 1)
        resp = self.post_pin(self.pin)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('expired', resp.json()['message'].lower())

        # An expired PIN does not consume the brute-force budget.
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_pin_attempts, 0)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'accepted')
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, 0)

    def test_correct_pin_within_ttl_is_accepted(self):
        self.age_pin(1)
        resp = self.post_pin(self.pin)
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertIsNone(self.order.delivery_pin)


class DeliveryPinBruteForceTests(BasePinFlowTests):
    def test_cap_reached_invalidates_pin_and_credits_nothing(self):
        for index, wrong in enumerate(
            self.wrong_pins(DELIVERY_PIN_MAX_ATTEMPTS), start=1
        ):
            resp = self.post_pin(wrong)
            self.assertEqual(resp.status_code, 400)
            self.order.refresh_from_db()
            if index < DELIVERY_PIN_MAX_ATTEMPTS:
                self.assertEqual(self.order.delivery_pin_attempts, index)
                self.assertIsNotNone(self.order.delivery_pin)
            else:
                self.assertIsNone(self.order.delivery_pin)
                self.assertIsNone(self.order.delivery_pin_generated_at)
                self.assertEqual(self.order.delivery_pin_attempts, 0)
                self.assertIn('new pin', resp.json()['message'].lower())

        # The original PIN is worthless once invalidated.
        resp = self.post_pin(self.pin)
        self.assertEqual(resp.status_code, 400)

        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, 0)
        self.assertEqual(RiderEarning.objects.filter(rider=self.rider).count(), 0)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'accepted')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')

    def test_correct_pin_within_budget_still_works(self):
        resp = self.post_pin(self.wrong_pins(1)[0])
        self.assertEqual(resp.status_code, 400)
        resp = self.post_pin(self.pin)
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')


class DeliveryPinReissueTests(BasePinFlowTests):
    def customer_get(self):
        self.client.force_login(self.customer)
        return self.client.get(
            reverse('order_detail', args=[self.order.id])
        )

    def test_fresh_pin_is_not_reissued(self):
        resp = self.customer_get()
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_pin, self.pin)

    def test_expired_pin_is_reissued_for_owner(self):
        self.age_pin(
            getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30) + 1
        )
        old_generated_at = self.order.delivery_pin_generated_at

        resp = self.customer_get()
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivery_pin)
        self.assertFalse(self.order.delivery_pin_is_expired())
        self.assertGreater(self.order.delivery_pin_generated_at, old_generated_at)
        self.assertEqual(self.order.delivery_pin_attempts, 0)

    def test_invalidated_pin_is_reissued_and_rider_can_finish(self):
        for wrong in self.wrong_pins(DELIVERY_PIN_MAX_ATTEMPTS):
            self.post_pin(wrong)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.delivery_pin)

        resp = self.customer_get()
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivery_pin)
        self.assertEqual(self.order.delivery_pin_attempts, 0)

        resp = self.post_pin(self.order.delivery_pin)
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, 40)

    def test_non_owner_cannot_trigger_reissue(self):
        self.age_pin(
            getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30) + 1
        )
        stale_generated_at = self.order.delivery_pin_generated_at

        stranger = make_user('pin_stranger')
        self.client.force_login(stranger)
        resp = self.client.get(reverse('order_detail', args=[self.order.id]))
        self.assertEqual(resp.status_code, 404)

        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_pin_generated_at, stale_generated_at)


class DeliveryPinLoggingTests(BasePinFlowTests):
    def test_pin_value_never_appears_in_logs(self):
        # Force a distinctive PIN so an accidental match with an id or
        # timestamp in a log line is impossible.
        Order.objects.filter(pk=self.order.pk).update(
            delivery_pin='8642',
            delivery_pin_generated_at=timezone.now(),
        )
        self.order.refresh_from_db()

        with self.assertLogs(level='DEBUG') as captured:
            resp = self.post_pin('9999')
            self.assertEqual(resp.status_code, 400)
            resp = self.post_pin('8642')
            self.assertEqual(resp.status_code, 200)

        logged = '\n'.join(captured.output)
        self.assertNotIn('8642', logged)
