from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from rider_app.models import OrderAssignment, Rider
from user_app.models import Order

from .forms import MerchantRegistrationForm
from .models import Restaurant


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username, password='pw12345678', **kwargs
    )


class OrderAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = make_user('merchant_owner')
        self.customer = make_user('buyer1')
        self.stranger = make_user('stranger1')
        self.restaurant = Restaurant.objects.create(
            owner=self.owner,
            name='Auth Kitchen',
            email='auth@example.com',
            contact_number='9876543210',
            address='1 Main Road',
            city='Testville',
        )
        self.order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            customer_name='Buyer',
            customer_contact='',
            landmark='',
            delivery_address='1 Road',
            special_instructions='',
        )
        self.rider = Rider.objects.create(
            user=make_user('rider_auth'),
            phone='9876543210',
            gender='Male',
            aadhar_number='123456789012',
            driving_license='DL1234567890',
            address='1 Test Street',
            area='Test Area',
            pincode='123456',
            profile_photo='riders/profiles/p.jpg',
            aadhar_front='riders/aadhar/f.jpg',
            license_copy='riders/license/l.jpg',
            is_approved=True,
            is_available=True,
        )

    def test_confirm_requires_login(self):
        resp = self.client.get(
            reverse('confirm_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 302)

    def test_confirm_forbidden_for_non_owner(self):
        self.client.force_login(self.customer)
        resp = self.client.get(
            reverse('confirm_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_owner_can_confirm_pending_order(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse('confirm_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')

    def test_confirming_twice_does_not_crash(self):
        self.client.force_login(self.owner)
        self.client.get(reverse('confirm_order', args=[self.order.id]))
        resp = self.client.get(
            reverse('confirm_order', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')

    def test_ready_requires_confirmed_state(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse('mark_order_ready', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_ready_keeps_accepted_assignment_and_excludes_rider(self):
        other_rider = Rider.objects.create(
            user=make_user('rider_other'),
            phone='9876543211',
            gender='Female',
            aadhar_number='123456789013',
            driving_license='DL1234567891',
            address='2 Test Street',
            area='Test Area',
            pincode='123456',
            profile_photo='riders/profiles/p2.jpg',
            aadhar_front='riders/aadhar/f2.jpg',
            license_copy='riders/license/l2.jpg',
            is_approved=True,
            is_available=True,
        )
        self.order.status = 'confirmed'
        self.order.save()
        accepted = OrderAssignment.objects.create(
            order=self.order, rider=self.rider, status='pending'
        )
        OrderAssignment.objects.create(
            order=self.order, rider=other_rider, status='pending'
        )
        # Bypass the accept signal: a real "accepted" assignment implies
        # out_for_delivery, which would take the order out of the ready
        # path entirely. This exercises the view's exclude-accepted logic.
        OrderAssignment.objects.filter(pk=accepted.pk).update(
            status='accepted'
        )

        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse('mark_order_ready', args=[self.order.id])
        )
        self.assertEqual(resp.status_code, 302)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready')

        accepted.refresh_from_db()
        self.assertEqual(accepted.status, 'accepted')

        for rider in (self.rider, other_rider):
            assignments = OrderAssignment.objects.filter(
                order=self.order, rider=rider
            )
            self.assertEqual(assignments.count(), 1)

        self.assertEqual(
            OrderAssignment.objects.get(
                order=self.order, rider=other_rider
            ).status,
            'pending',
        )

    def test_export_orders_requires_login(self):
        resp = self.client.get(reverse('export_orders_pdf'))
        self.assertEqual(resp.status_code, 302)

    def test_export_payments_requires_login(self):
        resp = self.client.get(reverse('export_payments_pdf'))
        self.assertEqual(resp.status_code, 302)

    def test_export_orders_renders_for_owner(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('export_orders_pdf'))
        self.assertEqual(resp.status_code, 200)


class PasswordResetEnumerationTests(TestCase):
    def setUp(self):
        self.merchant = make_user(
            'reset_merchant', email='reset_merchant@example.com'
        )

    def post_reset(self, email):
        with mock.patch(
            'merchant_app.views.send_mailersend_reset_email'
        ) as sender:
            resp = self.client.post(
                reverse('merchant-password-reset'), {'email': email}
            )
        return resp, sender

    def test_unknown_and_known_email_get_identical_response(self):
        unknown_resp, unknown_sender = self.post_reset('nobody@example.com')
        known_resp, known_sender = self.post_reset('reset_merchant@example.com')

        self.assertEqual(unknown_resp.status_code, 302)
        self.assertEqual(known_resp.status_code, 302)
        self.assertEqual(unknown_resp['Location'], known_resp['Location'])
        unknown_sender.assert_not_called()
        known_sender.assert_called_once()

    def test_reset_page_renders(self):
        resp = self.client.get(reverse('merchant-password-reset'))
        self.assertEqual(resp.status_code, 200)


class MerchantPhoneValidationTests(TestCase):
    BASE = {
        'username': 'phone_user_1',
        'name': 'Phone User',
        'email': 'phone_user_1@example.com',
        'password': 'Abcdef1!',
        'retypePassword': 'Abcdef1!',
    }

    def form(self, number):
        data = dict(self.BASE, number=number)
        return MerchantRegistrationForm(data=data)

    def test_ten_digit_local_number(self):
        form = self.form('9876543210')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_nine_one_prefix_normalized(self):
        form = self.form('919876543210')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_plus_country_code_normalized(self):
        form = self.form('+919876543210')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_number_starting_with_one_rejected(self):
        form = self.form('1234567890')
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)

    def test_short_number_rejected(self):
        form = self.form('987654321')
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)
