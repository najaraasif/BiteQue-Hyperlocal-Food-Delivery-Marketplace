import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string as real_render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils import http
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.db import IntegrityError

from rider_app.models import OrderAssignment, Rider
from user_app.models import CustomerFeedback, MerchantNotification, Order, OrderMenuItem

from .forms import RestaurantForm
from .models import (
    BankAccount,
    MerchantEarning,
    MerchantPayment,
    Restaurant,
    RestaurantMenu,
    Review,
    SizeCategory,
    Ticket,
    TicketMessage,
    merchantRegistration,
)


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username, password='pw12345678', **kwargs
    )


def make_registration(user, approved=False):
    return merchantRegistration.objects.create(
        username=user,
        name=user.username.title(),
        number=Decimal('9876543210.0'),
        is_approved=approved,
    )


def make_restaurant(owner, name='View Kitchen', **kwargs):
    defaults = dict(
        owner=owner,
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Main Road',
        city='Testville',
        image=f'restaurantImages/{name.replace(" ", "").lower()}.jpg',
    )
    defaults.update(kwargs)
    return Restaurant.objects.create(**defaults)


def make_menu(restaurant, name='Dash Burger', price='100.00', **kwargs):
    size, _ = SizeCategory.objects.get_or_create(
        name=f'Regular {restaurant.name}'
    )
    defaults = dict(
        restaurant=restaurant,
        name=name,
        category='Burgers',
        price=Decimal(price),
        prep_time=10,
        sizes_categories=size,
        image=f'menu_images/{name.replace(" ", "").lower()}.jpg',
    )
    defaults.update(kwargs)
    return RestaurantMenu.objects.create(**defaults)


def make_order(restaurant, user=None, status='pending', total='100.00', **kwargs):
    kwargs.setdefault('customer_name', 'View Customer')
    customer_name = kwargs.pop('customer_name')
    order = Order.objects.create(
        user=user or make_user(f'cust_{restaurant.pk}_{Order.objects.count()}'),
        restaurant=restaurant,
        customer_name=customer_name,
        customer_contact='',
        landmark='',
        delivery_address='1 Road',
        special_instructions='',
        status=status,
        total=Decimal(total),
        **kwargs,
    )
    return order


def add_order_item(order, item, quantity=1, price=None):
    return OrderMenuItem.objects.create(
        order=order, menu_item=item, quantity=quantity,
        price=price or item.price,
    )


def make_rider(username, approved=True, available=True):
    import zlib
    user = make_user(username)
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


def message_list(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class SavePlayerIdTests(TestCase):
    def setUp(self):
        self.owner = make_user('player_owner')
        self.restaurant = make_restaurant(self.owner, name='Player Kitchen')
        self.url = reverse('save_player_id')

    def test_unauthenticated_post_returns_401(self):
        resp = self.client.post(
            self.url, data=json.dumps({'player_id': 'abc'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json(), {'status': 'unauthorized'})

    def test_authenticated_get_returns_401(self):
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_post_saves_player_id(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            self.url, data=json.dumps({'player_id': 'player-99'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'success'})
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.player_id, 'player-99')

    def test_invalid_json_body_returns_400(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            self.url, data='not json', content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['message'], 'Invalid JSON body')

    def test_owner_without_restaurant_returns_404(self):
        plain = make_user('player_plain')
        self.client.force_login(plain)
        resp = self.client.post(
            self.url, data=json.dumps({'player_id': 'x'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()['message'], 'Restaurant not found')


class CheckNotificationsTests(TestCase):
    def setUp(self):
        self.owner = make_user('notif_owner')
        self.other = make_user('notif_other')
        self.url = reverse('check_notifications')

    def test_login_required(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_unread_notification_returned_and_marked_read(self):
        MerchantNotification.objects.create(
            merchant=self.owner, message='New order #7 received'
        )
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(), {'notify': True, 'message': 'New order #7 received'}
        )
        self.assertTrue(
            MerchantNotification.objects.get(
                message='New order #7 received'
            ).is_read
        )

    def test_other_merchants_notifications_are_ignored(self):
        MerchantNotification.objects.create(
            merchant=self.other, message='For someone else'
        )
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.json(), {'notify': False})

    def test_already_read_notifications_are_not_returned_again(self):
        MerchantNotification.objects.create(
            merchant=self.owner, message='Seen already', is_read=True
        )
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.json(), {'notify': False})


class MerchantRegisterViewTests(TestCase):
    def setUp(self):
        self.url = reverse('merchant_register')

    def valid_data(self, **overrides):
        data = {
            'username': 'view_merchant',
            'name': 'View Merchant',
            'number': '9876543210',
            'email': 'view_merchant@example.com',
            'password': 'Str0ngPass!',
            'retypePassword': 'Str0ngPass!',
        }
        data.update(overrides)
        return data

    def test_get_renders_registration_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'merchantRegister.html')
        self.assertIn('form', resp.context)

    def test_valid_post_creates_user_and_registration(self):
        resp = self.client.post(self.url, self.valid_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_register_success'))
        user = User.objects.get(username='view_merchant')
        self.assertEqual(user.email, 'view_merchant@example.com')
        registration = merchantRegistration.objects.get(username=user)
        self.assertEqual(registration.name, 'View Merchant')
        self.assertEqual(registration.number, Decimal('9876543210.0'))
        self.assertFalse(registration.is_approved)

    def test_duplicate_username_is_reported_as_form_error(self):
        make_user('taken_merchant')
        resp = self.client.post(
            self.url, self.valid_data(username='taken_merchant')
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('username', resp.context['form'].errors)

    def test_password_mismatch_is_reported_on_retype_field(self):
        resp = self.client.post(
            self.url, self.valid_data(retypePassword='Different1!')
        )
        self.assertEqual(resp.status_code, 200)
        errors = resp.context['form'].errors
        self.assertIn('retypePassword', errors)
        self.assertIn('Passwords do not match.', errors['retypePassword'])

    def test_integrity_error_during_user_creation_is_reported(self):
        with mock.patch.object(
            User.objects, 'create_user',
            side_effect=IntegrityError('duplicate key'),
        ):
            resp = self.client.post(self.url, self.valid_data())
        self.assertEqual(resp.status_code, 200)
        errors = resp.context['form'].errors
        self.assertIn('username', errors)
        self.assertIn(
            'Username already exists. Please choose a different one.',
            errors['username'],
        )
        self.assertEqual(merchantRegistration.objects.count(), 0)


class MerchantLoginViewTests(TestCase):
    def setUp(self):
        self.url = reverse('merchant_login')
        self.user = make_user('login_merchant')

    def test_get_renders_login_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'merchantLogin.html')

    def test_valid_credentials_redirect_to_post_login(self):
        resp = self.client.post(
            self.url, {'username': 'login_merchant', 'password': 'pw12345678'}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('post-login-redirect'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_wrong_password_re_renders_with_errors(self):
        resp = self.client.post(
            self.url, {'username': 'login_merchant', 'password': 'wrong'}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)


class PostLoginRedirectTests(TestCase):
    def setUp(self):
        self.url = reverse('post-login-redirect')
        self.owner = make_user('postlogin_owner')

    def test_login_required(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_missing_restaurant_routes_to_add_restaurant(self):
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('add_restaurant'))

    def test_approved_restaurant_routes_to_dashboard(self):
        make_restaurant(self.owner, name='Approved View Kitchen',
                        is_approved=True)
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_dashboard'))

    def test_unapproved_restaurant_sees_awaiting_page(self):
        make_restaurant(self.owner, name='Pending View Kitchen',
                        is_approved=False)
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'awaitingApproval.html')


class AddRestaurantViewTests(TestCase):
    def setUp(self):
        self.url = reverse('add_restaurant')
        self.owner = make_user('addrest_owner')
        make_registration(self.owner, approved=True)

    def valid_data(self, **overrides):
        data = {
            'name': 'New View Kitchen',
            'email': 'newview@example.com',
            'contact_number': '9876543210',
            'address': '2 Side Road',
            'city': 'Testville',
        }
        data.update(overrides)
        return data

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_user_without_registration_gets_404(self):
        plain = make_user('addrest_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_unapproved_registration_is_redirected_to_approval(self):
        pending = make_user('addrest_pending')
        make_registration(pending, approved=False)
        self.client.force_login(pending)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_approval'))

    def test_approved_get_renders_restaurant_form(self):
        self.client.force_login(self.owner)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'addRestaurant.html')
        self.assertIn('form', resp.context)

    def test_approved_post_creates_restaurant_owned_by_user(self):
        self.client.force_login(self.owner)
        resp = self.client.post(self.url, self.valid_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('restaurant_success'))
        restaurant = Restaurant.objects.get(name='New View Kitchen')
        self.assertEqual(restaurant.owner.pk, self.owner.pk)
        self.assertFalse(restaurant.is_approved)
        self.assertFalse(restaurant.is_available)

    def test_invalid_post_re_renders_with_errors(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            self.url, self.valid_data(contact_number='12345')
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('contact_number', resp.context['form'].errors)
        self.assertEqual(Restaurant.objects.count(), 0)


class MerchantDashboardTests(TestCase):
    def setUp(self):
        self.url = reverse('merchant_dashboard')
        self.owner = make_user('dash_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Dash Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_missing_restaurant_returns_404(self):
        plain = make_user('dash_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_unapproved_restaurant_redirects_to_awaiting(self):
        pending = make_user('dash_pending')
        make_restaurant(pending, name='Dash Pending', is_approved=False)
        self.client.force_login(pending)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('awaiting-approval'))

    def test_context_aggregates_orders_revenue_and_top_items(self):
        pending = make_order(self.restaurant, status='pending', total='100.00')
        make_order(self.restaurant, status='confirmed', total='150.00')
        make_order(self.restaurant, status='delivered', total='200.00')
        mid = make_order(self.restaurant, status='delivered', total='100.00')
        Order.objects.filter(pk=mid.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        old = make_order(self.restaurant, status='delivered', total='300.00')
        Order.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        burger = make_menu(self.restaurant, name='Dash Burger')
        add_order_item(pending, burger, quantity=5)

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'merchantDashboard.html')
        ctx = resp.context
        self.assertEqual(ctx['restaurant'].pk, self.restaurant.pk)
        self.assertEqual(len(ctx['Pending_orders']), 1)
        self.assertEqual(len(ctx['Confirmed_orders']), 1)
        self.assertEqual(ctx['total_orders_today'], 1)
        self.assertEqual(ctx['total_revenue_today'], Decimal('200.00'))
        self.assertEqual(ctx['net_revenue'], Decimal('168.00'))
        self.assertEqual(ctx['performance_rate'], Decimal('66.7'))
        self.assertEqual(len(ctx['top_items']), 1)
        self.assertEqual(ctx['top_items'][0]['total_quantity'], 5)
        self.assertEqual(
            json.loads(ctx['top_items_names']), ['Dash Burger']
        )
        self.assertEqual(
            json.loads(ctx['top_items_quantities']), [5]
        )
        self.assertEqual(
            ctx['order_item_quantities'][pending.pk][burger.pk], 5
        )

    def test_zero_orders_yield_zero_performance(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['performance_rate'], 0)
        self.assertEqual(resp.context['total_orders_today'], 0)

    def test_toggle_availability_flips_flag(self):
        self.assertFalse(self.restaurant.is_available)
        resp = self.client.post(self.url, {'toggle_availability': '1'})
        self.assertEqual(resp.status_code, 302)
        self.restaurant.refresh_from_db()
        self.assertTrue(self.restaurant.is_available)
        self.client.post(self.url, {'toggle_availability': '1'})
        self.restaurant.refresh_from_db()
        self.assertFalse(self.restaurant.is_available)


class MerchantOrderViewTests(TestCase):
    def setUp(self):
        self.url = reverse('merchant_orders')
        self.owner = make_user('orders_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Orders View Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_missing_restaurant_returns_404(self):
        plain = make_user('orders_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_context_buckets_exclude_active_from_history(self):
        make_order(self.restaurant, status='pending')
        make_order(self.restaurant, status='confirmed')
        make_order(self.restaurant, status='ready')
        make_order(self.restaurant, status='delivered')

        resp = self.client.get(self.url)
        ctx = resp.context
        self.assertEqual(len(ctx['pending_orders']), 1)
        self.assertEqual(len(ctx['confirmed_orders']), 1)
        history = list(ctx['order_history'])
        self.assertEqual(len(history), 2)
        self.assertEqual(
            {order.status for order in history}, {'ready', 'delivered'}
        )
        self.assertFalse(ctx['is_paginated'])

    def test_history_filters_by_order_date(self):
        make_order(self.restaurant, status='pending')
        yesterday = make_order(self.restaurant, status='delivered')
        Order.objects.filter(pk=yesterday.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        today_only = make_order(self.restaurant, status='delivered')

        resp = self.client.get(
            self.url,
            {'order_date': (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')},
        )
        history = list(resp.context['order_history'])
        self.assertEqual([order.pk for order in history], [yesterday.pk])
        self.assertNotIn(today_only.pk, [order.pk for order in history])
        self.assertEqual(resp.context['order_date'],
                         (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d'))

    def test_invalid_date_is_ignored(self):
        make_order(self.restaurant, status='delivered')
        resp = self.client.get(self.url, {'order_date': 'not-a-date'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['order_history']), 1)

    def test_history_is_paginated_at_ten(self):
        for index in range(11):
            make_order(self.restaurant, status='delivered')

        page1 = self.client.get(self.url)
        self.assertEqual(len(page1.context['order_history']), 10)
        self.assertTrue(page1.context['is_paginated'])

        page2 = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(page2.context['order_history']), 1)


class DownloadFilteredOrdersTests(TestCase):
    def setUp(self):
        self.url = reverse('download_filtered_orders')
        self.owner = make_user('csv_owner')
        self.restaurant = make_restaurant(
            self.owner, name='CSV Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)
        self.today = timezone.now().strftime('%Y-%m-%d')

    def test_missing_date_parameter_returns_400(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode(), 'Date parameter is missing.')

    def test_invalid_date_format_returns_400(self):
        resp = self.client.get(self.url, {'order_date': '01/02/2026'})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode(), 'Invalid date format.')

    def test_csv_contains_only_terminal_orders_with_items(self):
        delivered = make_order(
            self.restaurant, status='delivered', total='250.00'
        )
        delivered.customer_name = 'CSV Customer'
        delivered.save()
        item = make_menu(self.restaurant, name='CSV Burger')
        add_order_item(delivered, item, quantity=2)
        make_order(self.restaurant, status='pending')
        make_order(self.restaurant, status='confirmed')

        resp = self.client.get(self.url, {'order_date': self.today})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn(
            f'attachment; filename="orders_{self.today}.csv"',
            resp['Content-Disposition'],
        )
        body = resp.content.decode()
        self.assertIn('ID,Customer,Contact,Items,Total,Address,Status,Date', body)
        self.assertIn('CSV Customer', body)
        self.assertIn('CSV Burger', body)
        self.assertIn('Delivered', body)
        self.assertNotIn('View Customer', body)

    def test_owner_without_restaurant_gets_404(self):
        plain = make_user('csv_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url, {'order_date': self.today})
        self.assertEqual(resp.status_code, 404)


class ConfirmAndReadyTests(TestCase):
    def setUp(self):
        self.owner = make_user('confirm_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Confirm Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_confirming_non_pending_order_reports_error(self):
        order = make_order(self.restaurant, status='confirmed')
        resp = self.client.get(reverse('confirm_order', args=[order.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(any(
            'cannot be confirmed' in m for m in message_list(resp)
        ))
        order.refresh_from_db()
        self.assertEqual(order.status, 'confirmed')

    def test_ready_creates_pending_assignments_for_eligible_riders_only(self):
        approved = make_rider('mr_approved')
        unapproved = make_rider('mr_unapproved', approved=False)
        unavailable = make_rider('mr_unavailable', available=False)
        order = make_order(self.restaurant, status='confirmed')

        resp = self.client.get(reverse('mark_order_ready', args=[order.pk]))
        self.assertEqual(resp.status_code, 302)

        order.refresh_from_db()
        self.assertEqual(order.status, 'ready')
        self.assertEqual(
            OrderAssignment.objects.filter(
                order=order, rider=approved, status='pending'
            ).count(),
            1,
        )
        self.assertEqual(
            OrderAssignment.objects.filter(rider=unapproved).count(), 0
        )
        self.assertEqual(
            OrderAssignment.objects.filter(rider=unavailable).count(), 0
        )

    def test_ready_from_pending_reports_error(self):
        order = make_order(self.restaurant, status='pending')
        resp = self.client.get(reverse('mark_order_ready', args=[order.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(any(
            'cannot be marked ready' in m for m in message_list(resp)
        ))
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')


class MenuManagementTests(TestCase):
    def setUp(self):
        self.owner = make_user('menu_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Menu View Kitchen', is_approved=True
        )
        self.size = SizeCategory.objects.create(name='Menu View Size')
        self.item = make_menu(self.restaurant, name='Existing Item')
        self.client.force_login(self.owner)

    def test_add_item_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('add_item'))
        self.assertEqual(resp.status_code, 302)

    def test_add_item_get_renders_form(self):
        resp = self.client.get(reverse('add_item'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'add_menu.html')

    def test_add_item_post_creates_item_for_owner_restaurant(self):
        resp = self.client.post(reverse('add_item'), {
            'name': 'Fresh Item',
            'sizes_categories': self.size.pk,
            'category': 'Bowls',
            'description': 'Fresh',
            'price': '149.00',
            'available': True,
            'prep_time': 8,
            'veg_or_nonveg': 'veg',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('menu_dashboard'))
        item = RestaurantMenu.objects.get(name='Fresh Item')
        self.assertEqual(item.restaurant.pk, self.restaurant.pk)

    def test_add_item_invalid_post_re_renders_with_errors(self):
        resp = self.client.post(reverse('add_item'), {
            'name': 'No Price Item',
            'sizes_categories': self.size.pk,
            'category': 'Bowls',
            'price': '',
            'available': True,
            'prep_time': 8,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('price', resp.context['form'].errors)
        self.assertFalse(
            RestaurantMenu.objects.filter(name='No Price Item').exists()
        )

    def test_add_item_without_restaurant_returns_404(self):
        plain = make_user('menu_plain')
        self.client.force_login(plain)
        resp = self.client.post(reverse('add_item'), {
            'name': 'Ghost Item',
            'sizes_categories': self.size.pk,
            'category': 'Bowls',
            'price': '10.00',
            'available': True,
            'prep_time': 8,
        })
        self.assertEqual(resp.status_code, 404)

    def test_edit_item_foreign_item_returns_404(self):
        other = make_user('menu_other')
        other_restaurant = make_restaurant(other, name='Other Menu Kitchen')
        other_item = make_menu(other_restaurant, name='Foreign Item')
        resp = self.client.get(
            reverse('edit_menu_item', args=[other_item.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def test_edit_item_get_prefills_form(self):
        resp = self.client.get(
            reverse('edit_menu_item', args=[self.item.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'edit_item.html')
        self.assertEqual(resp.context['item'].pk, self.item.pk)
        self.assertEqual(resp.context['form'].initial['name'], 'Existing Item')

    def test_edit_item_post_updates_values(self):
        resp = self.client.post(
            reverse('edit_menu_item', args=[self.item.pk]),
            {
                'name': 'Renamed Item',
                'sizes_categories': self.size.pk,
                'category': 'Bowls',
                'description': 'Renamed',
                'price': '175.00',
                'available': True,
                'prep_time': 9,
                'veg_or_nonveg': 'nonveg',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Renamed Item')
        self.assertEqual(self.item.price, Decimal('175.00'))
        self.assertEqual(self.item.veg_or_nonveg, 'nonveg')

    def test_menu_dashboard_lists_items_and_categories(self):
        resp = self.client.get(reverse('menu_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'menu_list.html')
        self.assertEqual(len(resp.context['items']), 1)
        self.assertIn('Burgers', list(resp.context['categories']))
        self.assertFalse(resp.context['is_editing'])

    def test_menu_dashboard_name_search_filters(self):
        make_menu(self.restaurant, name='Pizza Special')
        resp = self.client.get(reverse('menu_dashboard'), {'q': 'pizza'})
        self.assertEqual(
            [item.name for item in resp.context['items']], ['Pizza Special']
        )

    def test_menu_dashboard_category_filter_is_exact(self):
        make_menu(self.restaurant, name='Dosa', category='South Indian')
        resp = self.client.get(
            reverse('menu_dashboard'), {'category': 'South Indian'}
        )
        self.assertEqual(
            [item.name for item in resp.context['items']], ['Dosa']
        )
        resp = self.client.get(
            reverse('menu_dashboard'), {'category': 'No Such'}
        )
        self.assertEqual(len(resp.context['items']), 0)

    def test_menu_dashboard_edit_param_enters_edit_mode(self):
        resp = self.client.get(
            reverse('menu_dashboard'), {'edit': self.item.pk}
        )
        self.assertTrue(resp.context['is_editing'])
        self.assertEqual(resp.context['item'].pk, self.item.pk)

    def test_menu_dashboard_edit_foreign_item_returns_404(self):
        other = make_user('menu_other2')
        other_restaurant = make_restaurant(other, name='Other Menu Kitchen2')
        other_item = make_menu(other_restaurant, name='Foreign Item2')
        resp = self.client.get(
            reverse('menu_dashboard'), {'edit': other_item.pk}
        )
        self.assertEqual(resp.status_code, 404)

    def test_menu_dashboard_post_creates_new_item(self):
        resp = self.client.post(reverse('menu_dashboard'), {
            'name': 'Created From Dashboard',
            'sizes_categories': self.size.pk,
            'category': 'Bowls',
            'description': '',
            'price': '120.00',
            'available': True,
            'prep_time': 6,
            'veg_or_nonveg': 'veg',
        })
        self.assertEqual(resp.status_code, 302)
        item = RestaurantMenu.objects.get(name='Created From Dashboard')
        self.assertEqual(item.restaurant.pk, self.restaurant.pk)

    def test_menu_dashboard_post_with_edit_id_updates_item(self):
        resp = self.client.post(
            reverse('menu_dashboard'),
            {
                'edit_id': str(self.item.pk),
                'name': 'Updated From Dashboard',
                'sizes_categories': self.size.pk,
                'category': 'Bowls',
                'description': '',
                'price': '130.00',
                'available': False,
                'prep_time': 7,
                'veg_or_nonveg': '',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Updated From Dashboard')
        self.assertEqual(self.item.price, Decimal('130.00'))
        self.assertFalse(self.item.available)


class BankAccountViewTests(TestCase):
    def setUp(self):
        self.owner = make_user('bankview_owner')
        self.restaurant = make_restaurant(self.owner, name='Bank View Kitchen')
        self.client.force_login(self.owner)
        self.approved = BankAccount.objects.create(
            merchant=self.owner,
            bank_name='Approved Bank',
            account_holder_name='Holder A',
            account_number='111111111111',
            ifsc_code='B1IN0000001',
            is_primary=True,
            is_approved=True,
        )
        self.pending = BankAccount.objects.create(
            merchant=self.owner,
            bank_name='Pending Bank',
            account_holder_name='Holder B',
            account_number='222222222222',
            ifsc_code='B2IN0000002',
        )

    def valid_data(self, **overrides):
        data = {
            'bank_name': 'Fresh Bank',
            'account_holder_name': 'Holder C',
            'account_number': '333333333333',
            'ifsc_code': 'B3IN0000003',
            'is_primary': False,
        }
        data.update(overrides)
        return data

    def test_list_splits_approved_and_pending(self):
        resp = self.client.get(reverse('bank_account_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'bank_account_list.html')
        ctx = resp.context
        self.assertEqual(len(ctx['accounts']), 2)
        self.assertEqual([a.pk for a in ctx['approved_accounts']],
                         [self.approved.pk])
        self.assertEqual([a.pk for a in ctx['pending_accounts']],
                         [self.pending.pk])

    def test_list_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('bank_account_list'))
        self.assertEqual(resp.status_code, 302)

    def test_add_get_renders_form(self):
        resp = self.client.get(reverse('add_bank_account'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'add_bank_account.html')

    def test_add_post_creates_account_for_request_user(self):
        resp = self.client.post(reverse('add_bank_account'), self.valid_data())
        self.assertEqual(resp.status_code, 302)
        account = BankAccount.objects.get(account_number='333333333333')
        self.assertEqual(account.merchant.pk, self.owner.pk)
        self.assertFalse(account.is_approved)

    def test_add_invalid_post_re_renders_with_errors(self):
        resp = self.client.post(reverse('add_bank_account'), {
            'bank_name': '', 'account_holder_name': '', 'account_number': '',
            'ifsc_code': '', 'is_primary': False,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('bank_name', resp.context['form'].errors)
        self.assertEqual(BankAccount.objects.count(), 2)

    def test_edit_foreign_account_returns_404(self):
        other = make_user('bankview_other')
        foreign = BankAccount.objects.create(
            merchant=other,
            bank_name='Foreign Bank',
            account_holder_name='Holder F',
            account_number='999999999999',
            ifsc_code='BFIN0000009',
        )
        resp = self.client.get(
            reverse('edit_bank_account', args=[foreign.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def test_edit_get_prefills_form(self):
        resp = self.client.get(
            reverse('edit_bank_account', args=[self.pending.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'edit_bank_account.html')
        self.assertEqual(
            resp.context['account'].pk, self.pending.pk
        )
        self.assertEqual(
            resp.context['form'].initial['bank_name'], 'Pending Bank'
        )

    def test_edit_post_updates_account(self):
        resp = self.client.post(
            reverse('edit_bank_account', args=[self.pending.pk]),
            self.valid_data(
                account_number='222222222222', bank_name='Renamed Bank'
            ),
        )
        self.assertEqual(resp.status_code, 302)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.bank_name, 'Renamed Bank')

    def test_delete_get_renders_confirmation_page(self):
        resp = self.client.get(
            reverse('delete_bank_account', args=[self.pending.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'confirm_bank_account_delete.html')

    def test_delete_post_removes_account(self):
        resp = self.client.post(
            reverse('delete_bank_account', args=[self.pending.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            BankAccount.objects.filter(pk=self.pending.pk).exists()
        )

    def test_delete_foreign_account_returns_404(self):
        other = make_user('bankview_other2')
        foreign = BankAccount.objects.create(
            merchant=other,
            bank_name='Foreign Bank 2',
            account_holder_name='Holder G',
            account_number='888888888888',
            ifsc_code='BFIN0000008',
        )
        resp = self.client.get(
            reverse('delete_bank_account', args=[foreign.pk])
        )
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(
            reverse('delete_bank_account', args=[foreign.pk])
        )
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(BankAccount.objects.filter(pk=foreign.pk).exists())


class PaymentSectionTests(TestCase):
    def setUp(self):
        self.url = reverse('merchant_payment_section')
        self.owner = make_user('payview_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Pay View Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_missing_restaurant_returns_404(self):
        plain = make_user('payview_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_context_computes_share_paid_and_pending(self):
        make_order(self.restaurant, status='delivered', total='100.00')
        make_order(self.restaurant, status='delivered', total='200.00')
        payment = MerchantPayment.objects.create(
            merchant=self.owner, restaurant=self.restaurant,
            amount_paid=Decimal('50.00'),
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'merchantPaymentSection.html')
        ctx = resp.context
        self.assertEqual(ctx['total_revenues'], Decimal('300.00'))
        self.assertEqual(ctx['weekly_revenue'], Decimal('300.00'))
        self.assertEqual(ctx['merchant_share'], Decimal('252.00'))
        self.assertEqual(ctx['weekly_merchant_share'], Decimal('252.00'))
        self.assertEqual(ctx['weekly_platform_share'], Decimal('48.00'))
        self.assertEqual(ctx['paid_amount'], Decimal('50.00'))
        self.assertEqual(ctx['pending_amount'], Decimal('202.00'))
        self.assertEqual(ctx['subscription_fee'], 1000)
        self.assertIn(payment.pk, [p.pk for p in ctx['payments']])

        earning = MerchantEarning.objects.get(
            merchant=self.owner, restaurant=self.restaurant
        )
        self.assertEqual(earning.net_sales, Decimal('300.00'))
        self.assertEqual(earning.weekly_sales, Decimal('300.00'))
        self.assertEqual(earning.amount_paid, Decimal('50.00'))
        self.assertEqual(earning.amount_pending, Decimal('202.00'))

    def test_weekly_figures_exclude_orders_older_than_seven_days(self):
        old = make_order(self.restaurant, status='delivered', total='300.00')
        Order.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        make_order(self.restaurant, status='delivered', total='100.00')

        resp = self.client.get(self.url)
        ctx = resp.context
        self.assertEqual(ctx['total_revenues'], Decimal('400.00'))
        self.assertEqual(ctx['weekly_revenue'], Decimal('100.00'))
        self.assertEqual(ctx['weekly_merchant_share'], Decimal('84.00'))

    def test_only_delivered_orders_are_counted(self):
        make_order(self.restaurant, status='pending', total='500.00')
        make_order(self.restaurant, status='confirmed', total='700.00')

        resp = self.client.get(self.url)
        ctx = resp.context
        self.assertEqual(ctx['total_revenues'], 0)
        self.assertEqual(ctx['merchant_share'], 0)
        self.assertEqual(ctx['pending_amount'], Decimal('0'))

    def test_repeated_visits_upsert_a_single_earning_record(self):
        make_order(self.restaurant, status='delivered', total='100.00')
        self.client.get(self.url)
        self.client.get(self.url)
        self.client.get(self.url)
        self.assertEqual(
            MerchantEarning.objects.filter(
                merchant=self.owner, restaurant=self.restaurant
            ).count(),
            1,
        )


class RevenueReportTests(TestCase):
    def setUp(self):
        self.url = reverse('merchant_revenue_report')
        self.owner = make_user('revenueview_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Revenue View Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_missing_restaurant_returns_404(self):
        plain = make_user('revenueview_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_context_values_and_chart_points(self):
        make_order(self.restaurant, status='delivered', total='100.00')
        old = make_order(self.restaurant, status='delivered', total='400.00')
        Order.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'revenue_report.html')
        ctx = resp.context
        self.assertEqual(ctx['total_revenue'], Decimal('420.00'))
        self.assertEqual(ctx['today_revenue'], Decimal('84.00'))
        self.assertEqual(ctx['week_revenue'], Decimal('420.00'))
        self.assertEqual(ctx['month_revenue'], Decimal('420.00'))
        labels = json.loads(ctx['chart_labels'])
        data = json.loads(ctx['chart_data'])
        self.assertEqual(len(labels), 30)
        self.assertEqual(len(data), 30)
        self.assertEqual(data[29], 100.0)
        self.assertEqual(data[19], 400.0)

    def test_pending_orders_are_excluded_everywhere(self):
        make_order(self.restaurant, status='pending', total='999.00')

        resp = self.client.get(self.url)
        ctx = resp.context
        self.assertEqual(ctx['total_revenue'], Decimal('0'))
        self.assertEqual(ctx['today_revenue'], Decimal('0.00'))
        data = json.loads(ctx['chart_data'])
        self.assertEqual(data[29], 0.0)


class OrderReportTests(TestCase):
    def setUp(self):
        self.url = reverse('order_report')
        self.owner = make_user('reportview_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Report View Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_owner_without_restaurant_gets_zero_counts(self):
        plain = make_user('reportview_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_orders'], 0)

    def test_window_aggregates_and_chart_counts(self):
        make_order(self.restaurant, status='pending', total='50.00')
        make_order(self.restaurant, status='delivered', total='100.00')
        mid = make_order(self.restaurant, status='delivered', total='200.00')
        Order.objects.filter(pk=mid.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        old = make_order(self.restaurant, status='delivered', total='300.00')
        Order.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=40)
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'order_reports.html')
        ctx = resp.context
        self.assertEqual(ctx['total_orders'], 4)
        self.assertEqual(ctx['total_revenue'], Decimal('650.00'))
        self.assertEqual(ctx['thirty_day_orders'], 3)
        self.assertEqual(ctx['thirty_day_revenue'], Decimal('350.00'))
        self.assertEqual(ctx['seven_day_orders'], 2)
        self.assertEqual(ctx['seven_day_revenue'], Decimal('150.00'))
        self.assertEqual(ctx['today_orders'], 1)
        self.assertEqual(ctx['today_revenue'], Decimal('100.00'))
        labels = json.loads(ctx['order_chart_labels'])
        data = json.loads(ctx['order_chart_data'])
        self.assertEqual(len(labels), 30)
        self.assertEqual(len(data), 30)
        self.assertEqual(data[29], 2)
        self.assertEqual(data[19], 1)


class CustomerFeedbackTests(TestCase):
    def setUp(self):
        self.url = reverse('customer_feedback')
        self.owner = make_user('feedbackview_owner')
        self.restaurant = make_restaurant(
            self.owner, name='Feedback View Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_missing_restaurant_returns_404(self):
        plain = make_user('feedbackview_plain')
        self.client.force_login(plain)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_reviews_are_limited_to_ten_by_default(self):
        for index in range(12):
            reviewer = make_user(f'fb_reviewer_{index}')
            Review.objects.create(
                restaurant=self.restaurant, user=reviewer,
                rating=5, comment=f'Review {index}',
            )

        resp = self.client.get(self.url)
        ctx = resp.context
        self.assertEqual(len(ctx['reviews']), 10)
        self.assertFalse(ctx['show_all_reviews'])

    def test_all_parameter_returns_every_review(self):
        for index in range(12):
            reviewer = make_user(f'fb2_reviewer_{index}')
            Review.objects.create(
                restaurant=self.restaurant, user=reviewer,
                rating=4, comment=f'Review {index}',
            )

        resp = self.client.get(self.url, {'all': '1'})
        ctx = resp.context
        self.assertEqual(len(ctx['reviews']), 12)
        self.assertTrue(ctx['show_all_reviews'])

    def test_only_this_restaurants_feedback_is_listed(self):
        order = make_order(self.restaurant, status='delivered')
        customer = order.user
        CustomerFeedback.objects.create(
            order=order, restaurant=self.restaurant, customer=customer,
            rating=5, comments='Tasty',
        )
        foreign = make_user('feedbackview_foreign')
        foreign_restaurant = make_restaurant(foreign, name='Foreign Feedback')
        foreign_order = make_order(foreign_restaurant, status='delivered')
        CustomerFeedback.objects.create(
            order=foreign_order, restaurant=foreign_restaurant,
            customer=foreign_order.user, rating=1, comments='Bad',
        )

        resp = self.client.get(self.url)
        ctx = resp.context
        self.assertEqual(len(ctx['feedbacks']), 1)
        self.assertEqual(ctx['feedbacks'][0].restaurant.pk,
                         self.restaurant.pk)
        self.assertEqual(len(ctx['reviews']), 0)


class MerchantSupportTests(TestCase):
    def setUp(self):
        self.url = reverse('support_portal')
        self.owner = make_user('supportview_owner')
        self.restaurant = make_restaurant(self.owner, name='Support Kitchen')
        self.client.force_login(self.owner)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_create_ticket_persists_ticket_and_initial_message(self):
        resp = self.client.post(self.url, {
            'create_ticket': '1',
            'subject': 'App crashes on open',
            'category': 'technical',
            'message': 'It crashes every time.',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('support_portal'))
        ticket = Ticket.objects.get(subject='App crashes on open')
        self.assertEqual(ticket.merchant.pk, self.owner.pk)
        self.assertEqual(ticket.status, 'open')
        self.assertEqual(ticket.messages.count(), 1)
        first = ticket.messages.first()
        self.assertEqual(first.sender.pk, self.owner.pk)
        self.assertEqual(first.message, 'It crashes every time.')
        self.assertTrue(any(
            f'Ticket created successfully with ID {ticket.ticket_id}' in m
            for m in message_list(resp)
        ))

    def test_invalid_create_re_renders_with_form_errors(self):
        resp = self.client.post(self.url, {
            'create_ticket': '1',
            'subject': '',
            'category': 'technical',
            'message': 'No subject given.',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('subject', resp.context['ticket_form'].errors)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_reply_appends_message_and_redirects_back_to_ticket(self):
        ticket = Ticket.objects.create(
            merchant=self.owner, subject='Existing issue',
            category='billing',
        )
        resp = self.client.post(
            f'{self.url}?ticket_id={ticket.ticket_id}',
            {'reply_ticket': '1', 'message': 'Any update?', 'image': ''},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            f'/merchant/support/?ticket_id={ticket.ticket_id}',
        )
        self.assertEqual(ticket.messages.count(), 1)
        self.assertTrue(any(
            'Reply sent successfully.' in m for m in message_list(resp)
        ))

    def test_reply_to_closed_ticket_is_rejected(self):
        ticket = Ticket.objects.create(
            merchant=self.owner, subject='Closed issue',
            category='general', status='closed',
        )
        resp = self.client.post(
            f'{self.url}?ticket_id={ticket.ticket_id}',
            {'reply_ticket': '1', 'message': 'Reopening?', 'image': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(
            'Cannot reply to a closed ticket.' in m
            for m in message_list(resp)
        ))
        self.assertEqual(ticket.messages.count(), 0)

    def test_foreign_ticket_id_falls_back_to_own_ticket(self):
        own = Ticket.objects.create(
            merchant=self.owner, subject='My ticket', category='general'
        )
        other = make_user('supportview_other')
        foreign = Ticket.objects.create(
            merchant=other, subject='Their ticket', category='general'
        )
        resp = self.client.get(
            self.url, {'ticket_id': foreign.ticket_id}
        )
        self.assertEqual(resp.context['selected_ticket'].pk, own.pk)

    def test_tickets_context_lists_only_own_tickets(self):
        Ticket.objects.create(
            merchant=self.owner, subject='Mine', category='general'
        )
        other = make_user('supportview_other2')
        Ticket.objects.create(
            merchant=other, subject='Theirs', category='general'
        )
        resp = self.client.get(self.url)
        subjects = [t.subject for t in resp.context['tickets']]
        self.assertEqual(subjects, ['Mine'])

    def test_get_with_existing_ticket_shows_its_messages(self):
        ticket = Ticket.objects.create(
            merchant=self.owner, subject='With messages',
            category='general'
        )
        TicketMessage.objects.create(
            ticket=ticket, sender=self.owner, message='Hello support'
        )
        resp = self.client.get(
            self.url, {'ticket_id': ticket.ticket_id}
        )
        self.assertEqual(resp.context['selected_ticket'].pk, ticket.pk)
        self.assertEqual(len(resp.context['messages']), 1)
        self.assertEqual(resp.context['messages'][0].message,
                         'Hello support')


class PasswordResetConfirmTests(TestCase):
    def setUp(self):
        self.user = make_user('resetview_merchant', email='resetview@example.com')

    def build_urls(self, user, token):
        uid = http.urlsafe_base64_encode(force_bytes(user.pk))
        return reverse('merchant-password-reset-confirm',
                       kwargs={'uidb64': uid, 'token': token})

    def test_valid_link_renders_confirm_page(self):
        token = default_token_generator.make_token(self.user)
        resp = self.client.get(self.build_urls(self.user, token))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['validlink'])

    def test_tampered_token_renders_invalid_link(self):
        token = default_token_generator.make_token(self.user)
        resp = self.client.get(self.build_urls(self.user, token + 'x'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['validlink'])

    def test_unknown_uid_renders_invalid_link(self):
        token = default_token_generator.make_token(self.user)
        uid = http.urlsafe_base64_encode(force_bytes(999999))
        resp = self.client.get(
            reverse('merchant-password-reset-confirm',
                    kwargs={'uidb64': uid, 'token': token})
        )
        self.assertFalse(resp.context['validlink'])

    def test_valid_post_sets_password_and_redirects_to_login(self):
        token = default_token_generator.make_token(self.user)
        resp = self.client.post(
            self.build_urls(self.user, token),
            {'password': 'BrandNewPass1!'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_login'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass1!'))
        self.assertFalse(self.user.check_password('pw12345678'))
        self.assertTrue(any(
            'Password reset successful.' in m for m in message_list(resp)
        ))
        self.assertTrue(
            self.client.login(username='resetview_merchant',
                              password='BrandNewPass1!')
        )


class ExportPdfTests(TestCase):
    def setUp(self):
        self.owner = make_user('pdfview_owner')
        self.restaurant = make_restaurant(
            self.owner, name='PDF View Kitchen', is_approved=True
        )
        self.client.force_login(self.owner)

    def test_export_payments_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('export_payments_pdf'))
        self.assertEqual(resp.status_code, 302)

    def test_export_payments_without_restaurant_returns_404(self):
        plain = make_user('pdfview_plain')
        self.client.force_login(plain)
        resp = self.client.get(reverse('export_payments_pdf'))
        self.assertEqual(resp.status_code, 404)

    def test_export_payments_renders_pdf_with_restaurant_name(self):
        MerchantPayment.objects.create(
            merchant=self.owner, restaurant=self.restaurant,
            amount_paid=Decimal('75.00'),
        )
        resp = self.client.get(reverse('export_payments_pdf'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(
            'attachment; filename="Payment_History_PDF View Kitchen.pdf"',
            resp['Content-Disposition'],
        )
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_export_payments_accepts_date_range_parameters(self):
        resp = self.client.get(reverse('export_payments_pdf'), {
            'start_date': timezone.now().strftime('%Y-%m-%d'),
            'end_date': timezone.now().strftime('%Y-%m-%d'),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_export_orders_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('export_orders_pdf'))
        self.assertEqual(resp.status_code, 302)

    def test_export_orders_filters_by_valid_date_range(self):
        inside = make_order(self.restaurant, status='delivered',
                            customer_name='InRange Customer')
        outside = make_order(self.restaurant, status='delivered',
                             customer_name='OutOfRange Customer')
        Order.objects.filter(pk=outside.pk).update(
            created_at=timezone.now() - timedelta(days=40)
        )
        captured = {}

        def capturing_render(template_name, context, *args, **kwargs):
            captured['orders'] = list(context['orders'])
            return real_render_to_string(template_name, context,
                                         *args, **kwargs)

        with mock.patch(
            'merchant_app.views.render_to_string',
            side_effect=capturing_render,
        ):
            resp = self.client.get(reverse('export_orders_pdf'), {
                'start_date': (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                'end_date': timezone.now().strftime('%Y-%m-%d'),
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertEqual(
            [order.pk for order in captured['orders']], [inside.pk]
        )

    def test_export_orders_with_unparseable_dates_returns_all_orders(self):
        make_order(self.restaurant, status='delivered')
        make_order(self.restaurant, status='pending')
        captured = {}

        def capturing_render(template_name, context, *args, **kwargs):
            captured['orders'] = list(context['orders'])
            return real_render_to_string(template_name, context,
                                         *args, **kwargs)

        with mock.patch(
            'merchant_app.views.render_to_string',
            side_effect=capturing_render,
        ):
            resp = self.client.get(reverse('export_orders_pdf'), {
                'start_date': 'not-a-date', 'end_date': 'also-bad',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(captured['orders']), 2)


class SendPushTests(TestCase):
    def test_empty_player_id_returns_false_without_request(self):
        from merchant_app.views import send_push_to_merchant
        with mock.patch('merchant_app.views.requests.post') as post:
            self.assertFalse(send_push_to_merchant('', 42))
            post.assert_not_called()

    def test_missing_api_key_returns_false_without_request(self):
        from merchant_app.views import send_push_to_merchant
        with mock.patch.dict(os.environ, {'ONESIGNAL_REST_API_KEY': ''}):
            with mock.patch('merchant_app.views.requests.post') as post:
                self.assertFalse(send_push_to_merchant('player-1', 42))
                post.assert_not_called()

    def test_successful_push_posts_expected_payload(self):
        from merchant_app.views import send_push_to_merchant
        with mock.patch.dict(os.environ, {
            'ONESIGNAL_REST_API_KEY': 'secret-key-123',
            'ONESIGNAL_APP_ID': 'app-id-456',
        }):
            with mock.patch('merchant_app.views.requests.post') as post:
                post.return_value = mock.Mock(ok=True)
                self.assertTrue(send_push_to_merchant('player-7', 99))
        post.assert_called_once()
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers']['Authorization'], 'secret-key-123')
        payload = json.loads(kwargs['data'])
        self.assertEqual(payload['app_id'], 'app-id-456')
        self.assertEqual(payload['include_player_ids'], ['player-7'])
        self.assertEqual(payload['headings']['en'], 'New Order Received')
        self.assertIn('#99', payload['contents']['en'])
        self.assertIn(settings.SITE_URL, payload['url'])
        self.assertIn(reverse('merchant_orders'), payload['url'])

    def test_request_exception_returns_false_and_logs_warning(self):
        import requests as requests_lib
        from merchant_app.views import send_push_to_merchant
        with mock.patch.dict(os.environ, {
            'ONESIGNAL_REST_API_KEY': 'secret-key-123',
        }):
            with mock.patch(
                'merchant_app.views.requests.post',
                side_effect=requests_lib.RequestException('offline'),
            ):
                with self.assertLogs('merchant_app.views',
                                     level='WARNING') as logs:
                    self.assertFalse(send_push_to_merchant('player-7', 5))
        self.assertTrue(any(
            'OneSignal push failed for order 5' in line
            for line in logs.output
        ))
