import sys
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.test import SimpleTestCase, TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from sib_api_v3_sdk.rest import ApiException

from rider_app.brevo_helper import send_brevo_email
from rider_app.views import RiderPasswordResetView


def argv_for(command):
    return ['manage.py', command, 'placeholder']


class BrevoHelperTests(SimpleTestCase):
    def send(self, **overrides):
        payload = dict(
            subject='Hello there',
            html_content='<p>Hi</p>',
            recipient_email='rider@example.com',
            recipient_name='rider1',
        )
        payload.update(overrides)
        return send_brevo_email(**payload)

    def test_short_circuits_when_manage_py_runs_tests(self):
        with mock.patch.object(
            sys, 'argv', ['manage.py', 'test', 'rider_app']
        ), mock.patch('sib_api_v3_sdk.Configuration') as configuration_cls:
            result = self.send()
        self.assertIsNone(result)
        configuration_cls.assert_not_called()

    def test_builds_and_sends_the_transactional_email(self):
        smtp_payload = mock.sentinel.smtp_payload
        api_response = mock.sentinel.api_response
        api_instance = mock.MagicMock()
        api_instance.send_transac_email.return_value = api_response

        with mock.patch.object(
            sys, 'argv', argv_for('runserver')
        ), mock.patch(
            'sib_api_v3_sdk.Configuration'
        ) as configuration_cls, mock.patch(
            'sib_api_v3_sdk.ApiClient'
        ), mock.patch(
            'sib_api_v3_sdk.TransactionalEmailsApi',
            return_value=api_instance,
        ), mock.patch(
            'sib_api_v3_sdk.SendSmtpEmail', return_value=smtp_payload
        ) as payload_cls:
            result = self.send(
                subject='Order shipped',
                html_content='<b>packed</b>',
                recipient_email='rider@example.com',
                recipient_name='Rider One',
            )

        configuration_cls.return_value.api_key.__setitem__.assert_called_with(
            'api-key', settings.BREVO_API_KEY
        )
        payload_cls.assert_called_once_with(
            sender={
                'name': 'ZemQue Support',
                'email': settings.DEFAULT_FROM_EMAIL,
            },
            to=[{'email': 'rider@example.com', 'name': 'Rider One'}],
            html_content='<b>packed</b>',
            subject='Order shipped',
        )
        api_instance.send_transac_email.assert_called_once_with(smtp_payload)
        self.assertIs(result, api_response)

    def test_api_exception_is_logged_and_returns_none(self):
        api_instance = mock.MagicMock()
        api_instance.send_transac_email.side_effect = ApiException(
            status=500, reason='boom'
        )

        with mock.patch.object(
            sys, 'argv', argv_for('runserver')
        ), mock.patch('sib_api_v3_sdk.Configuration'), mock.patch(
            'sib_api_v3_sdk.ApiClient'
        ), mock.patch(
            'sib_api_v3_sdk.TransactionalEmailsApi',
            return_value=api_instance,
        ), mock.patch('sib_api_v3_sdk.SendSmtpEmail'), self.assertLogs(
            'rider_app.brevo_helper', level='WARNING'
        ) as logs:
            result = self.send(recipient_email='late@example.com')

        self.assertIsNone(result)
        self.assertTrue(
            any('late@example.com' in entry for entry in logs.output)
        )

    def test_unexpected_exception_propagates(self):
        api_instance = mock.MagicMock()
        api_instance.send_transac_email.side_effect = RuntimeError('net down')

        with mock.patch.object(
            sys, 'argv', argv_for('runserver')
        ), mock.patch('sib_api_v3_sdk.Configuration'), mock.patch(
            'sib_api_v3_sdk.ApiClient'
        ), mock.patch(
            'sib_api_v3_sdk.TransactionalEmailsApi',
            return_value=api_instance,
        ), mock.patch('sib_api_v3_sdk.SendSmtpEmail'):
            with self.assertRaises(RuntimeError):
                self.send()


class RiderPasswordResetMailDispatchTests(TestCase):
    def build_context(self, user):
        return {
            'user': user,
            'protocol': 'https',
            'uid': urlsafe_base64_encode(force_bytes(user.pk)).rstrip('='),
            'token': default_token_generator.make_token(user),
            'domain': 'testserver',
            'site_name': 'BiteQue',
        }

    def test_send_mail_renders_templates_and_calls_brevo(self):
        user = User.objects.create_user(
            username='mail_rider',
            password='pw12345678',
            email='mail_rider@example.com',
        )
        view = RiderPasswordResetView()

        with mock.patch(
            'rider_app.views.send_brevo_email'
        ) as sender:
            view.send_mail(
                subject_template_name='rider_app/password_reset_subject.txt',
                email_template_name='rider_app/password_reset_email.html',
                context=self.build_context(user),
                from_email='no-reply@biteque.example',
                to_email=[user.email],
            )

        sender.assert_called_once()
        kwargs = sender.call_args.kwargs
        self.assertEqual(kwargs['subject'], 'Password Reset Request')
        self.assertEqual(kwargs['recipient_email'], 'mail_rider@example.com')
        self.assertEqual(kwargs['recipient_name'], 'mail_rider')
        self.assertIn('mail_rider', kwargs['html_content'])
        self.assertIn('password-reset-confirm', kwargs['html_content'])

    def test_rendered_subject_collapses_template_newlines(self):
        user = User.objects.create_user(
            username='newline_rider',
            password='pw12345678',
            email='newline_rider@example.com',
        )
        view = RiderPasswordResetView()

        with mock.patch(
            'rider_app.views.send_brevo_email'
        ) as sender:
            view.send_mail(
                subject_template_name='rider_app/password_reset_subject.txt',
                email_template_name='rider_app/password_reset_email.html',
                context=self.build_context(user),
                from_email='no-reply@biteque.example',
                to_email=[user.email],
            )

        subject = sender.call_args.kwargs['subject']
        self.assertEqual(subject, 'Password Reset Request')
        self.assertNotIn('\n', subject)
