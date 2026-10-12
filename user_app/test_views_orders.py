from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory
from rider_app.models import OrderAssignment, Rider

from .models import CustomerFeedback, Order, OrderMenuItem


def make_restaurant(name='Orders Kitchen'):
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


def make_menu_item(restaurant, name='Test Burger', price='100.00'):
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


def make_order(user, restaurant, **kwargs):
    defaults = {
        'customer_name': 'Pat',
        'customer_contact': '',
        'landmark': 'Near park',
        'delivery_address': '1 Road',
        'special_instructions': '',
        'status': 'delivered',
    }
    defaults.update(kwargs)
    return Order.objects.create(user=user, restaurant=restaurant, **defaults)


def add_item(order, item, quantity=1, price=None):
    return OrderMenuItem.objects.create(
        order=order, menu_item=item, quantity=quantity,
        price=price or item.price,
    )


def make_rider(username='rider1', **kwargs):
    user = User.objects.create_user(username=username, password='pw12345678')
    defaults = {
        'user': user,
        'phone': '9876500001',
        'gender': 'M',
        'aadhar_number': f'{abs(hash(username)) % 10**12:012d}',
        'driving_license': f'DL{abs(hash(username)) % 10**9:09d}',
        'address': '1 Rider Road',
        'pincode': '560001',
        'profile_photo': 'riders/profiles/p.jpg',
        'aadhar_front': 'riders/aadhar/f.jpg',
        'license_copy': 'riders/license/l.jpg',
        'is_approved': True,
        'is_available': True,
    }
    defaults.update(kwargs)
    return Rider.objects.create(**defaults)


def messages_of(response):
    return [m.message for m in get_messages(response.wsgi_request)]


class OrderDetailTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant, price='200.00')
        self.user = User.objects.create_user(username='detailuser', password='pw12345678')
        self.other = User.objects.create_user(username='detailstranger', password='pw12345678')
        self.client.force_login(self.user)

    def build_order(self, **kwargs):
        order = make_order(self.user, self.restaurant, **kwargs)
        add_item(order, self.item, quantity=2)
        return order

    def test_login_required(self):
        self.client.logout()
        order = self.build_order()
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(resp.status_code, 302)

    def test_foreign_order_returns_404(self):
        order = self.build_order()
        self.client.force_login(self.other)
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(resp.status_code, 404)

    def test_unknown_order_returns_404(self):
        resp = self.client.get(reverse('order_detail', args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_context_math_subtotal_gst_delivery_and_total(self):
        order = self.build_order(
            distance_earning=Decimal('25.00'),
            total=Decimal('400.00'),
        )
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'order_detail.html')
        ctx = resp.context
        self.assertEqual(ctx['item_subtotal'], Decimal('400.00'))
        self.assertEqual(ctx['gst'], Decimal('12.00'))
        self.assertEqual(ctx['delivery_fee'], Decimal('25.60'))
        self.assertEqual(ctx['pakaging_charges'], Decimal('10.00'))
        self.assertEqual(ctx['order_total'], Decimal('447.60'))
        self.assertEqual(len(ctx['order_items']), 1)
        self.assertEqual(ctx['order_items'][0]['quantity'], 2)

    def test_eta_is_created_at_plus_45_minutes(self):
        order = self.build_order()
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(
            resp.context['eta'], order.created_at + timedelta(minutes=45)
        )

    def test_feedback_none_until_written(self):
        order = self.build_order()
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertIsNone(resp.context['feedback'])

    def test_existing_feedback_passed_to_context(self):
        order = self.build_order()
        fb = CustomerFeedback.objects.create(
            order=order, restaurant=self.restaurant, customer=self.user, rating=5
        )
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(resp.context['feedback'].pk, fb.pk)

    def test_rider_none_without_accepted_assignment(self):
        order = self.build_order()
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertIsNone(resp.context['rider'])

    def test_rider_taken_from_accepted_assignment(self):
        order = self.build_order()
        rider = make_rider('detailrider')
        OrderAssignment.objects.create(
            rider=rider, order=order, status='accepted'
        )
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(resp.context['rider'].pk, rider.pk)

    def test_pending_assignment_does_not_supply_rider(self):
        order = self.build_order()
        rider = make_rider('detailrider2')
        OrderAssignment.objects.create(
            rider=rider, order=order, status='pending'
        )
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertIsNone(resp.context['rider'])

    def test_pin_issued_on_first_view_when_out_for_delivery(self):
        order = self.build_order(status='out_for_delivery')
        self.assertFalse(order.delivery_pin)
        resp = self.client.get(reverse('order_detail', args=[order.id]))
        order.refresh_from_db()
        self.assertTrue(order.delivery_pin)
        self.assertEqual(len(order.delivery_pin), 4)
        self.assertTrue(order.delivery_pin.isdigit())
        self.assertEqual(order.delivery_pin_attempts, 0)
        self.assertEqual(resp.context['order'].delivery_pin, order.delivery_pin)

    def test_pin_not_issued_before_out_for_delivery(self):
        order = self.build_order(status='confirmed')
        self.client.get(reverse('order_detail', args=[order.id]))
        order.refresh_from_db()
        self.assertFalse(order.delivery_pin)
        self.assertIsNone(order.delivery_pin_generated_at)

    def test_existing_fresh_pin_survives_view(self):
        order = self.build_order(status='out_for_delivery')
        order.generate_delivery_pin()
        order.save()
        original = order.delivery_pin
        self.client.get(reverse('order_detail', args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.delivery_pin, original)

    def test_expired_pin_is_reissued_with_reset_attempts(self):
        order = self.build_order(status='out_for_delivery')
        order.generate_delivery_pin()
        order.delivery_pin_attempts = 3
        order.save()
        old_generated = order.delivery_pin_generated_at
        ttl = getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30)
        Order.objects.filter(pk=order.pk).update(
            delivery_pin_generated_at=old_generated - timedelta(minutes=ttl + 5),
            delivery_pin_attempts=3,
        )
        self.client.get(reverse('order_detail', args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.delivery_pin_attempts, 0)
        self.assertGreater(order.delivery_pin_generated_at, old_generated)


class OrderConfirmationTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.user = User.objects.create_user(username='confirmuser', password='pw12345678')
        self.other = User.objects.create_user(username='confirmstranger', password='pw12345678')

    def test_login_required(self):
        order = make_order(self.user, self.restaurant)
        resp = self.client.get(reverse('order_confirmation', args=[order.id]))
        self.assertEqual(resp.status_code, 302)

    def test_unpaid_order_redirects_to_checkout_with_warning(self):
        self.client.force_login(self.user)
        order = make_order(self.user, self.restaurant, is_paid=False)
        resp = self.client.get(reverse('order_confirmation', args=[order.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assertTrue(any('Payment not completed yet' in m for m in messages_of(resp)))

    def test_paid_order_renders_confirmation(self):
        self.client.force_login(self.user)
        order = make_order(self.user, self.restaurant, is_paid=True)
        resp = self.client.get(reverse('order_confirmation', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'order_confirmation.html')
        self.assertEqual(resp.context['order'].pk, order.pk)

    def test_foreign_order_returns_404(self):
        order = make_order(self.user, self.restaurant, is_paid=True)
        self.client.force_login(self.other)
        resp = self.client.get(reverse('order_confirmation', args=[order.id]))
        self.assertEqual(resp.status_code, 404)


class ActiveOrdersAndHistoryTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.user = User.objects.create_user(username='listuser', password='pw12345678')
        self.other = User.objects.create_user(username='liststranger', password='pw12345678')
        self.client.force_login(self.user)

    def test_active_orders_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('user_active_orders'))
        self.assertEqual(resp.status_code, 302)

    def test_active_orders_lists_only_open_statuses(self):
        for status in ('pending', 'confirmed', 'ready', 'out_for_delivery'):
            make_order(self.user, self.restaurant, status=status)
        make_order(self.user, self.restaurant, status='delivered')
        make_order(self.other, self.restaurant, status='pending')
        resp = self.client.get(reverse('user_active_orders'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'partials/active_orders.html')
        statuses = [o.status for o in resp.context['active_orders']]
        self.assertCountEqual(
            statuses, ['pending', 'confirmed', 'ready', 'out_for_delivery']
        )
        self.assertEqual(len(resp.context['orders']), 5)

    def test_active_orders_sorted_newest_first(self):
        older = make_order(self.user, self.restaurant, status='pending')
        newer = make_order(self.user, self.restaurant, status='pending')
        Order.objects.filter(pk=older.pk).update(created_at='2026-01-01T00:00:00Z')
        Order.objects.filter(pk=newer.pk).update(created_at='2026-02-01T00:00:00Z')
        resp = self.client.get(reverse('user_active_orders'))
        ids = [o.id for o in resp.context['active_orders']]
        self.assertEqual(ids, [newer.id, older.id])

    def test_history_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('order_user_history'))
        self.assertEqual(resp.status_code, 302)

    def test_history_lists_only_delivered_orders(self):
        make_order(self.user, self.restaurant, status='delivered')
        make_order(self.user, self.restaurant, status='pending')
        make_order(self.other, self.restaurant, status='delivered')
        resp = self.client.get(reverse('order_user_history'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'partials/order_history.html')
        self.assertEqual(len(resp.context['past_orders']), 1)
        self.assertEqual(resp.context['past_orders'][0].status, 'delivered')
        self.assertEqual(len(resp.context['orders']), 2)


class DownloadInvoiceTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant, price='100.00')
        self.user = User.objects.create_user(username='invoiceuser', password='pw12345678')
        self.other = User.objects.create_user(username='invoicestranger', password='pw12345678')
        self.client.force_login(self.user)

    def build_order(self, **kwargs):
        order = make_order(self.user, self.restaurant, **kwargs)
        add_item(order, self.item, quantity=1)
        return order

    def test_login_required(self):
        self.client.logout()
        order = self.build_order()
        resp = self.client.get(reverse('download_invoice', args=[order.id]))
        self.assertEqual(resp.status_code, 302)

    def test_foreign_order_returns_404(self):
        order = self.build_order(status='delivered')
        self.client.force_login(self.other)
        resp = self.client.get(reverse('download_invoice', args=[order.id]))
        self.assertEqual(resp.status_code, 404)

    def test_not_delivered_is_forbidden(self):
        for status in ('pending', 'confirmed', 'ready', 'out_for_delivery'):
            with self.subTest(status=status):
                order = self.build_order(status=status)
                resp = self.client.get(reverse('download_invoice', args=[order.id]))
                self.assertEqual(resp.status_code, 403)
                self.assertIn(
                    'Invoice is available only for delivered orders.',
                    resp.content.decode(),
                )

    def test_delivered_order_renders_invoice_pdf(self):
        order = self.build_order(
            status='delivered',
            total=Decimal('100.00'),
            distance_earning=Decimal('25.00'),
        )
        with mock.patch('user_app.views.render_to_string') as render, \
                mock.patch('user_app.views.HTML') as html_cls:
            render.return_value = '<html>invoice</html>'
            html_cls.return_value.write_pdf.return_value = b'%PDF-1.4 fake'
            resp = self.client.get(reverse('download_invoice', args=[order.id]))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertEqual(
            resp['Content-Disposition'],
            f'attachment; filename=invoice_order_{order.id}.pdf',
        )
        self.assertEqual(resp.content, b'%PDF-1.4 fake')

        render.assert_called_once()
        template_name, context = render.call_args[0]
        self.assertEqual(template_name, 'invoice.html')
        self.assertEqual(context['order'].pk, order.pk)
        self.assertEqual(context['delivery_fee'], Decimal('25.60'))
        self.assertEqual(context['gst'], Decimal('3.00'))
        self.assertEqual(context['packaging_charges'], Decimal('10.00'))
        self.assertEqual(context['order_total'], Decimal('138.60'))
        self.assertIn('now', context)

        html_cls.assert_called_once()
        kwargs = html_cls.call_args[1]
        self.assertEqual(kwargs['string'], '<html>invoice</html>')
        self.assertEqual(kwargs['base_url'], 'http://testserver/')
        html_cls.return_value.write_pdf.assert_called_once()

    def test_invoice_gst_scales_with_order_total(self):
        order = self.build_order(
            status='delivered',
            total=Decimal('333.33'),
            distance_earning=Decimal('0.00'),
        )
        with mock.patch('user_app.views.render_to_string') as render, \
                mock.patch('user_app.views.HTML'):
            render.return_value = '<html></html>'
            self.client.get(reverse('download_invoice', args=[order.id]))
        context = render.call_args[0][1]
        self.assertEqual(context['gst'], Decimal('9.9999'))
        self.assertEqual(context['order_total'], Decimal('353.93'))
