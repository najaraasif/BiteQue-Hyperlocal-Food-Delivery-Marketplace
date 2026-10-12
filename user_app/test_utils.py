from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from .utils import REQUEST_TIMEOUT_SECONDS, send_sms, send_whatsapp


class SendSmsTests(SimpleTestCase):
    def post_response(self, status_code=200):
        resp = mock.MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {'return': True}
        return resp

    def test_posts_to_configured_fast2sms_url(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_sms('9876543210', 'Hello')
            post.assert_called_once()
            self.assertEqual(post.call_args[0][0], settings.FAST2SMS_URL)

    def test_uses_request_timeout_constant(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_sms('9876543210', 'Hello')
            self.assertEqual(post.call_args[1]['timeout'], REQUEST_TIMEOUT_SECONDS)
            self.assertEqual(REQUEST_TIMEOUT_SECONDS, 15)

    def test_payload_contains_route_and_recipient(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_sms('9876543210', 'Order shipped')
            payload = post.call_args[1]['data']
            self.assertEqual(payload['route'], 'v3')
            self.assertEqual(payload['numbers'], '9876543210')
            self.assertEqual(payload['message'], 'Order shipped')
            self.assertEqual(payload['language'], 'english')
            self.assertEqual(payload['sender_id'], settings.WHATSAPP_SENDER_ID)

    def test_headers_carry_api_key_and_form_content_type(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_sms('9876543210', 'Hello')
            headers = post.call_args[1]['headers']
            self.assertEqual(headers['Authorization'], settings.FAST2SMS_API_KEY)
            self.assertEqual(headers['Content-Type'], 'application/x-www-form-urlencoded')
            self.assertEqual(headers['Cache-Control'], 'no-cache')

    def test_returns_true_on_http_200(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response(200)):
            self.assertTrue(send_sms('9876543210', 'Hello'))

    def test_returns_false_on_non_200(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response(503)):
            self.assertFalse(send_sms('9876543210', 'Hello'))

    def test_returns_false_and_logs_when_request_raises(self):
        with mock.patch('user_app.utils.requests.post', side_effect=RuntimeError('network down')):
            with self.assertLogs('user_app.utils', level='ERROR') as logs:
                result = send_sms('9876543210', 'Hello')
            self.assertFalse(result)
            self.assertIn('network down', logs.output[0])

    def test_does_not_raise_when_response_json_is_broken(self):
        resp = self.post_response(200)
        resp.json.side_effect = ValueError('bad json')
        with mock.patch('user_app.utils.requests.post', return_value=resp):
            with self.assertLogs('user_app.utils', level='ERROR'):
                result = send_sms('9876543210', 'Hello')
            self.assertFalse(result)


class SendWhatsappTests(SimpleTestCase):
    WHATTAPP_URL = 'https://www.fast2sms.com/dev/whatsapp'

    def post_response(self, status_code=200):
        resp = mock.MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {'return': True}
        return resp

    def test_posts_to_whatsapp_endpoint(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_whatsapp('919876543210', 'Hi')
            post.assert_called_once()
            self.assertEqual(post.call_args[0][0], self.WHATTAPP_URL)

    def test_payload_route_is_whatsapp_with_91_number(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_whatsapp('919876543210', 'Hi')
            payload = post.call_args[1]['json']
            self.assertEqual(payload['route'], 'whatsapp')
            self.assertEqual(payload['numbers'], '919876543210')
            self.assertEqual(payload['message'], 'Hi')
            self.assertEqual(payload['language'], 'english')
            self.assertEqual(payload['sender_id'], settings.WHATSAPP_SENDER_ID)

    def test_headers_use_json_content_type_and_api_key(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_whatsapp('919876543210', 'Hi')
            headers = post.call_args[1]['headers']
            self.assertEqual(headers['Authorization'], settings.FAST2SMS_API_KEY)
            self.assertEqual(headers['Content-Type'], 'application/json')

    def test_uses_shared_timeout_constant(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response()) as post:
            send_whatsapp('919876543210', 'Hi')
            self.assertEqual(post.call_args[1]['timeout'], REQUEST_TIMEOUT_SECONDS)

    def test_returns_true_on_http_200(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response(200)):
            self.assertTrue(send_whatsapp('919876543210', 'Hi'))

    def test_returns_false_on_http_403(self):
        with mock.patch('user_app.utils.requests.post', return_value=self.post_response(403)):
            self.assertFalse(send_whatsapp('919876543210', 'Hi'))

    def test_returns_false_and_logs_on_exception(self):
        with mock.patch('user_app.utils.requests.post', side_effect=RuntimeError('blocked')):
            with self.assertLogs('user_app.utils', level='ERROR') as logs:
                result = send_whatsapp('919876543210', 'Hi')
            self.assertFalse(result)
            self.assertIn('blocked', logs.output[0])
