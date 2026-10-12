import hashlib
import hmac
import zlib
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from merchant_app.models import MerchantEarning, Restaurant, RestaurantMenu, SizeCategory
from rider_app.models import OrderAssignment, Rider, RiderEarning
from user_app.models import (
    CustomerFeedback,
    MerchantNotification,
    Order,
    OrderMenuItem,
)

RAZORPAY_CLIENT = 'user_app.views.razorpay.Client'
PAYMENT_FETCH = 'razorpay.resources.payment.Payment.fetch'

RIDE_OTP_HEADER = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


def make_restaurant(owner, name='Lifecycle Kitchen'):
    return Restaurant.objects.create(
        owner=owner,
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Main Road',
        city='Testville',
        image=f'restaurantImages/{name.replace(" ", "").lower()}.jpg',
    )


def make_menu_item(restaurant, name='Lifecycle Burger', price='150.00'):
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


def make_rider(username, approved=True, available=True):
    user = User.objects.create_user(username=username, password='pw12345678')
    aadhar = str(10_000_000_000 + zlib.crc32(username.encode()) % 10**11)
    return Rider.objects.create(
        user=user,
        phone='9876543210',
        gender='Male',
        aadhar_number=aadhar,
        driving_license=f'DL-{username}'[:20],
        address='1 Test Street',
        area='Test Area',
        pincode='123456',
        profile_photo='riders/profiles/p.jpg',
        aadhar_front='riders/aadhar/f.jpg',
        license_copy='riders/license/l.jpg',
        is_approved=approved,
        is_available=available,
    )


def sign_payload(order_id, payment_id):
    message = f'{order_id}|{payment_id}'.encode()
    return hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(), message, hashlib.sha256
    ).hexdigest()


class LifecycleBase(TestCase):
    """Three independent sessions (customer, merchant, rider) plus a
    shared catalogue fixture, reused by every end-to-end scenario."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='e2e_customer', password='pw12345678'
        )
        self.merchant = User.objects.create_user(
            username='e2e_merchant', password='pw12345678'
        )
        self.restaurant = make_restaurant(self.merchant)
        self.restaurant.is_approved = True
        self.restaurant.save()
        self.item = make_menu_item(self.restaurant, price='150.00')

        self.rider1 = make_rider('e2e_rider1')

        self.customer_client = self.client_class()
        self.customer_client.force_login(self.customer)
        self.merchant_client = self.client_class()
        self.merchant_client.force_login(self.merchant)
        self.rider_client = self.client_class()
        self.rider_client.force_login(self.rider1.user)

    def fill_cart(self, client=None, quantity=2, item=None):
        client = client or self.customer_client
        session = client.session
        session['cart'] = {str((item or self.item).id): {'quantity': quantity}}
        session.save()

    def create_order(self, **overrides):
        """Create a pending order straight through the checkout endpoint."""
        self.fill_cart()
        data = {
            'create_order': '1',
            'customer_name': 'Lifecycle Buyer',
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
                'id': 'order_e2e_1'
            }
            resp = self.customer_client.post(reverse('checkout'), data)
        assert resp.status_code == 200 and resp.json()['success'], resp.content
        return Order.objects.latest('pk')

    def pay_for(self, order, payment_id='pay_E2EONE'):
        payload = {
            'razorpay_order_id': order.razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': sign_payload(
                order.razorpay_order_id, payment_id
            ),
        }
        with mock.patch(PAYMENT_FETCH) as fetch:
            fetch.return_value = {
                'id': payment_id,
                'order_id': order.razorpay_order_id,
                'amount': int(order.final_total * 100),
                'currency': 'INR',
                'status': 'captured',
            }
            resp = self.customer_client.post(reverse('payment_success'), payload)
        return resp

    def merchant_confirm(self, order):
        return self.merchant_client.get(
            reverse('confirm_order', args=[order.pk])
        )

    def merchant_mark_ready(self, order):
        return self.merchant_client.get(
            reverse('mark_order_ready', args=[order.pk])
        )

    def rider_accept(self, order, client=None):
        client = client or self.rider_client
        return client.post(
            reverse('rider:accept_order_assignment_action', args=[order.pk])
        )

    def rider_deliver(self, order, otp, client=None, headers=None):
        client = client or self.rider_client
        return client.post(
            reverse('rider:mark_delivered', args=[order.pk]),
            {'otp': otp},
            **(headers or {}),
        )


class CustomerJourneyTests(LifecycleBase):
    def test_anonymous_checkout_redirects_to_login_with_next(self):
        anon = self.client_class()
        resp = anon.get(reverse('checkout'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            f"{reverse('user_login')}?next={reverse('checkout')}", resp.url
        )

    def test_browse_to_payment_creates_paid_order_with_correct_money(self):
        home = self.customer_client.get(reverse('home'))
        self.assertEqual(home.status_code, 200)

        add = self.customer_client.get(
            reverse('add_to_cart', args=[self.item.pk]),
            HTTP_REFERER=reverse('user_view_menu', args=[self.restaurant.pk]),
        )
        self.assertEqual(add.status_code, 302)

        cart = self.customer_client.get(reverse('view_cart'))
        self.assertEqual(len(cart.context['cart_items']), 1)

        checkout = self.customer_client.get(reverse('checkout'))
        self.assertEqual(checkout.status_code, 200)

        order = self.create_order()
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.is_paid)
        self.assertEqual(order.total, Decimal('300.00'))
        self.assertEqual(order.item_gst, Decimal('9.00'))
        self.assertEqual(order.packaging_charges, Decimal('10.00'))
        self.assertEqual(order.distance_km, Decimal('1.00'))
        self.assertEqual(order.distance_earning, Decimal('10.00'))
        self.assertEqual(order.final_total, Decimal('329.00'))
        self.assertEqual(
            order.order_items.count(), 1
        )
        line = order.order_items.get()
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.price, Decimal('150.00'))

        resp = self.pay_for(order)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, reverse('order_confirmation', args=[order.pk])
        )
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.razorpay_payment_id, 'pay_E2EONE')
        self.assertNotIn('cart', self.customer_client.session)

        confirmation = self.customer_client.get(
            reverse('order_confirmation', args=[order.pk])
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTemplateUsed(confirmation, 'order_confirmation.html')

    def test_failed_payment_leaves_order_unpaid_and_cart_in_place(self):
        order = self.create_order()
        self.fill_cart()

        resp = self.customer_client.post(reverse('payment_success'), {
            'razorpay_order_id': order.razorpay_order_id,
            'razorpay_payment_id': 'pay_BAD',
            'razorpay_signature': '0' * 64,
        })
        self.assertEqual(resp.url, reverse('checkout'))
        order.refresh_from_db()
        self.assertFalse(order.is_paid)
        self.assertIn('cart', self.customer_client.session)

    def test_checkout_notifies_merchant_and_poll_returns_it_once(self):
        order = self.create_order()
        self.assertTrue(MerchantNotification.objects.filter(
            merchant=self.merchant,
            message=f'New order #{order.pk} received',
        ).exists())

        first = self.merchant_client.get(reverse('check_notifications'))
        self.assertEqual(
            first.json(),
            {'notify': True, 'message': f'New order #{order.pk} received'},
        )
        second = self.merchant_client.get(reverse('check_notifications'))
        self.assertEqual(second.json(), {'notify': False})

    def test_pending_order_lives_in_active_not_history(self):
        order = self.create_order()
        active = self.customer_client.get(reverse('user_active_orders'))
        history = self.customer_client.get(reverse('order_user_history'))
        self.assertIn(order.pk, [o.pk for o in active.context['active_orders']])
        self.assertNotIn(order.pk, [o.pk for o in history.context['past_orders']])

    def test_order_confirmation_blocks_unpaid_order(self):
        order = self.create_order()
        resp = self.customer_client.get(
            reverse('order_confirmation', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))

    def test_logout_flushes_the_cart_session(self):
        self.fill_cart()
        self.customer_client.get(reverse('user_logout'))
        self.assertNotIn('cart', self.customer_client.session)
        self.customer_client.force_login(self.customer)
        resp = self.customer_client.get(reverse('checkout'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('home'))


class MerchantFulfilmentTests(LifecycleBase):
    def test_ready_order_moves_into_history_and_creates_assignments(self):
        rider2 = make_rider('e2e_rider2')
        order = self.create_order()

        dashboard = self.merchant_client.get(reverse('merchant_dashboard'))
        self.assertIn(order.pk, [o.pk for o in dashboard.context['Pending_orders']])

        self.merchant_confirm(order)
        order.refresh_from_db()
        self.assertEqual(order.status, 'confirmed')

        ready = self.merchant_mark_ready(order)
        self.assertEqual(ready.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, 'ready')

        pending_riders = set(
            OrderAssignment.objects.filter(
                order=order, status='pending'
            ).values_list('rider_id', flat=True)
        )
        self.assertEqual(pending_riders, {self.rider1.pk, rider2.pk})

        orders_page = self.merchant_client.get(reverse('merchant_orders'))
        history_pks = [o.pk for o in orders_page.context['order_history']]
        self.assertIn(order.pk, history_pks)
        self.assertEqual(len(orders_page.context['pending_orders']), 0)
        self.assertEqual(len(orders_page.context['confirmed_orders']), 0)

    def test_dashboard_top_item_reflects_pending_order_lines(self):
        order = self.create_order()

        pending_page = self.merchant_client.get(reverse('merchant_dashboard'))
        quantities = pending_page.context['order_item_quantities']
        self.assertEqual(quantities[order.pk][self.item.pk], 2)

        self.merchant_confirm(order)
        self.merchant_mark_ready(order)

        dashboard = self.merchant_client.get(reverse('merchant_dashboard'))
        ctx = dashboard.context
        self.assertEqual(len(ctx['top_items']), 1)
        self.assertEqual(ctx['top_items'][0]['menu_item__name'],
                         'Lifecycle Burger')
        self.assertEqual(ctx['top_items'][0]['total_quantity'], 2)


class RiderDeliveryTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        self.order = self.create_order()
        self.merchant_confirm(self.order)
        self.merchant_mark_ready(self.order)

    def order_with_sibling(self, username):
        """A second rider that exists before a fresh order reaches ready,
        so both riders receive a pending assignment for it."""
        rider2 = make_rider(username)
        order = self.create_order()
        self.merchant_confirm(order)
        self.merchant_mark_ready(order)
        return order, rider2

    def test_rider_order_detail_offers_acceptance_prompt(self):
        resp = self.rider_client.get(
            reverse('rider:rider_order_detail', args=[self.order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'rider_app/accept_order_prompt.html')

    def test_accept_sets_out_for_delivery_and_generates_pin(self):
        resp = self.rider_accept(self.order)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse('rider:rider_order_detail', args=[self.order.pk]),
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')
        self.assertTrue(self.order.delivery_pin)
        assignment = OrderAssignment.objects.get(
            order=self.order, rider=self.rider1
        )
        self.assertEqual(assignment.status, 'accepted')
        self.assertIsNotNone(assignment.accepted_at)

    def test_accepting_rejects_the_sibling_assignment(self):
        order, rider2 = self.order_with_sibling('e2e_sibling')
        sibling = OrderAssignment.objects.get(order=order, rider=rider2)
        self.assertEqual(sibling.status, 'pending')

        self.rider_accept(order)

        sibling.refresh_from_db()
        self.assertEqual(sibling.status, 'rejected')
        other_resp = self.rider_client.get(
            reverse('rider:rider_order_detail', args=[order.pk])
        )
        self.assertEqual(other_resp.status_code, 200)

    def test_second_rider_cannot_accept_rejected_assignment(self):
        order, rider2 = self.order_with_sibling('e2e_late')
        self.rider_accept(order)

        late_client = self.client_class()
        late_client.force_login(rider2.user)
        resp = late_client.post(
            reverse('rider:accept_order_assignment_action',
                    args=[order.pk])
        )
        self.assertEqual(resp.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, 'out_for_delivery')
        late = OrderAssignment.objects.get(order=order, rider=rider2)
        self.assertEqual(late.status, 'rejected')
        self.assertTrue(any(
            'cannot be accepted' in m for m in messages_of(resp)
        ))

    def test_customer_order_detail_shows_rider_and_pin(self):
        self.rider_accept(self.order)
        resp = self.customer_client.get(
            reverse('order_detail', args=[self.order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.order.refresh_from_db()
        self.assertEqual(ctx['rider'].pk, self.rider1.pk)
        self.assertEqual(ctx['order'].delivery_pin, self.order.delivery_pin)
        self.assertTrue(ctx['order'].delivery_pin)

    def test_deliver_with_wrong_pin_then_correct_pin(self):
        self.rider_accept(self.order)

        form_page = self.rider_client.get(
            reverse('rider:mark_delivered', args=[self.order.pk])
        )
        self.assertEqual(form_page.status_code, 200)
        self.assertTemplateUsed(form_page, 'rider_app/mark_delivered_otp.html')

        wrong = self.rider_deliver(self.order, '000000')
        self.assertEqual(wrong.status_code, 200)
        self.assertTemplateUsed(wrong, 'rider_app/mark_delivered_otp.html')
        self.assertTrue(any(
            'Incorrect PIN' in m for m in messages_of(wrong)
        ))
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_pin_attempts, 1)
        self.assertEqual(self.order.status, 'out_for_delivery')

        self.order.refresh_from_db()
        done = self.rider_deliver(self.order, self.order.delivery_pin)
        self.assertEqual(done.status_code, 302)
        self.assertEqual(done.url, reverse('rider:dashboard'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        assignment = OrderAssignment.objects.get(
            order=self.order, rider=self.rider1
        )
        self.assertEqual(assignment.status, 'delivered')

    def test_deliver_commission_earning_math_for_midsize_order(self):
        self.rider_accept(self.order)
        self.order.refresh_from_db()

        resp = self.rider_deliver(self.order, self.order.delivery_pin)
        self.assertTrue(any(
            'marked as delivered successfully' in m for m in messages_of(resp)
        ))

        self.order.refresh_from_db()
        self.assertEqual(self.order.commission, Decimal('18.00'))
        self.assertEqual(self.order.total_earning, Decimal('28.00'))

        self.rider1.refresh_from_db()
        self.assertEqual(self.rider1.today_earnings, Decimal('28.00'))

        earning = RiderEarning.objects.get(rider=self.rider1)
        self.assertEqual(earning.total_earnings, Decimal('28.00'))
        self.assertEqual(earning.orders_completed, 1)
        self.assertEqual(earning.distance_km, Decimal('1.00'))
        self.assertEqual(earning.distance_earning, Decimal('10.00'))
        self.assertEqual(earning.commission_earning, Decimal('18.00'))

    def test_second_deliver_attempt_earns_nothing(self):
        self.rider_accept(self.order)
        self.order.refresh_from_db()
        self.rider_deliver(self.order, self.order.delivery_pin)
        self.assertEqual(RiderEarning.objects.count(), 1)

        again = self.rider_deliver(self.order, self.order.delivery_pin)
        self.assertEqual(again.status_code, 302)
        self.assertEqual(again.url, reverse('rider:dashboard'))
        self.assertTrue(any(
            'already been marked as delivered' in m
            or 'not found' in m for m in messages_of(again)
        ))
        self.assertEqual(RiderEarning.objects.count(), 1)
        self.rider1.refresh_from_db()
        self.assertEqual(self.rider1.today_earnings, Decimal('28.00'))

    def test_ajax_deliver_returns_json_success(self):
        self.rider_accept(self.order)
        self.order.refresh_from_db()
        resp = self.rider_client.post(
            reverse('rider:mark_delivered', args=[self.order.pk]),
            {'otp': self.order.delivery_pin},
            **RIDE_OTP_HEADER,
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['order_id'], self.order.pk)

    def test_ajax_wrong_pin_returns_json_field_error(self):
        self.rider_accept(self.order)
        resp = self.rider_client.post(
            reverse('rider:mark_delivered', args=[self.order.pk]),
            {'otp': '111111'},
            **RIDE_OTP_HEADER,
        )
        self.assertEqual(resp.status_code, 400)
        payload = resp.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('otp', payload['field_errors'])

    def test_delivered_order_moves_to_customer_history(self):
        self.rider_accept(self.order)
        self.order.refresh_from_db()
        self.rider_deliver(self.order, self.order.delivery_pin)

        active = self.customer_client.get(reverse('user_active_orders'))
        history = self.customer_client.get(reverse('order_user_history'))
        active_pks = [o.pk for o in active.context['active_orders']]
        history_pks = [o.pk for o in history.context['past_orders']]
        self.assertNotIn(self.order.pk, active_pks)
        self.assertIn(self.order.pk, history_pks)

    def test_rider_earnings_page_lists_the_new_row(self):
        self.rider_accept(self.order)
        self.order.refresh_from_db()
        self.rider_deliver(self.order, self.order.delivery_pin)

        resp = self.rider_client.get(reverse('rider:earnings'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'rider_app/earnings.html')
        self.assertTrue(resp.context['total_earnings'] >= Decimal('28.00'))

    def test_acceptance_rates_split_after_partial_accept(self):
        order, rider2 = self.order_with_sibling('e2e_rate2')
        self.rider_accept(order)
        rider2.refresh_from_db()
        self.rider1.refresh_from_db()
        self.assertGreater(self.rider1.get_acceptance_rate(), 0)
        self.assertEqual(rider2.get_acceptance_rate(), 0.0)


class PostDeliveryReportingTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        self.order = self.create_order()
        self.pay_for(self.order)
        self.merchant_confirm(self.order)
        self.merchant_mark_ready(self.order)
        self.rider_accept(self.order)
        self.order.refresh_from_db()
        self.rider_deliver(self.order, self.order.delivery_pin)
        self.order.refresh_from_db()

    def test_revenue_report_counts_delivered_order(self):
        resp = self.merchant_client.get(reverse('merchant_revenue_report'))
        ctx = resp.context
        self.assertEqual(ctx['total_revenue'], Decimal('252.00'))
        self.assertEqual(ctx['today_revenue'], Decimal('252.00'))

    def test_payment_section_upserts_merchant_earning(self):
        resp = self.merchant_client.get(reverse('merchant_payment_section'))
        ctx = resp.context
        self.assertEqual(ctx['total_revenues'], Decimal('300.00'))
        self.assertEqual(ctx['merchant_share'], Decimal('252.00'))
        self.assertEqual(ctx['paid_amount'], 0)
        self.assertEqual(ctx['pending_amount'], Decimal('252.00'))
        earning = MerchantEarning.objects.get(
            merchant=self.merchant, restaurant=self.restaurant
        )
        self.assertEqual(earning.net_sales, Decimal('300.00'))
        self.assertEqual(earning.amount_pending, Decimal('252.00'))

    def test_money_is_consistent_across_all_three_apps(self):
        self.merchant_client.get(reverse('merchant_payment_section'))
        order = self.order
        self.assertEqual(
            order.final_total,
            (order.total + order.item_gst + order.packaging_charges
             + order.distance_earning).quantize(Decimal('0.00')),
        )
        self.assertEqual(order.commission, Decimal('18.00'))
        self.assertEqual(order.total_earning, Decimal('28.00'))
        self.rider1.refresh_from_db()
        self.assertEqual(self.rider1.today_earnings, order.total_earning)
        earning = MerchantEarning.objects.get(merchant=self.merchant)
        self.assertEqual(earning.net_sales, order.total)
        self.assertEqual(
            earning.net_sales * Decimal('0.84'), Decimal('252.0000')
        )

    def test_customer_feedback_lands_in_merchant_feedback_page(self):
        resp = self.customer_client.post(
            reverse('write_feedback', args=[self.order.pk]),
            {
                'item_quality': '5',
                'delivery_experience': '4',
                'restaurant_rating': '5',
                'rider_rating': '4',
                'additional_comments': 'Great end to end',
                f'item_rating_{self.item.pk}': '5',
            },
        )
        self.assertEqual(resp.status_code, 302)
        feedback = CustomerFeedback.objects.get(order=self.order)
        self.assertEqual(feedback.rating, 4)

        merchant_page = self.merchant_client.get(
            reverse('customer_feedback')
        )
        feedbacks = list(merchant_page.context['feedbacks'])
        self.assertEqual([f.pk for f in feedbacks], [feedback.pk])

    def test_invoice_downloads_as_pdf_after_delivery(self):
        resp = self.customer_client.get(
            reverse('download_invoice', args=[self.order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_merchant_history_lists_delivered_order(self):
        resp = self.merchant_client.get(reverse('merchant_orders'))
        history = list(resp.context['order_history'])
        self.assertEqual([o.pk for o in history], [self.order.pk])
        self.assertEqual(history[0].status, 'delivered')

    def test_dashboard_revenue_after_delivery(self):
        resp = self.merchant_client.get(reverse('merchant_dashboard'))
        ctx = resp.context
        self.assertEqual(ctx['total_orders_today'], 1)
        self.assertEqual(ctx['total_revenue_today'], Decimal('300.00'))
        self.assertEqual(ctx['net_revenue'], Decimal('252.00'))


class CrossRoleBoundaryTests(LifecycleBase):
    def test_customer_sees_404_on_merchant_dashboard(self):
        resp = self.customer_client.get(reverse('merchant_dashboard'))
        self.assertEqual(resp.status_code, 404)

    def test_merchant_is_redirected_off_rider_dashboard(self):
        resp = self.merchant_client.get(reverse('rider:dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_customer_is_redirected_off_rider_order_detail(self):
        order = self.create_order()
        resp = self.customer_client.get(
            reverse('rider:rider_order_detail', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 302)

    def test_anonymous_rider_dashboard_redirects_to_login(self):
        anon = self.client_class()
        resp = anon.get(reverse('rider:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/accounts/login/?next=/dashboard/')

    def test_merchant_cannot_confirm_foreign_order(self):
        foreign_owner = User.objects.create_user(
            username='e2e_foreign_merchant', password='pw12345678'
        )
        foreign_restaurant = make_restaurant(foreign_owner, name='Foreign Spot')
        foreign_order = Order.objects.create(
            user=self.customer,
            restaurant=foreign_restaurant,
            customer_name='Someone',
            customer_contact='',
            landmark='',
            delivery_address='2 Road',
            special_instructions='',
        )
        resp = self.merchant_client.get(
            reverse('confirm_order', args=[foreign_order.pk])
        )
        self.assertEqual(resp.status_code, 404)
        foreign_order.refresh_from_db()
        self.assertEqual(foreign_order.status, 'pending')
