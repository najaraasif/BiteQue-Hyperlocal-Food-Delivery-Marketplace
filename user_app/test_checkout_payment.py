from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory

from .models import MerchantNotification, Order, OrderMenuItem

RAZORPAY_CLIENT = 'user_app.views.razorpay.Client'
OSRM = 'user_app.views.calculate_osrm_distance'


def make_restaurant(name='Checkout Kitchen'):
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
        image=f'restaurantImages/{name.replace(" ", "").lower()}.jpg',
    )


def make_menu_item(restaurant, name='Test Burger', price='150.00'):
    size, _ = SizeCategory.objects.get_or_create(name=f'Regular {restaurant.name}')
    return RestaurantMenu.objects.create(
        restaurant=restaurant,
        name=name,
        category='Burgers',
        price=Decimal(price),
        prep_time=10,
        sizes_categories=size,
        image=f'menu_images/{name.replace(" ", "").lower()}.jpg',
    )


def messages_of(response):
    return [m.message for m in get_messages(response.wsgi_request)]


class CheckoutPageTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='pagebuyer', password='pw12345678'
        )
        self.client.force_login(self.customer)
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant, price='150.00')
        session = self.client.session
        session['cart'] = {str(self.item.id): {'quantity': 2}}
        session.save()

    def test_get_renders_checkout_template(self):
        resp = self.client.get(reverse('checkout'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'checkout.html')

    def test_context_cart_items_include_quantities_and_subtotals(self):
        resp = self.client.get(reverse('checkout'))
        cart_items = resp.context['cart_items']
        self.assertEqual(len(cart_items), 1)
        entry = cart_items[0]
        self.assertEqual(entry['id'], self.item.id)
        self.assertEqual(entry['name'], 'Test Burger')
        self.assertEqual(entry['quantity'], 2)
        self.assertEqual(entry['price'], Decimal('150.00'))
        self.assertEqual(entry['subtotal'], Decimal('300.00'))

    def test_context_totals_packaging_gst_and_delivery_fee(self):
        resp = self.client.get(reverse('checkout'))
        ctx = resp.context
        self.assertEqual(ctx['packaging_charges'], Decimal('10.00'))
        self.assertEqual(ctx['platform_gst'], Decimal('9.00'))
        self.assertEqual(ctx['total_price'], Decimal('319.00'))
        self.assertEqual(ctx['delivery_fee'], Decimal('0.00'))

    def test_context_exposes_osrm_and_maps_config(self):
        resp = self.client.get(reverse('checkout'))
        ctx = resp.context
        self.assertEqual(ctx['OSRM_SERVER_URL'], settings.OSRM_SERVER_URL)
        self.assertEqual(
            ctx['GOOGLE_MAPS_API_KEY'], settings.GOOGLE_MAPS_API_KEY
        )
        self.assertEqual(ctx['user'].pk, self.customer.pk)

    def test_context_restaurant_matches_cart_item(self):
        resp = self.client.get(reverse('checkout'))
        self.assertEqual(resp.context['restaurant'].pk, self.restaurant.pk)

    def test_second_cart_item_stacks_into_totals(self):
        second = make_menu_item(self.restaurant, name='Fries', price='50.00')
        session = self.client.session
        session['cart'] = {
            str(self.item.id): {'quantity': 2},
            str(second.id): {'quantity': 1},
        }
        session.save()
        resp = self.client.get(reverse('checkout'))
        ctx = resp.context
        self.assertEqual(len(ctx['cart_items']), 2)
        self.assertEqual(ctx['platform_gst'], Decimal('10.50'))
        self.assertEqual(ctx['total_price'], Decimal('370.50'))


class CheckoutOrderCreationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='createbuyer', password='pw12345678'
        )
        self.client.force_login(self.customer)
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant, price='150.00')
        session = self.client.session
        session['cart'] = {str(self.item.id): {'quantity': 2}}
        session.save()

    def post_create_order(self, **overrides):
        data = {
            'create_order': '1',
            'customer_name': 'Buyer',
            'contact_number': '',
            'delivery_address': '1 Delivery Road',
            'landmark': 'Near park',
            'special_instructions': '',
            'dest_lat': '',
            'dest_lon': '',
            'calculated_distance_km': '1',
            'calculated_delivery_fee': '9999',
        }
        data.update(overrides)
        with mock.patch(RAZORPAY_CLIENT) as client_cls:
            client_cls.return_value.order.create.return_value = {
                'id': 'order_mock_1'
            }
            resp = self.client.post(reverse('checkout'), data)
            created = client_cls.return_value.order.create
        return resp, created

    def give_restaurant_coordinates(self):
        Restaurant.objects.filter(pk=self.restaurant.pk).update(
            lat=Decimal('12.9000000'), lon=Decimal('77.6000000')
        )

    def test_post_without_create_order_flag_renders_page_without_order(self):
        with mock.patch(RAZORPAY_CLIENT) as client_cls:
            resp = self.client.post(reverse('checkout'), {
                'delivery_address': '1 Delivery Road',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'checkout.html')
        self.assertEqual(Order.objects.count(), 0)
        client_cls.assert_not_called()

    def test_order_financial_fields_and_status(self):
        resp, _ = self.post_create_order()
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['success'])

        order = Order.objects.get()
        self.assertEqual(order.user.pk, self.customer.pk)
        self.assertEqual(order.restaurant.pk, self.restaurant.pk)
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.is_paid)
        self.assertEqual(order.total, Decimal('300.00'))
        self.assertEqual(order.item_gst, Decimal('9.00'))
        self.assertEqual(order.packaging_charges, Decimal('10.00'))
        self.assertEqual(order.distance_km, Decimal('1.00'))
        self.assertEqual(order.distance_earning, Decimal('10.00'))
        self.assertEqual(order.final_total, Decimal('329.00'))
        self.assertEqual(order.delivery_address, '1 Delivery Road')
        self.assertEqual(order.landmark, 'Near park')
        self.assertEqual(order.customer_name, 'Buyer')
        self.assertIsNone(order.dest_lat)
        self.assertIsNone(order.dest_lon)

    def test_order_items_recorded_with_quantities(self):
        self.post_create_order()
        order = Order.objects.get()
        items = list(order.order_items.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].menu_item.pk, self.item.id)
        self.assertEqual(items[0].quantity, 2)
        self.assertEqual(items[0].price, Decimal('150.00'))

    def test_razorpay_order_payload(self):
        _, created = self.post_create_order()
        created.assert_called_once()
        payload = created.call_args[0][0]
        self.assertEqual(payload['amount'], 32900)
        self.assertEqual(payload['currency'], 'INR')
        self.assertEqual(payload['payment_capture'], '1')
        order = Order.objects.get()
        self.assertEqual(payload['notes']['order_id'], str(order.id))
        self.assertEqual(
            payload['notes']['actual_amount'], str(order.final_total)
        )

    def test_response_payload_shape(self):
        resp, _ = self.post_create_order()
        payload = resp.json()
        order = Order.objects.get()
        self.assertEqual(
            set(payload.keys()),
            {
                'success', 'razorpay_key', 'razorpay_order_id',
                'razorpay_amount', 'amount', 'order_id',
            },
        )
        self.assertEqual(payload['razorpay_key'], settings.RAZORPAY_KEY_ID)
        self.assertEqual(payload['razorpay_order_id'], 'order_mock_1')
        self.assertEqual(payload['razorpay_amount'], 32900)
        self.assertEqual(payload['amount'], '329.00')
        self.assertEqual(payload['order_id'], order.id)

    def test_razorpay_order_id_persisted_to_order(self):
        self.post_create_order()
        order = Order.objects.get()
        self.assertEqual(order.razorpay_order_id, 'order_mock_1')

    def test_merchant_notification_created(self):
        resp, _ = self.post_create_order()
        self.assertTrue(resp.json()['success'])
        order = Order.objects.get()
        notification = MerchantNotification.objects.get()
        self.assertEqual(notification.merchant.pk, self.restaurant.owner.pk)
        self.assertEqual(notification.message, f'New order #{order.id} received')

    def test_session_cart_survives_order_creation(self):
        self.post_create_order()
        session = self.client.session
        self.assertIn(str(self.item.id), session.get('cart', {}))

    def test_osrm_recompute_overrides_posted_distance(self):
        self.give_restaurant_coordinates()
        with mock.patch(OSRM) as osrm:
            osrm.return_value = 3.5
            resp, _ = self.post_create_order(dest_lat='12.90', dest_lon='77.60')
        self.assertTrue(resp.json()['success'])
        osrm.assert_called_once_with(12.9, 77.6, 12.9, 77.6)
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('3.50'))
        self.assertEqual(order.distance_earning, Decimal('35.00'))
        self.assertEqual(order.final_total, Decimal('354.00'))

    def test_osrm_none_falls_back_to_posted_distance(self):
        self.give_restaurant_coordinates()
        with mock.patch(OSRM) as osrm:
            osrm.return_value = None
            resp, _ = self.post_create_order(
                dest_lat='12.90', dest_lon='77.60',
                calculated_distance_km='2',
            )
        self.assertTrue(resp.json()['success'])
        osrm.assert_called_once()
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('2.00'))
        self.assertEqual(order.final_total, Decimal('339.00'))

    def test_osrm_exception_logs_warning_and_uses_posted_distance(self):
        self.give_restaurant_coordinates()
        with self.assertLogs('user_app.views', level='WARNING') as logs:
            with mock.patch(OSRM) as osrm:
                osrm.side_effect = RuntimeError('osrm down')
                resp, _ = self.post_create_order(
                    dest_lat='12.90', dest_lon='77.60',
                    calculated_distance_km='4',
                )
        self.assertTrue(resp.json()['success'])
        self.assertTrue(any(
            'Server-side distance calculation failed' in line
            for line in logs.output
        ))
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('4.00'))
        self.assertEqual(order.final_total, Decimal('359.00'))

    def test_no_osrm_call_without_restaurant_coordinates(self):
        with mock.patch(OSRM) as osrm:
            resp, _ = self.post_create_order(dest_lat='12.90', dest_lon='77.60')
        self.assertTrue(resp.json()['success'])
        osrm.assert_not_called()
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('1.00'))

    def test_no_osrm_call_when_destination_missing(self):
        self.give_restaurant_coordinates()
        with mock.patch(OSRM) as osrm:
            resp, _ = self.post_create_order(dest_lat='', dest_lon='')
        self.assertTrue(resp.json()['success'])
        osrm.assert_not_called()
        order = Order.objects.get()
        self.assertEqual(order.distance_km, Decimal('1.00'))

    def test_destination_stored_as_decimal_coordinates(self):
        self.give_restaurant_coordinates()
        with mock.patch(OSRM) as osrm:
            osrm.return_value = 3.5
            self.post_create_order(dest_lat='12.90', dest_lon='77.60')
        order = Order.objects.get()
        self.assertEqual(order.dest_lat, Decimal('12.90'))
        self.assertEqual(order.dest_lon, Decimal('77.60'))

    def test_invalid_destination_coordinate_returns_error_and_no_order(self):
        resp, created = self.post_create_order(
            dest_lat='not-a-number', dest_lon='77.60'
        )
        payload = resp.json()
        self.assertEqual(
            payload,
            {
                'success': False,
                'error': 'Unable to create order. Please try again.',
            },
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(MerchantNotification.objects.count(), 0)
        created.assert_not_called()


class PaymentSuccessEdgeTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='edgebuyer', password='pw12345678'
        )
        self.client.force_login(self.customer)

    def test_get_redirects_to_checkout_without_message(self):
        resp = self.client.get(reverse('payment_success'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assertEqual(messages_of(resp), [])

    def test_failed_signature_keeps_session_cart(self):
        session = self.client.session
        session['cart'] = {'77': {'quantity': 3}}
        session.save()

        resp = self.client.post(reverse('payment_success'), {
            'razorpay_order_id': 'order_ANY',
            'razorpay_payment_id': 'pay_ANY',
            'razorpay_signature': '0' * 64,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assertTrue(any(
            'Invalid payment signature.' in m for m in messages_of(resp)
        ))
        session = self.client.session
        self.assertEqual(session.get('cart'), {'77': {'quantity': 3}})

    def test_missing_params_report_verification_failure_and_keep_cart(self):
        session = self.client.session
        session['cart'] = {'55': {'quantity': 1}}
        session.save()

        resp = self.client.post(reverse('payment_success'), {
            'razorpay_order_id': 'order_ANY',
        })
        self.assertEqual(resp.url, reverse('checkout'))
        self.assertTrue(any(
            'Payment verification failed' in m for m in messages_of(resp)
        ))
        session = self.client.session
        self.assertEqual(session.get('cart'), {'55': {'quantity': 1}})
