from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from .utils import REQUEST_TIMEOUT_SECONDS, send_sms, send_whatsapp


def fake_response(status=200, payload=None):
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = payload if payload is not None else {
        'return': True,
    }
    return response


class SendSmsTests(SimpleTestCase):
    @mock.patch('user_app.utils.requests.post')
    def test_success_returns_true_with_expected_request(self, post):
        post.return_value = fake_response()

        result = send_sms('9876543210', 'Your OTP is 4412')

        self.assertTrue(result)
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], settings.FAST2SMS_URL)
        self.assertEqual(kwargs['timeout'], REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(
            kwargs['headers']['Authorization'], settings.FAST2SMS_API_KEY
        )
        self.assertEqual(
            kwargs['headers']['Content-Type'],
            'application/x-www-form-urlencoded',
        )
        payload = kwargs['data']
        self.assertEqual(payload['numbers'], '9876543210')
        self.assertEqual(payload['message'], 'Your OTP is 4412')
        self.assertEqual(payload['route'], 'v3')
        self.assertEqual(payload['language'], 'english')
        self.assertEqual(payload['sender_id'], settings.WHATSAPP_SENDER_ID)

    @mock.patch('user_app.utils.requests.post')
    def test_non_200_response_returns_false(self, post):
        post.return_value = fake_response(status=503)
        self.assertFalse(send_sms('9876543210', 'hello'))

    @mock.patch('user_app.utils.requests.post')
    def test_transport_exception_returns_false(self, post):
        post.side_effect = RuntimeError('network down')
        self.assertFalse(send_sms('9876543210', 'hello'))

    @mock.patch('user_app.utils.requests.post')
    def test_unreadable_success_body_returns_false(self, post):
        response = fake_response()
        response.json.side_effect = ValueError('bad json')
        post.return_value = response
        self.assertFalse(send_sms('9876543210', 'hello'))

    def test_request_timeout_is_fixed(self):
        self.assertEqual(REQUEST_TIMEOUT_SECONDS, 15)


class SendWhatsappTests(SimpleTestCase):
    @mock.patch('user_app.utils.requests.post')
    def test_success_returns_true_with_expected_request(self, post):
        post.return_value = fake_response()

        result = send_whatsapp('9876543210', 'Order is out for delivery')

        self.assertTrue(result)
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://www.fast2sms.com/dev/whatsapp')
        self.assertEqual(kwargs['timeout'], REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(
            kwargs['headers']['Authorization'], settings.FAST2SMS_API_KEY
        )
        self.assertEqual(
            kwargs['headers']['Content-Type'], 'application/json'
        )
        payload = kwargs['json']
        self.assertEqual(payload['route'], 'whatsapp')
        self.assertEqual(payload['numbers'], '9876543210')
        self.assertEqual(payload['message'], 'Order is out for delivery')
        self.assertEqual(payload['language'], 'english')
        self.assertEqual(payload['sender_id'], settings.WHATSAPP_SENDER_ID)

    @mock.patch('user_app.utils.requests.post')
    def test_non_200_response_returns_false(self, post):
        post.return_value = fake_response(status=403)
        self.assertFalse(send_whatsapp('9876543210', 'hello'))

    @mock.patch('user_app.utils.requests.post')
    def test_transport_exception_returns_false(self, post):
        post.side_effect = RuntimeError('boom')
        self.assertFalse(send_whatsapp('9876543210', 'hello'))


class SmsHelperFromModelLayerTests(TestCase):
    def test_order_save_path_can_use_empty_contact_without_sms(self):
        from django.contrib.auth.models import User
        from user_app.models import Order
        from merchant_app.models import Restaurant

        owner = User.objects.create_user(
            username='sms_owner', password='pw12345678'
        )
        restaurant = Restaurant.objects.create(
            owner=owner, name='SMS Rest',
            email='sms_rest@example.com', contact_number='9876543210',
            address='1 Road', city='Town',
        )
        user = User.objects.create_user(
            username='sms_customer', password='pw12345678'
        )
        with mock.patch('user_app.utils.requests.post') as post:
            order = Order.objects.create(
                user=user, restaurant=restaurant,
                customer_name='SMS Customer', customer_contact='',
                landmark='', delivery_address='1 Road',
                special_instructions='',
            )
            post.assert_not_called()
        self.assertIsNotNone(order.pk)
