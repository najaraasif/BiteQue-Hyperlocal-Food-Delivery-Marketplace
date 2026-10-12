from decimal import Decimal
from unittest import mock

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory
from user_app.admin import (
    CustomerFeedbackAdmin,
    OrderAdmin,
    userRegistrationAdmin,
)
from user_app.models import CustomerFeedback, Order, OrderMenuItem, UserProfile


def make_restaurant(name='Admin Rest'):
    owner = User.objects.create_user(
        username=f'admin_owner_{name}', password='pw12345678'
    )
    return Restaurant.objects.create(
        owner=owner, name=name,
        email=f'{name}@example.com'.lower().replace(' ', ''),
        contact_number='9876543210', address='1 Road', city='Town',
    )


def make_menu(restaurant):
    size = SizeCategory.objects.create(name=f'Size-{restaurant.name}')
    return RestaurantMenu.objects.create(
        restaurant=restaurant, name=f'{restaurant.name} Special',
        category='Main Course', price=Decimal('120.00'),
        prep_time=15, sizes_categories=size,
    )


class AdminRegistrationTests(TestCase):
    def test_order_is_registered_with_the_custom_admin(self):
        self.assertIn(Order, admin.site._registry)
        self.assertIsInstance(admin.site._registry[Order], OrderAdmin)

    def test_customer_feedback_is_registered(self):
        self.assertIn(CustomerFeedback, admin.site._registry)
        self.assertIsInstance(
            admin.site._registry[CustomerFeedback], CustomerFeedbackAdmin
        )

    def test_user_profile_is_registered_with_default_admin(self):
        self.assertIn(UserProfile, admin.site._registry)

    def test_user_registration_admin_declares_expected_columns(self):
        self.assertEqual(
            userRegistrationAdmin.list_display,
            ['username', 'name', 'number', 'email', 'address', 'password'],
        )
        self.assertEqual(
            userRegistrationAdmin.list_filter, ['name', 'number']
        )

    def test_order_admin_configuration(self):
        model_admin = admin.site._registry[Order]
        self.assertIn('status', model_admin.list_filter)
        self.assertIn('customer_name', model_admin.search_fields)
        self.assertIn('js/geocode.js', model_admin.Media.js)
        self.assertEqual(
            model_admin.get_menu_items.short_description, 'Menu Items'
        )

    def test_customer_feedback_admin_configuration(self):
        model_admin = admin.site._registry[CustomerFeedback]
        self.assertEqual(
            model_admin.list_display,
            ['customer', 'rating', 'comments', 'created_at'],
        )
        self.assertIn('customer', model_admin.list_filter)


class AdminAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin_user', email='admin@example.com',
            password='pw12345678',
        )

    def test_admin_index_renders_for_staff(self):
        self.client.force_login(self.superuser)
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_visitors_are_redirected_to_login(self):
        for path in (
            '/admin/', '/admin/user_app/order/',
            '/admin/user_app/customerfeedback/',
        ):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/admin/login/', resp.url)

    def test_order_changelist_renders(self):
        self.client.force_login(self.superuser)
        resp = self.client.get('/admin/user_app/order/')
        self.assertEqual(resp.status_code, 200)

    def test_feedback_changelist_renders(self):
        self.client.force_login(self.superuser)
        resp = self.client.get('/admin/user_app/customerfeedback/')
        self.assertEqual(resp.status_code, 200)

    def test_profile_changelist_renders(self):
        self.client.force_login(self.superuser)
        resp = self.client.get('/admin/user_app/userprofile/')
        self.assertEqual(resp.status_code, 200)

    def test_staff_without_model_permissions_gets_denied(self):
        plain_staff = User.objects.create_user(
            username='plain_staff', password='pw12345678',
            is_staff=True,
        )
        self.client.force_login(plain_staff)
        resp = self.client.get('/admin/user_app/order/')
        self.assertEqual(resp.status_code, 403)


class OrderAdminBehaviorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='order_admin_user', password='pw12345678'
        )
        self.restaurant = make_restaurant()
        self.order = Order.objects.create(
            user=self.user, restaurant=self.restaurant,
            customer_name='Admin Customer', customer_contact='',
            landmark='', delivery_address='1 Road',
            special_instructions='',
        )
        self.model_admin = admin.site._registry[Order]

    def test_get_menu_items_joins_names(self):
        menu_a = make_menu(self.restaurant)
        size = SizeCategory.objects.create(name='Big Bowl')
        menu_b = RestaurantMenu.objects.create(
            restaurant=self.restaurant, name='Second Dish',
            category='Sides', price=Decimal('60.00'),
            prep_time=10, sizes_categories=size,
        )
        OrderMenuItem.objects.create(
            order=self.order, menu_item=menu_a, quantity=1,
            price=menu_a.price,
        )
        OrderMenuItem.objects.create(
            order=self.order, menu_item=menu_b, quantity=2,
            price=menu_b.price,
        )
        joined = self.model_admin.get_menu_items(self.order)
        self.assertEqual(joined, f'{menu_a.name}, Second Dish')

    def test_get_menu_items_is_empty_for_order_without_items(self):
        self.assertEqual(self.model_admin.get_menu_items(self.order), '')

    @mock.patch.object(Order, 'send_status_update')
    def test_save_model_recalculates_total_and_notifies_on_status_change(
        self, notify
    ):
        menu = make_menu(self.restaurant)
        OrderMenuItem.objects.create(
            order=self.order, menu_item=menu, quantity=2,
            price=menu.price,
        )
        self.order.total = Decimal('0.00')
        self.order.save()

        obj = Order.objects.get(pk=self.order.pk)
        obj.status = 'confirmed'

        form = mock.Mock()
        form.changed_data = ['status']
        request = mock.Mock()

        self.model_admin.save_model(request, obj, form, change=True)

        obj.refresh_from_db()
        self.assertEqual(obj.total, Decimal('240.00'))
        self.assertGreaterEqual(notify.call_count, 1)

    @mock.patch.object(Order, 'send_status_update')
    def test_save_model_without_status_change_does_not_notify(self, notify):
        obj = Order.objects.get(pk=self.order.pk)
        obj.delivery_address = '2 Road'

        form = mock.Mock()
        form.changed_data = ['delivery_address']
        request = mock.Mock()

        self.model_admin.save_model(request, obj, form, change=True)
        notify.assert_not_called()

    @mock.patch.object(Order, 'send_status_update')
    def test_create_through_admin_sends_exactly_one_notification(
        self, notify
    ):
        obj = Order(
            user=self.user, restaurant=self.restaurant,
            customer_name='Fresh', customer_contact='',
            landmark='', delivery_address='9 Road',
            special_instructions='', status='confirmed',
        )
        form = mock.Mock()
        form.changed_data = ['status']
        self.model_admin.save_model(mock.Mock(), obj, form, change=False)
        notify.assert_called_once()
        self.assertTrue(Order.objects.filter(customer_name='Fresh').exists())

    def test_order_change_form_embeds_maps_bootstrap(self):
        superuser = User.objects.create_superuser(
            username='maps_admin', password='pw12345678'
        )
        self.client.force_login(superuser)
        resp = self.client.get(
            reverse('admin:user_app_order_change', args=[self.order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'window.GOOGLE_MAPS_API_KEY')
        self.assertContains(resp, 'Use My Current Location')

    def test_order_changelist_lists_created_order(self):
        superuser = User.objects.create_superuser(
            username='list_admin', password='pw12345678'
        )
        self.client.force_login(superuser)
        resp = self.client.get('/admin/user_app/order/')
        self.assertContains(resp, 'Admin Customer')
