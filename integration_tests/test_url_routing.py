from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import NoReverseMatch, resolve, reverse

NAMED_ROUTES = [
    ('home', {}, '/'),
    ('category_items', {'category_slug': 'burgers'}, '/category/burgers/'),
    ('user_registration', {}, '/user-registration/'),
    ('registration_success', {}, '/registration-success/'),
    ('about', {}, '/about/'),
    ('contact', {}, '/contact-us/'),
    ('privacy', {}, '/privacy/'),
    ('careers', {}, '/careers/'),
    ('terms-and-conditions', {}, '/terms-and-conditions/'),
    ('responsible-disclosure', {}, '/Responsible-disclosure/'),
    ('add-restaurant', {}, '/add-restaurant/'),
    ('ride-with-us', {}, '/ride-with-us/'),
    ('user_view_menu', {'restaurant_id': 5}, '/restaurant/5/menu/'),
    ('user_login', {}, '/user-login/'),
    ('user-dashboard', {}, '/user/home/'),
    ('dashboard_home', {}, '/user/home/'),
    ('order_detail', {'order_id': 9}, '/orders/9/'),
    ('profile-section', {}, '/user/profile'),
    ('user_active_orders', {}, '/user/active/'),
    ('order_user_history', {}, '/user/history/'),
    ('write_feedback', {'order_id': 3}, '/order/3/feedback/'),
    ('user_support_portal', {}, '/user/support/'),
    ('view_cart', {}, '/user/cart/'),
    ('add_to_cart', {'item_id': 7}, '/user/cart/add/7/'),
    ('remove_from_cart', {'item_id': 7}, '/user/cart/remove/7/'),
    ('change_quantity', {'item_id': 7, 'action': 'increase'},
     '/user/cart/7/increase/'),
    ('order_now', {'item_id': 7}, '/order-now/7/'),
    ('user_logout', {}, '/logout/'),
    ('checkout', {}, '/checkout/'),
    ('order_confirmation', {'order_id': 4}, '/order-confirmation/4/'),
    ('payment_success', {}, '/payment/success/'),
    ('submit_review', {'restaurant_id': 2}, '/restaurant/2/review/'),
    ('profile', {}, '/profile/'),
    ('update_profile', {}, '/profile/update/'),
    ('update_avatar', {}, '/profile/update-avatar/'),
    ('change_password', {}, '/change-password/'),
    ('contact-form', {}, '/contact-form/'),
    ('clear_alert_flag', {}, '/clear-alert-flag/'),
    ('download_invoice', {'order_id': 6}, '/orders/6/invoice/'),

    ('rider:dashboard', {}, '/dashboard/'),
    ('rider:registration', {}, '/registration/'),
    ('rider:registration_success', {}, '/registration_success/'),
    ('rider:rider-login', {}, '/rider-login/'),
    ('rider:update_availability', {}, '/update-availability/'),
    ('rider:accept_order', {'order_id': 8}, '/orders/accept/8/'),
    ('rider:logout', {}, '/logout/'),
    ('rider:earnings', {}, '/earnings/'),
    ('rider:mark_delivered', {'order_id': 8}, '/orders/deliver/8/'),
    ('rider:bank_details_list', {}, '/bank-details/'),
    ('rider:delete_bank_account', {'account_id': 1},
     '/bank-details/delete/1/'),
    ('rider:set_primary_bank_account', {'account_id': 1},
     '/bank-details/set-primary/1/'),
    ('rider:rider_order_detail', {'order_id': 8}, '/rider/order/8/'),
    ('rider:accept_order_assignment_action', {'order_id': 8},
     '/rider/order/8/accept/'),
    ('rider:password_reset', {}, '/password-reset/'),
    ('rider:password_reset_done', {}, '/password-reset/done/'),
    ('rider:password_reset_complete', {}, '/password-reset-complete/'),
    ('rider:earning_details', {'earning_id': 2},
     '/earnings/details/2/'),
    ('rider:order_earning_details', {'order_id': 8},
     '/order-details/8/'),

    ('merchant_register', {}, '/merchant-register/'),
    ('merchant_register_success', {}, '/merchant-register/success/'),
    ('merchant_login', {}, '/merchant-login/'),
    ('merchant_approval', {}, '/merchant-approval/'),
    ('merchant_logout', {}, '/merchant-logout/'),
    ('post-login-redirect', {}, '/restaurant-status/'),
    ('add_restaurant', {}, '/add-restaurant'),
    ('restaurant_success', {}, '/merchant-dashboard/restaurant-success/'),
    ('awaiting-approval', {}, '/awaiting-approval/'),
    ('merchant_dashboard', {}, '/merchant-dashboard/'),
    ('save_player_id', {}, '/save-player-id/'),
    ('merchant_orders', {}, '/merchant/orders/'),
    ('confirm_order', {'order_id': 11}, '/merchant/orders/confirm/11/'),
    ('mark_order_ready', {'order_id': 11}, '/merchant/orders/ready/11/'),
    ('download_filtered_orders', {}, '/merchant/orders/download/'),
    ('menu_dashboard', {}, '/merchant-dashboard/menu/'),
    ('add_item', {}, '/menu/add/'),
    ('edit_menu_item', {'item_id': 4}, '/menu/edit/4/'),
    ('bank_account_list', {}, '/merchant/bank-accounts/'),
    ('add_bank_account', {}, '/merchant/bank-accounts/add/'),
    ('edit_bank_account', {'account_id': 2},
     '/merchant/bank-accounts/edit/2/'),
    ('delete_bank_account', {'account_id': 2},
     '/merchant/bank-accounts/delete/2/'),
    ('merchant_payment_section', {}, '/merchant/payments/'),
    ('export_payments_pdf', {}, '/merchant/payments/export/'),
    ('export_orders_pdf', {}, '/merchant/payments/export-orders'),
    ('merchant_revenue_report', {}, '/merchant/revenue-report/'),
    ('order_report', {}, '/merchant/order-report/'),
    ('customer_feedback', {}, '/merchant/feedbacks/'),
    ('support_portal', {}, '/merchant/support/'),
    ('check_notifications', {}, '/merchant/check_notifications/'),
    ('merchant-password-reset', {}, '/merchant/reset-password/'),
    ('password_reset_sent', {}, '/merchant/reset-sent/'),
]

ANONYMOUS_200 = [
    'home', 'about', 'contact', 'privacy', 'careers',
    'terms-and-conditions', 'responsible-disclosure', 'add-restaurant',
    'ride-with-us', 'user_registration', 'registration_success',
    'user_login',
    ('user_view_menu', {'restaurant_id': 1}),
    ('category_items', {'category_slug': 'burgers'}),
    'rider:registration', 'rider:registration_success',
    'rider:rider-login', 'rider:password_reset',
    'rider:password_reset_done', 'rider:password_reset_complete',
    'merchant_register', 'merchant_register_success', 'merchant_login',
    'merchant_approval', 'password_reset_sent',
    'merchant-password-reset',
]

ANONYMOUS_302 = [
    'checkout', 'user-dashboard', 'order_detail', 'profile-section',
    'user_active_orders', 'order_user_history', 'write_feedback',
    'user_support_portal', 'profile', 'update_profile', 'update_avatar',
    'change_password', 'order_confirmation', 'download_invoice',
    'submit_review',
    'rider:dashboard', 'rider:earnings', 'rider:bank_details_list',
    'rider:rider_order_detail', 'rider:earning_details',
    'rider:order_earning_details', 'rider:mark_delivered',
    'merchant_dashboard', 'merchant_orders', 'support_portal',
    'check_notifications', 'merchant_payment_section',
    'merchant_revenue_report', 'order_report', 'customer_feedback',
    'menu_dashboard', 'add_item', 'bank_account_list',
    'post-login-redirect', 'add_restaurant',
]


class NamedRouteTableTests(TestCase):
    def test_every_named_route_reverses_to_the_expected_path(self):
        for entry in NAMED_ROUTES:
            name, kwargs, expected = entry
            with self.subTest(name=name):
                self.assertEqual(reverse(name, kwargs=kwargs), expected)

    def test_every_reversed_path_resolves_back_to_a_view(self):
        for entry in NAMED_ROUTES:
            name, kwargs, _ = entry
            with self.subTest(name=name):
                match = resolve(reverse(name, kwargs=kwargs))
                self.assertIsNotNone(match)
                self.assertTrue(callable(match.func) or hasattr(
                    match.func, 'cls'  # class-based views
                ))

    def test_resolve_preserves_the_path_kwargs(self):
        cases = [
            ('order_detail', {'order_id': 42}),
            ('rider:mark_delivered', {'order_id': 42}),
            ('confirm_order', {'order_id': 42}),
            ('change_quantity', {'item_id': 7, 'action': 'decrease'}),
        ]
        for name, kwargs in cases:
            with self.subTest(name=name):
                match = resolve(reverse(name, kwargs=kwargs))
                for key, value in kwargs.items():
                    self.assertEqual(str(match.kwargs[key]), str(value))

    def test_unknown_names_fail_to_reverse(self):
        with self.assertRaises(NoReverseMatch):
            reverse('definitely_not_a_route')

    def test_key_views_bind_to_the_expected_callables(self):
        expectations = [
            ('home', 'home'),
            ('checkout', 'checkout'),
            ('payment_success', 'payment_success'),
            ('merchant_dashboard', 'merchant_dashboard'),
            ('rider:dashboard', 'rider_dashboard'),
            ('save_player_id', 'save_player_id'),
        ]
        for name, func_name in expectations:
            with self.subTest(name=name):
                match = resolve(reverse(name))
                self.assertEqual(match.func.__name__, func_name)

    def test_duplicate_user_dashboard_names_share_one_path(self):
        self.assertEqual(reverse('user-dashboard'), reverse('dashboard_home'))


class AnonymousAccessTests(TestCase):
    def setUp(self):
        from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory
        owner = User.objects.create_user(
            username='route_owner', password='pw12345678'
        )
        restaurant = Restaurant.objects.create(
            owner=owner,
            name='Route Kitchen',
            email='route@example.com',
            contact_number='9876543210',
            address='1 Road',
            city='Town',
            image='restaurantImages/route.jpg',
            is_approved=True,
        )
        size, _ = SizeCategory.objects.get_or_create(name='Route Size')
        RestaurantMenu.objects.create(
            restaurant=restaurant,
            name='Route Burger',
            category='Burgers',
            price=100,
            prep_time=5,
            sizes_categories=size,
            image='menu_images/route.jpg',
        )
        self.client = self.client_class()

    def resolve_view(self, entry):
        if isinstance(entry, tuple):
            name, kwargs = entry
        else:
            name, kwargs = entry, {}
        return name, resolve(reverse(name, kwargs=kwargs))

    def test_public_pages_render_for_anonymous_visitors(self):
        for entry in ANONYMOUS_200:
            name, match = self.resolve_view(entry)
            with self.subTest(name=name):
                resp = self.client.get(
                    reverse(name, kwargs=(
                        match.kwargs if isinstance(entry, tuple) else {}
                    ))
                )
                self.assertEqual(resp.status_code, 200)

    def test_member_pages_redirect_anonymous_visitors(self):
        for name in ANONYMOUS_302:
            with self.subTest(name=name):
                kwargs = {}
                if name == 'submit_review':
                    kwargs = {'restaurant_id': 1}
                elif name in ('order_detail', 'order_confirmation',
                              'download_invoice', 'write_feedback',
                              'rider:mark_delivered',
                              'rider:rider_order_detail',
                              'rider:order_earning_details'):
                    kwargs = {'order_id': 1}
                elif name == 'rider:earning_details':
                    kwargs = {'earning_id': 1}
                resp = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(resp.status_code, 302)

    def test_payment_success_still_redirects_for_anonymous(self):
        resp = self.client.get(reverse('payment_success'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))

    def test_rider_availability_endpoint_returns_401_json(self):
        resp = self.client.post(reverse('rider:update_availability'))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['status'], 'error')

    def test_save_player_id_returns_401_json_for_anonymous(self):
        resp = self.client.post(reverse('save_player_id'))
        self.assertEqual(resp.status_code, 401)

    def test_admin_requires_staff_login(self):
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp.url)
