from decimal import Decimal
from unittest import mock

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Restaurant
from .signals import (
    send_mailersend_reset_email,
    send_merchant_restaurant_email,
    send_merchant_verification_email,
)

NEW_EMAIL = 'merchant_app.signals.emails.NewEmail'


def make_registration(username='signal_merchant'):
    user = User.objects.create_user(
        username=username, password='pw12345678',
        email=f'{username}@example.com',
    )
    from .models import merchantRegistration
    return merchantRegistration.objects.create(
        username=user, name='Signal Merchant',
        number=Decimal('9876543210.0'),
    )


def make_restaurant(owner, name='Signal Kitchen'):
    return Restaurant.objects.create(
        owner=owner,
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Main Road',
        city='Testville',
    )


class MerchantVerificationEmailTests(TestCase):
    def test_sends_to_registered_email_with_login_link(self):
        registration = make_registration()
        with mock.patch(NEW_EMAIL) as email_cls:
            send_merchant_verification_email(registration)

        email_cls.assert_called_once_with(settings.MAILERSEND_API_KEY)
        mailer = email_cls.return_value
        mailer.send.assert_called_once()
        payload = mailer.send.call_args[0][0]
        self.assertEqual(payload['subject'], 'Your Merchant Account is Approved')
        self.assertEqual(
            payload['to'], [{'email': registration.username.email}]
        )
        self.assertEqual(payload['from']['name'], 'BiteQue')
        self.assertIn('Hello Signal Merchant', payload['text'])
        self.assertIn('approved', payload['html'])
        self.assertIn(
            f'{settings.SITE_URL}/merchant-login/', payload['html']
        )

    def test_send_failure_is_logged_and_swallowed(self):
        registration = make_registration('signal_failing')
        with mock.patch(NEW_EMAIL) as email_cls:
            email_cls.return_value.send.side_effect = RuntimeError('down')
            with self.assertLogs('merchant_app.signals', 'WARNING') as logs:
                send_merchant_verification_email(registration)
        self.assertTrue(any(
            'Merchant verification e-mail' in line for line in logs.output
        ))


class RestaurantApprovalEmailTests(TestCase):
    def test_sends_to_restaurant_email_with_restaurant_name(self):
        owner = User.objects.create_user(
            username='signal_owner', password='pw12345678',
            email='signal_owner@example.com',
        )
        restaurant = make_restaurant(owner, name='Approval Kitchen')
        with mock.patch(NEW_EMAIL) as email_cls:
            send_merchant_restaurant_email(restaurant)

        mailer = email_cls.return_value
        mailer.send.assert_called_once()
        payload = mailer.send.call_args[0][0]
        self.assertEqual(payload['to'], [{'email': restaurant.email}])
        self.assertEqual(payload['subject'], 'Your Merchant Account is Approved')
        self.assertIn('Approval Kitchen', payload['html'])
        self.assertIn(
            f'{settings.SITE_URL}/merchant-login/', payload['html']
        )
        self.assertIn('signal_owner', payload['text'])

    def test_send_failure_is_logged_and_swallowed(self):
        owner = User.objects.create_user(
            username='signal_owner2', password='pw12345678',
            email='signal_owner2@example.com',
        )
        restaurant = make_restaurant(owner, name='Failing Kitchen')
        with mock.patch(NEW_EMAIL) as email_cls:
            email_cls.return_value.send.side_effect = RuntimeError('down')
            with self.assertLogs('merchant_app.signals', 'WARNING') as logs:
                send_merchant_restaurant_email(restaurant)
        self.assertTrue(any(
            'Restaurant approval e-mail' in line for line in logs.output
        ))


class MailerSendResetEmailTests(TestCase):
    def test_posts_reset_link_to_mailersend_api(self):
        with mock.patch('merchant_app.signals.requests.post') as post:
            post.return_value.raise_for_status.return_value = None
            result = send_mailersend_reset_email(
                'reset@example.com', 'https://site.example/reset/uid/token/'
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
        payload = kwargs['json']
        self.assertEqual(payload['to'], [{'email': 'reset@example.com'}])
        self.assertEqual(
            payload['subject'], 'Reset your Merchant App password'
        )
        self.assertIn(
            'https://site.example/reset/uid/token/', payload['html']
        )
        self.assertEqual(kwargs['timeout'], 15)

    def test_network_failure_returns_false_and_logs(self):
        with mock.patch('merchant_app.signals.requests.post') as post:
            post.side_effect = requests.ConnectionError('no route')
            with self.assertLogs('merchant_app.signals', 'WARNING') as logs:
                result = send_mailersend_reset_email(
                    'reset@example.com', 'https://site.example/reset/'
                )

        self.assertFalse(result)
        self.assertTrue(any(
            'password-reset' in line for line in logs.output
        ))

    def test_http_error_status_returns_false(self):
        with mock.patch('merchant_app.signals.requests.post') as post:
            post.return_value.raise_for_status.side_effect = (
                requests.HTTPError('500')
            )
            result = send_mailersend_reset_email(
                'reset@example.com', 'https://site.example/reset/'
            )
        self.assertFalse(result)
