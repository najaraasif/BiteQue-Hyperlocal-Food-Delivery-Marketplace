import hashlib
import hmac
import os
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory
from rider_app.models import Rider

from .models import Order, OrderMenuItem

PROBE_FILES = (
    'menu_images/_ut_probe.jpg',
    'riders/aadhar/_ut_probe.jpg',
    'avatars/_ut_probe.jpg',
)


def setUpModule():
    for rel in PROBE_FILES:
        abs_path = os.path.join(settings.MEDIA_ROOT, rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'wb') as fh:
            fh.write(b'probe')


def tearDownModule():
    for rel in PROBE_FILES:
        abs_path = os.path.join(settings.MEDIA_ROOT, rel)
        try:
            os.remove(abs_path)
        except OSError:
            pass


def close_response(resp):
    stream = getattr(resp, 'streaming', False)
    if stream:
        for _ in resp:
            pass
    if hasattr(resp, 'close'):
        resp.close()


def make_restaurant(name='Fee Kitchen', lat=None, lon=None):
    owner = User.objects.create_user(
        username=f'own_{name}', password='pw12345678',
        email=f'{name}@example.com'.replace(' ', '').lower(),
    )
    return Restaurant.objects.create(
        owner=owner,
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Main Road',
        city='Testville',
        lat=lat,
        lon=lon,
    )


def make_menu_item(restaurant, price='100.00'):
    size, _ = SizeCategory.objects.get_or_create(
        name=f'Regular {restaurant.name}'
    )
    return RestaurantMenu.objects.create(
        restaurant=restaurant,
        name='Test Burger',
        category='Burgers',
        price=Decimal(price),
        prep_time=10,
        sizes_categories=size,
    )


class CheckoutFeeTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='buyer', password='pw12345678'
        )
        self.client.force_login(self.customer)
        self.restaurant = make_restaurant('NoGeo Kitchen')
        self.item = make_menu_item(self.restaurant)

        session = self.client.session
        session['cart'] = {str(self.item.id): {'quantity': 2}}
        session.save()

    def post_checkout(self, distance_km, tampered_fee='9999'):
        with mock.patch('user_app.views.razorpay.Client') as client_cls:
            client_cls.return_value.order.create.return_value = {
                'id': 'order_mock_1'
            }
            resp = self.client.post(
                reverse('checkout'),
                {
                    'create_order': '1',
                    'customer_name': 'Buyer',
                    'contact_number': '',
                    'delivery_address': '1 Delivery Road',
                    'landmark': 'Near park',
                    'special_instructions': '',
                    'dest_lat': '',
                    'dest_lon': '',
                    'calculated_distance_km': distance_km,
                    'calculated_delivery_fee': tampered_fee,
                },
            )
            created = client_cls.return_value.order.create
        return resp, created

    def test_fee_is_server_derived_posted_fee_ignored(self):
        resp, _ = self.post_checkout('5')
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['success'])

        order = Order.objects.get()
        # restaurant has no coordinates -> posted distance is the fallback,
        # fee = distance * 10, tampered posted fee (9999) must be ignored.
        self.assertEqual(order.distance_km, Decimal('5.00'))
        self.assertEqual(order.distance_earning, Decimal('50.00'))
        # 200 subtotal + 6 gst + 10 packaging + 50 fee
        self.assertEqual(order.final_total, Decimal('266.00'))
        self.assertEqual(
            Order.objects.filter(status='pending').count(), 1
        )

    def test_razorpay_amount_matches_server_total(self):
        resp, created = self.post_checkout('5')
        self.assertTrue(resp.json()['success'])
        self.assertEqual(created.call_args[0][0]['amount'], 26600)

    def test_distance_clamped_to_50km(self):
        resp, _ = self.post_checkout('999')
        self.assertTrue(resp.json()['success'])
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('50.00'))
        self.assertEqual(order.distance_earning, Decimal('500.00'))
        self.assertEqual(order.final_total, Decimal('716.00'))

    def test_negative_distance_clamped_to_zero(self):
        resp, _ = self.post_checkout('-5')
        self.assertTrue(resp.json()['success'])
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('0.00'))
        self.assertEqual(order.distance_earning, Decimal('0.00'))
        self.assertEqual(order.final_total, Decimal('216.00'))

    def test_garbage_distance_treated_as_zero(self):
        resp, _ = self.post_checkout('not-a-number')
        self.assertTrue(resp.json()['success'])
        order = Order.objects.get()
        self.assertEqual(order.distance_earning, Decimal('0.00'))

    def test_checkout_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('checkout'))
        self.assertEqual(resp.status_code, 302)

    def test_empty_cart_redirects_home(self):
        session = self.client.session
        session['cart'] = {}
        session.save()
        resp = self.client.get(reverse('checkout'))
        self.assertEqual(resp.status_code, 302)


class CalculateTotalTests(TestCase):
    def test_total_is_quantity_aware(self):
        restaurant = make_restaurant('Qty Kitchen')
        item_a = make_menu_item(restaurant, price='50.00')
        item_b = make_menu_item(restaurant, price='20.00')
        order = Order.objects.create(
            user=User.objects.create_user(
                username='qtybuyer', password='pw12345678'
            ),
            restaurant=restaurant,
            customer_name='Qty',
            customer_contact='',
            landmark='',
            delivery_address='1 Road',
            special_instructions='',
        )
        OrderMenuItem.objects.create(
            order=order, menu_item=item_a, quantity=3, price=item_a.price
        )
        OrderMenuItem.objects.create(
            order=order, menu_item=item_b, quantity=2, price=item_b.price
        )
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal('190.00'))


class MediaAuthTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_public_menu_image_served_anonymously(self):
        resp = self.client.get('/media/menu_images/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 200)
        close_response(resp)

    def test_kyc_blocked_for_anonymous(self):
        resp = self.client.get('/media/riders/aadhar/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 404)

    def test_avatar_blocked_for_anonymous(self):
        resp = self.client.get('/media/avatars/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 404)

    def test_avatar_served_to_any_authenticated_user(self):
        stranger = User.objects.create_user(
            username='media_stranger', password='pw12345678'
        )
        self.client.force_login(stranger)
        resp = self.client.get('/media/avatars/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 200)
        close_response(resp)

    def test_kyc_blocked_for_non_owner(self):
        stranger = User.objects.create_user(
            username='media_other', password='pw12345678'
        )
        self.client.force_login(stranger)
        resp = self.client.get('/media/riders/aadhar/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 404)

    def test_kyc_served_to_owning_rider(self):
        owner_user = User.objects.create_user(
            username='media_rider', password='pw12345678'
        )
        Rider.objects.create(
            user=owner_user,
            phone='9876543210',
            gender='Male',
            aadhar_number='123456789012',
            driving_license='DL1234567890',
            address='1 Test Street',
            area='Test Area',
            pincode='123456',
            profile_photo='riders/profiles/p.jpg',
            aadhar_front='riders/aadhar/_ut_probe.jpg',
            license_copy='riders/license/l.jpg',
        )
        self.client.force_login(owner_user)
        resp = self.client.get('/media/riders/aadhar/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 200)
        close_response(resp)

    def test_kyc_served_to_staff(self):
        staff = User.objects.create_user(
            username='media_staff', password='pw12345678', is_staff=True
        )
        self.client.force_login(staff)
        resp = self.client.get('/media/riders/aadhar/_ut_probe.jpg')
        self.assertEqual(resp.status_code, 200)
        close_response(resp)

    def test_path_traversal_rejected(self):
        resp = self.client.get('/media/../BITEQUE/urls.py')
        self.assertEqual(resp.status_code, 404)


PAYMENT_FETCH = 'razorpay.resources.payment.Payment.fetch'


class PaymentConfirmationTests(TestCase):
    """payment_success must never trust the browser: the Razorpay
    signature, the payment/order linkage and the charged amount and
    currency all have to check out server-side before is_paid flips."""

    ORDER_ID = 'order_TESTORDERXYZ'
    OTHER_ORDER_ID = 'order_OTHERORDERXYZ'
    PAYMENT_ID = 'pay_TESTPAYMENTXYZ'

    def setUp(self):
        self.customer = User.objects.create_user(
            username='paybuyer', password='pw12345678'
        )
        self.restaurant = make_restaurant('Pay Kitchen')
        self.order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            customer_name='Pay Buyer',
            customer_contact='9876543210',
            landmark='',
            delivery_address='1 Road',
            special_instructions='',
            final_total=Decimal('266.00'),
            razorpay_order_id=self.ORDER_ID,
        )
        # Order.save() recomputes final_total from its parts, so pin the
        # server-created amount explicitly (the checkout flow does this
        # through the real pricing pipeline).
        Order.objects.filter(pk=self.order.pk).update(
            final_total=Decimal('266.00')
        )
        self.order.refresh_from_db()

    def sign(self, order_id, payment_id, secret=None):
        secret = secret or settings.RAZORPAY_KEY_SECRET
        message = f'{order_id}|{payment_id}'.encode()
        return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    def post_confirmation(self, order_id=None, payment_id=None,
                          signature=None, **extra):
        order_id = order_id if order_id is not None else self.ORDER_ID
        payment_id = payment_id if payment_id is not None else self.PAYMENT_ID
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature if signature is not None
            else self.sign(order_id, payment_id),
        }
        payload.update(extra)
        return self.client.post(reverse('payment_success'), payload)

    @staticmethod
    def fetched_payment(**overrides):
        data = {
            'id': PaymentConfirmationTests.PAYMENT_ID,
            'order_id': PaymentConfirmationTests.ORDER_ID,
            'amount': 26600,
            'currency': 'INR',
            'status': 'captured',
        }
        data.update(overrides)
        return data

    def assert_unpaid(self):
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)
        self.assertIsNone(self.order.razorpay_payment_id)
        self.assertIsNone(self.order.razorpay_signature)

    def test_valid_payment_marks_paid_and_clears_cart(self):
        session = self.client.session
        session['cart'] = {'999': {'quantity': 1}}
        session.save()

        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = self.fetched_payment()
            resp = self.post_confirmation()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, reverse('order_confirmation', args=[self.order.id])
        )
        fetch.assert_called_once_with(self.PAYMENT_ID)

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.razorpay_payment_id, self.PAYMENT_ID)
        self.assertEqual(
            self.order.razorpay_signature,
            self.sign(self.ORDER_ID, self.PAYMENT_ID),
        )
        self.assertNotIn('cart', self.client.session)

    def test_tampered_amount_rejected(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = self.fetched_payment(amount=100)
            resp = self.post_confirmation()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        fetch.assert_called_once()
        self.assert_unpaid()

    def test_wrong_order_relationship_rejected(self):
        # Payment is bound to a different Razorpay order than ours.
        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = self.fetched_payment(
                order_id=self.OTHER_ORDER_ID
            )
            resp = self.post_confirmation()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assert_unpaid()

    def test_unknown_razorpay_order_rejected_without_fetch(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            resp = self.post_confirmation(order_id='order_NO_SUCH_ORDER')

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        fetch.assert_not_called()
        self.assert_unpaid()

    def test_currency_mismatch_rejected(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = self.fetched_payment(currency='USD')
            resp = self.post_confirmation()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assert_unpaid()

    def test_duplicate_callback_is_idempotent(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = self.fetched_payment()
            first = self.post_confirmation()
            second = self.post_confirmation()

        self.assertEqual(
            first.url, reverse('order_confirmation', args=[self.order.id])
        )
        self.assertEqual(
            second.url, reverse('order_confirmation', args=[self.order.id])
        )
        # The repeat short-circuits before touching Razorpay again.
        fetch.assert_called_once()

        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.razorpay_payment_id, self.PAYMENT_ID)

    def test_second_payment_for_paid_order_rejected(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = self.fetched_payment()
            self.post_confirmation()

        with mock.patch(PAYMENT_FETCH) as fetch:
            resp = self.post_confirmation(payment_id='pay_SOMETHINGELSE')
            fetch.assert_not_called()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.razorpay_payment_id, self.PAYMENT_ID)

    def test_invalid_signature_rejected_without_fetch(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            resp = self.post_confirmation(signature='0' * 64)
            fetch.assert_not_called()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assert_unpaid()

    def test_missing_params_rejected_without_fetch(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            resp = self.client.post(reverse('payment_success'), {
                'razorpay_order_id': self.ORDER_ID,
            })
            fetch.assert_not_called()

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assert_unpaid()

    def test_paid_flag_from_client_is_ignored(self):
        with mock.patch(PAYMENT_FETCH) as fetch:
            resp = self.post_confirmation(
                signature='0' * 64, is_paid='true'
            )
            fetch.assert_not_called()

        self.assertEqual(resp.status_code, 302)
        self.assert_unpaid()
