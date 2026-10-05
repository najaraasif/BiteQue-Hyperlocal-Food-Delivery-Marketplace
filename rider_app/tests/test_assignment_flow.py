import zlib
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from merchant_app.models import Restaurant
from user_app.models import Order
from rider_app.forms import DeliveryOTPForm
from rider_app.models import OrderAssignment, Rider, RiderEarning


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username, password='pw12345678', **kwargs
    )


def make_rider(username, approved=True, available=True, **rider_kwargs):
    user = make_user(username)
    # aadhar_number and driving_license are unique columns; derive
    # deterministic per-username values (aadhar must be exactly 12 digits).
    aadhar = str(10_000_000_000 + zlib.crc32(username.encode()) % 10**11)
    defaults = dict(
        phone='9876543210',
        gender='Male',
        aadhar_number=aadhar,
        driving_license=f'DL-{username}'[:20],
        address='1 Test Street',
        area='Test Area',
        pincode='123456',
        profile_photo='riders/profiles/p.jpg',
        aadhar_front='riders/aadhar/f.jpg',
        license_copy='riders/license/l.jpg',
        is_approved=approved,
        is_available=available,
    )
    defaults.update(rider_kwargs)
    rider = Rider.objects.create(user=user, **defaults)
    return rider


def make_order(customer, status='confirmed', contact=''):
    owner = User.objects.create_user(
        username=f'owner_{customer.username}', password='pw12345678'
    )
    restaurant = Restaurant.objects.create(
        owner=owner,
        name='Test Kitchen',
        email='kitchen@example.com',
        contact_number='9876543210',
        address='1 Main Road',
        city='Testville',
    )
    return Order.objects.create(
        user=customer,
        restaurant=restaurant,
        customer_name='Test Customer',
        customer_contact=contact,
        landmark='Near park',
        delivery_address='1 Delivery Road',
        special_instructions='',
        status=status,
        distance_earning=Decimal('40.00'),
        distance_km=Decimal('4.00'),
    )


class AcceptOrderTests(TestCase):
    def setUp(self):
        self.customer = make_user('cust1')
        self.rider1 = make_rider('rider1')
        self.rider2 = make_rider('rider2')
        self.order = make_order(self.customer)

    def test_accept_sets_out_for_delivery_and_pin(self):
        a1 = OrderAssignment.objects.create(
            order=self.order, rider=self.rider1, status='pending'
        )
        OrderAssignment.objects.create(
            order=self.order, rider=self.rider2, status='pending'
        )
        self.client.force_login(self.rider1.user)

        resp = self.client.post(
            reverse('rider:accept_order', args=[self.order.id])
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
        a1.refresh_from_db()
        self.assertEqual(a1.status, 'accepted')
        self.assertIsNotNone(a1.accepted_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')
        self.assertTrue(self.order.delivery_pin)
        self.assertEqual(len(self.order.delivery_pin), 4)
        self.assertTrue(self.order.delivery_pin.isdigit())

    def test_accept_rejects_other_pending_assignments(self):
        a1 = OrderAssignment.objects.create(
            order=self.order, rider=self.rider1, status='pending'
        )
        a2 = OrderAssignment.objects.create(
            order=self.order, rider=self.rider2, status='pending'
        )
        self.client.force_login(self.rider1.user)
        self.client.post(reverse('rider:accept_order', args=[self.order.id]))

        a2.refresh_from_db()
        self.assertEqual(a2.status, 'rejected')
        a1.refresh_from_db()
        self.assertEqual(a1.status, 'accepted')

    def test_second_rider_cannot_accept(self):
        OrderAssignment.objects.create(
            order=self.order, rider=self.rider1, status='pending'
        )
        OrderAssignment.objects.create(
            order=self.order, rider=self.rider2, status='pending'
        )
        self.client.force_login(self.rider1.user)
        self.client.post(reverse('rider:accept_order', args=[self.order.id]))

        self.client.force_login(self.rider2.user)
        resp = self.client.post(
            reverse('rider:accept_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 409)

    def test_rider_without_assignment_cannot_accept(self):
        self.client.force_login(self.rider2.user)
        resp = self.client.post(
            reverse('rider:accept_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 409)

    def test_accept_requires_login(self):
        OrderAssignment.objects.create(
            order=self.order, rider=self.rider1, status='pending'
        )
        resp = self.client.post(
            reverse('rider:accept_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 302)


class MarkDeliveredTests(TestCase):
    def setUp(self):
        self.customer = make_user('cust2')
        self.rider = make_rider('riderA')
        self.other_rider = make_rider('riderB')
        self.order = make_order(self.customer, status='out_for_delivery')
        self.assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider, status='accepted'
        )
        self.order.generate_delivery_pin()
        self.order.save()
        self.client.force_login(self.rider.user)
        self.ajax = {'X-Requested-With': 'XMLHttpRequest'}

    def test_deliver_with_correct_pin_credits_once(self):
        resp = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id]),
            {'otp': self.order.delivery_pin},
            headers=self.ajax,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')

        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, Decimal('40.00'))
        self.assertEqual(
            RiderEarning.objects.filter(rider=self.rider).count(), 1
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertIsNone(self.order.delivery_pin)

    def test_double_submit_cannot_earn_twice(self):
        pin = self.order.delivery_pin
        first = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id]),
            {'otp': pin},
            headers=self.ajax,
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id]),
            {'otp': pin},
            headers=self.ajax,
        )
        self.assertEqual(second.status_code, 404)

        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, Decimal('40.00'))
        self.assertEqual(
            RiderEarning.objects.filter(rider=self.rider).count(), 1
        )

    def test_wrong_pin_rejected(self):
        pin = self.order.delivery_pin
        wrong = '9999' if pin != '9999' else '1111'
        resp = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id]),
            {'otp': wrong},
            headers=self.ajax,
        )
        self.assertEqual(resp.status_code, 400)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'accepted')
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.today_earnings, Decimal('0.00'))

        retry = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id]),
            {'otp': pin},
            headers=self.ajax,
        )
        self.assertEqual(retry.status_code, 200)

    def test_deliver_requires_accepted_assignment(self):
        resp = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.id + 999]),
            {'otp': '1234'},
            headers=self.ajax,
        )
        self.assertEqual(resp.status_code, 404)


class UpdateAvailabilityTests(TestCase):
    def setUp(self):
        self.rider = make_rider('riderC')

    def test_toggle_flips_availability(self):
        self.assertTrue(self.rider.is_available)
        self.client.force_login(self.rider.user)

        with mock.patch('rider_app.signals.send_brevo_email') as emailer:
            resp = self.client.post(reverse('rider:update_availability'))
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertEqual(payload['status'], 'success')
            self.assertFalse(payload['is_available'])
            # Availability toggles must never re-send the welcome e-mail.
            emailer.assert_not_called()

        self.rider.refresh_from_db()
        self.assertFalse(self.rider.is_available)

        resp = self.client.post(reverse('rider:update_availability'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['is_available'])

    def test_requires_authentication(self):
        resp = self.client.post(reverse('rider:update_availability'))
        self.assertEqual(resp.status_code, 401)


class RiderApprovalEmailTests(TestCase):
    def test_welcome_email_sent_only_on_approval_transition(self):
        rider = make_rider('riderPending', approved=False)
        with mock.patch('rider_app.signals.send_brevo_email') as emailer:
            rider.is_approved = True
            rider.save()
            emailer.assert_called_once()

            rider.is_available = False
            rider.save()
            emailer.assert_called_once()

            rider.refresh_from_db()
            rider.save()
            emailer.assert_called_once()


class DeliveryOTPFormTests(TestCase):
    def test_digits_only(self):
        self.assertFalse(DeliveryOTPForm({'otp': '12ab'}).is_valid())
        self.assertFalse(DeliveryOTPForm({'otp': '123'}).is_valid())
        self.assertTrue(DeliveryOTPForm({'otp': '1234'}).is_valid())
        self.assertTrue(DeliveryOTPForm({'otp': '123456'}).is_valid())
