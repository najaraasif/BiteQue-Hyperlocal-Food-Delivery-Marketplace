from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .models import merchantRegistration


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class MerchantStaticPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='small_owner', password='pw12345678'
        )
        merchantRegistration.objects.create(
            username=self.owner,
            name='Small Owner',
            number=Decimal('9876543210.0'),
            is_approved=False,
        )
        self.client.force_login(self.owner)

    def test_awaiting_approval_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('awaiting-approval'))
        self.assertEqual(resp.status_code, 302)

    def test_awaiting_approval_renders_for_merchant(self):
        resp = self.client.get(reverse('awaiting-approval'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'awaitingApproval.html')

    def test_restaurant_success_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('restaurant_success'))
        self.assertEqual(resp.status_code, 302)

    def test_restaurant_success_renders_for_merchant(self):
        resp = self.client.get(reverse('restaurant_success'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'restaurant_success.html')

    def test_merchant_logout_get_is_method_not_allowed(self):
        resp = self.client.get(reverse('merchant_logout'))
        self.assertEqual(resp.status_code, 405)

    def test_merchant_logout_post_ends_the_session(self):
        resp = self.client.post(reverse('merchant_logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_anonymous_logout_still_redirects(self):
        self.client.logout()
        resp = self.client.post(reverse('merchant_logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_login'))


class MerchantPasswordResetRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset_small', email='reset_small@example.com',
            password='pw12345678',
        )
        self.url = reverse('merchant-password-reset')

    def test_get_renders_reset_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'password_reset_form.html')

    def test_known_email_sends_link_and_redirects(self):
        with mock.patch(
            'merchant_app.views.send_mailersend_reset_email'
        ) as sender:
            resp = self.client.post(self.url, {'email': self.user.email})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('password_reset_sent'))
        sender.assert_called_once()
        sent_to, link = sender.call_args.args
        self.assertEqual(sent_to, self.user.email)
        self.assertIn('/merchant/reset/', link)
        from django.utils.http import urlsafe_base64_decode
        tail = link.split('/merchant/reset/', 1)[1]
        uid, token = tail.rstrip('/').split('/', 1)
        self.assertEqual(
            int(urlsafe_base64_decode(uid).decode()), self.user.pk
        )
        self.assertTrue(token)
        self.assertTrue(any(
            'If an account exists for this email' in m
            for m in messages_of(resp)
        ))

    def test_unknown_email_gets_the_same_response_without_a_send(self):
        with mock.patch(
            'merchant_app.views.send_mailersend_reset_email'
        ) as sender:
            resp = self.client.post(self.url, {'email': 'nobody@example.com'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('password_reset_sent'))
        sender.assert_not_called()
        unknown_message = messages_of(resp)

        self.client.cookies.clear()
        with mock.patch(
            'merchant_app.views.send_mailersend_reset_email'
        ):
            known = self.client.post(self.url, {'email': self.user.email})
        self.assertEqual(messages_of(known), unknown_message)

    def test_missing_email_field_is_treated_like_unknown(self):
        with mock.patch(
            'merchant_app.views.send_mailersend_reset_email'
        ) as sender:
            resp = self.client.post(self.url, {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('password_reset_sent'))
        sender.assert_not_called()

    def test_get_request_does_not_send_anything(self):
        with mock.patch(
            'merchant_app.views.send_mailersend_reset_email'
        ) as sender:
            self.client.get(self.url)
        sender.assert_not_called()
