from unittest import mock

import requests as requests_lib
from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Restaurant, merchantRegistration
from .signals import (
    send_mailersend_reset_email,
    send_merchant_restaurant_email,
    send_merchant_verification_email,
)


class MerchantVerificationEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='verify_owner', email='verify_owner@example.com',
            password='pw12345678',
        )
        self.merchant = merchantRegistration.objects.create(
            username=self.user, name='Verify Owner',
            number='9876543210.0', is_approved=True,
        )

    @mock.patch('merchant_app.signals.emails.NewEmail')
    def test_approval_email_targets_the_merchant_login_link(self, new_email):
        mailer = new_email.return_value

        send_merchant_verification_email(self.merchant)

        new_email.assert_called_once_with(settings.MAILERSEND_API_KEY)
        mailer.send.assert_called_once()
        payload = mailer.send.call_args.args[0]
        self.assertEqual(
            payload['to'], [{'email': 'verify_owner@example.com'}]
        )
        self.assertEqual(payload['subject'], 'Your Merchant Account is Approved')
        self.assertEqual(payload['from']['email'], settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(payload['from']['name'], 'BiteQue')
        self.assertIn('Verify Owner', payload['text'])
        self.assertIn('approved', payload['text'])
        self.assertIn(settings.SITE_URL, payload['html'])
        self.assertIn(reverse('merchant_login'), payload['html'])
        self.assertIn('<html>', payload['html'])

    @mock.patch('merchant_app.signals.emails.NewEmail')
    def test_transport_failure_is_swallowed(self, new_email):
        new_email.return_value.send.side_effect = RuntimeError('smtp down')
        send_merchant_verification_email(self.merchant)


class MerchantRestaurantEmailTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='rest_owner', email='rest_owner@example.com',
            password='pw12345678',
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Approved Kitchen',
            email='kitchen@example.com', contact_number='9876543210',
            address='1 Road', city='Town',
        )

    @mock.patch('merchant_app.signals.emails.NewEmail')
    def test_restaurant_approval_email_targets_restaurant_address(
        self, new_email
    ):
        mailer = new_email.return_value

        send_merchant_restaurant_email(self.restaurant)

        new_email.assert_called_once_with(settings.MAILERSEND_API_KEY)
        mailer.send.assert_called_once()
        payload = mailer.send.call_args.args[0]
        self.assertEqual(payload['to'], [{'email': 'kitchen@example.com'}])
        self.assertIn('rest_owner', payload['text'])
        self.assertIn('approved', payload['text'])
        self.assertIn('Approved Kitchen', payload['html'])
        self.assertIn(settings.SITE_URL, payload['html'])
        self.assertIn(reverse('merchant_login'), payload['html'])

    @mock.patch('merchant_app.signals.emails.NewEmail')
    def test_failure_is_swallowed(self, new_email):
        new_email.return_value.send.side_effect = RuntimeError('down')
        send_merchant_restaurant_email(self.restaurant)


class MailerSendResetEmailTests(SimpleTestCase):
    @mock.patch('merchant_app.signals.requests.post')
    def test_posts_bearer_token_and_reset_link(self, post):
        post.return_value.raise_for_status.return_value = None

        result = send_mailersend_reset_email(
            'merchant@example.com', 'https://shop.test/merchant/reset/uid/tok/'
        )

        self.assertTrue(result)
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://api.mailersend.com/v1/email')
        self.assertEqual(
            kwargs['headers']['Authorization'],
            f'Bearer {settings.MAILERSEND_API_KEY}',
        )
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')
        self.assertEqual(kwargs['timeout'], 15)
        data = kwargs['json']
        self.assertEqual(data['to'], [{'email': 'merchant@example.com'}])
        self.assertEqual(
            data['subject'], 'Reset your Merchant App password'
        )
        self.assertEqual(
            data['from']['email'],
            f'no-reply@{settings.MAILERSEND_DOMAIN}',
        )
        self.assertEqual(data['from']['name'], 'Merchant App Support')
        self.assertIn(
            'https://shop.test/merchant/reset/uid/tok/', data['html']
        )

    @mock.patch('merchant_app.signals.requests.post')
    def test_http_error_status_returns_false(self, post):
        post.return_value.raise_for_status.side_effect = (
            requests_lib.HTTPError('400 Client Error')
        )
        self.assertFalse(
            send_mailersend_reset_email('a@example.com', 'http://x/')
        )

    @mock.patch('merchant_app.signals.requests.post')
    def test_transport_error_returns_false(self, post):
        post.side_effect = requests_lib.ConnectionError('offline')
        self.assertFalse(
            send_mailersend_reset_email('a@example.com', 'http://x/')
        )
