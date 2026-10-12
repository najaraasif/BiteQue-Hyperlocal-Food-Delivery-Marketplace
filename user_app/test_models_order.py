from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory

from .models import (
    CustomerFeedback,
    DELIVERY_PIN_MAX_ATTEMPTS,
    Order,
    OrderMenuItem,
)


def create_order(user, **kwargs):
    defaults = {
        'customer_name': 'Pat',
        'customer_contact': '',
        'landmark': 'Near park',
        'delivery_address': '1 Road',
        'special_instructions': '',
    }
    defaults.update(kwargs)
    return Order.objects.create(user=user, **defaults)


def make_restaurant(name='Model Kitchen'):
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
    )


def make_menu_item(restaurant, price='100.00', name='Test Burger'):
    size, _ = SizeCategory.objects.get_or_create(name=f'Regular {restaurant.name}')
    return RestaurantMenu.objects.create(
        restaurant=restaurant,
        name=name,
        category='Burgers',
        price=Decimal(price),
        prep_time=10,
        sizes_categories=size,
    )


class OrderTotalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='totbuyer', password='pw12345678')
        self.restaurant = make_restaurant('Total Kitchen')
        self.item_a = make_menu_item(self.restaurant, price='50.00', name='Burger')
        self.item_b = make_menu_item(self.restaurant, price='20.00', name='Fries')

    def test_calculate_total_sums_order_item_price_times_quantity(self):
        order = create_order(self.user, restaurant=self.restaurant)
        OrderMenuItem.objects.create(order=order, menu_item=self.item_a, quantity=3, price=self.item_a.price)
        OrderMenuItem.objects.create(order=order, menu_item=self.item_b, quantity=2, price=self.item_b.price)
        self.assertEqual(order.calculate_total(), Decimal('190.00'))

    def test_calculate_total_is_zero_without_items(self):
        order = create_order(self.user, restaurant=self.restaurant)
        self.assertEqual(order.calculate_total(), Decimal('0.00'))

    def test_order_items_take_precedence_over_legacy_cart_quantities(self):
        order = create_order(self.user, restaurant=self.restaurant)
        OrderMenuItem.objects.create(order=order, menu_item=self.item_a, quantity=2, price=self.item_a.price)
        order._cart_quantities = {str(self.item_a.id): 7}
        self.assertEqual(order.calculate_total(), Decimal('100.00'))

    def test_save_recomputes_total_from_order_items(self):
        order = create_order(self.user, restaurant=self.restaurant, total=Decimal('999.00'))
        OrderMenuItem.objects.create(order=order, menu_item=self.item_a, quantity=2, price=self.item_a.price)
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal('100.00'))

    def test_save_keeps_total_when_order_has_no_items(self):
        order = create_order(self.user, restaurant=self.restaurant, total=Decimal('77.00'))
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal('77.00'))

    def test_save_updates_final_total(self):
        order = create_order(
            self.user, restaurant=self.restaurant,
            total=Decimal('100.00'),
            item_gst=Decimal('3.00'),
            packaging_charges=Decimal('10.00'),
            distance_earning=Decimal('25.00'),
        )
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.final_total, Decimal('138.00'))

    def test_final_total_rounds_sub_cent_precision_half_even(self):
        order = create_order(
            self.user, restaurant=self.restaurant,
            total=Decimal('10.005'),
            item_gst=Decimal('0.00'),
            packaging_charges=Decimal('0.00'),
            distance_earning=Decimal('0.00'),
        )
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.final_total, Decimal('10.00'))

        order2 = create_order(
            self.user, restaurant=self.restaurant,
            total=Decimal('10.015'),
            item_gst=Decimal('0.00'),
            packaging_charges=Decimal('0.00'),
            distance_earning=Decimal('0.00'),
        )
        order2.save()
        order2.refresh_from_db()
        self.assertEqual(order2.final_total, Decimal('10.02'))

    def test_fresh_order_final_total_includes_default_packaging(self):
        order = create_order(self.user, restaurant=self.restaurant)
        order.refresh_from_db()
        self.assertEqual(order.final_total, Decimal('10.00'))

    def test_overall_sum_property_matches_final_total_components(self):
        order = create_order(
            self.user, restaurant=self.restaurant,
            total=Decimal('200.00'),
            item_gst=Decimal('6.00'),
            packaging_charges=Decimal('10.00'),
            distance_earning=Decimal('40.00'),
        )
        self.assertEqual(order.overall_sum, Decimal('256.00'))
        self.assertEqual(order.overall_sum, order.final_total)

    def test_order_str_is_id_and_customer_name(self):
        order = create_order(self.user, restaurant=self.restaurant)
        self.assertEqual(str(order), f'Order #{order.id} - Pat')

    def test_order_menu_item_unique_together(self):
        order = create_order(self.user, restaurant=self.restaurant)
        OrderMenuItem.objects.create(order=order, menu_item=self.item_a, quantity=1, price=self.item_a.price)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderMenuItem.objects.create(order=order, menu_item=self.item_a, quantity=2, price=self.item_a.price)

    def test_order_menu_item_delete_cascades_from_order(self):
        order = create_order(self.user, restaurant=self.restaurant)
        OrderMenuItem.objects.create(order=order, menu_item=self.item_a, quantity=1, price=self.item_a.price)
        order.delete()
        self.assertFalse(OrderMenuItem.objects.exists())

    def test_order_delete_cascades_from_user(self):
        order = create_order(self.user, restaurant=self.restaurant)
        self.user.delete()
        self.assertFalse(Order.objects.filter(pk=order.pk).exists())


class OrderStatusIndicatorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='statbuyer', password='pw12345678')
        self.restaurant = make_restaurant('Status Kitchen')

    def make(self, status):
        return create_order(self.user, restaurant=self.restaurant, status=status)

    def test_status_index_follows_pipeline_order(self):
        expected = {
            'pending': 1,
            'confirmed': 2,
            'ready': 3,
            'out_for_delivery': 4,
            'delivered': 5,
        }
        for status, index in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self.make(status).status_index, index)

    def test_status_index_unknown_status_is_zero(self):
        order = self.make('pending')
        order.status = 'cancelled'
        self.assertEqual(order.status_index, 0)

    def test_status_color_mapping(self):
        expected = {
            'pending': 'red',
            'confirmed': 'blue',
            'ready': 'yellow',
            'out_for_delivery': 'orange',
            'delivered': 'green',
        }
        for status, color in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self.make(status).status_color, color)

    def test_status_color_unknown_status_is_grey(self):
        order = self.make('pending')
        order.status = 'refunded'
        self.assertEqual(order.status_color, 'grey')


class DeliveryPinTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pinbuyer', password='pw12345678')
        self.restaurant = make_restaurant('Pin Kitchen')
        self.order = create_order(
            self.user, restaurant=self.restaurant, status='out_for_delivery'
        )

    def test_generate_delivery_pin_returns_digits_of_requested_length(self):
        pin = self.order.generate_delivery_pin(length=6)
        self.assertEqual(len(pin), 6)
        self.assertTrue(pin.isdigit())
        self.assertEqual(self.order.delivery_pin, pin)

    def test_generate_delivery_pin_stamps_time_and_resets_attempts(self):
        self.order.delivery_pin_attempts = 3
        before = timezone.now()
        self.order.generate_delivery_pin()
        self.assertGreaterEqual(self.order.delivery_pin_generated_at, before)
        self.assertEqual(self.order.delivery_pin_attempts, 0)

    def test_generate_delivery_pin_varies_between_calls(self):
        pins = {self.order.generate_delivery_pin() for _ in range(8)}
        self.assertGreater(len(pins), 1)

    def test_clear_delivery_pin_resets_all_pin_fields(self):
        self.order.generate_delivery_pin()
        self.order.delivery_pin_attempts = 2
        self.order.clear_delivery_pin()
        self.assertIsNone(self.order.delivery_pin)
        self.assertIsNone(self.order.delivery_pin_generated_at)
        self.assertEqual(self.order.delivery_pin_attempts, 0)

    def test_pin_expired_when_never_generated(self):
        self.order.delivery_pin_generated_at = None
        self.assertTrue(self.order.delivery_pin_is_expired())

    def test_pin_valid_window_within_ttl(self):
        self.order.delivery_pin_generated_at = timezone.now() - timedelta(minutes=5)
        self.assertFalse(self.order.delivery_pin_is_expired())

    def test_pin_expired_past_ttl(self):
        ttl = getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30)
        self.order.delivery_pin_generated_at = timezone.now() - timedelta(minutes=ttl + 1)
        self.assertTrue(self.order.delivery_pin_is_expired())

    def test_register_failure_below_cap_keeps_pin(self):
        self.order.generate_delivery_pin()
        invalidated = self.order.register_delivery_pin_failure()
        self.assertFalse(invalidated)
        self.assertEqual(self.order.delivery_pin_attempts, 1)
        self.assertIsNotNone(self.order.delivery_pin)

    def test_register_failure_at_cap_invalidates_pin(self):
        self.order.generate_delivery_pin()
        invalidated = False
        for _ in range(DELIVERY_PIN_MAX_ATTEMPTS):
            invalidated = self.order.register_delivery_pin_failure()
        self.assertTrue(invalidated)
        self.assertIsNone(self.order.delivery_pin)
        self.assertIsNone(self.order.delivery_pin_generated_at)
        self.assertEqual(self.order.delivery_pin_attempts, 0)

    def test_register_failure_persists_attempts_in_database(self):
        self.order.generate_delivery_pin()
        self.order.register_delivery_pin_failure()
        raw = Order.objects.values_list('delivery_pin_attempts', flat=True).get(pk=self.order.pk)
        self.assertEqual(raw, 1)

    def test_valid_pin_requires_out_for_delivery_status(self):
        self.order.generate_delivery_pin()
        self.order.status = 'confirmed'
        self.assertFalse(self.order.is_delivery_pin_valid(self.order.delivery_pin))

    def test_valid_pin_accepts_correct_pin_out_for_delivery(self):
        self.order.generate_delivery_pin()
        self.assertTrue(self.order.is_delivery_pin_valid(self.order.delivery_pin))

    def test_valid_pin_rejects_wrong_pin(self):
        pin = self.order.generate_delivery_pin()
        wrong = '9999' if pin != '9999' else '8888'
        self.assertFalse(self.order.is_delivery_pin_valid(wrong))

    def test_valid_pin_rejects_expired_pin(self):
        self.order.generate_delivery_pin()
        ttl = getattr(settings, 'DELIVERY_PIN_TTL_MINUTES', 30)
        Order.objects.filter(pk=self.order.pk).update(
            delivery_pin_generated_at=timezone.now() - timedelta(minutes=ttl + 1)
        )
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_delivery_pin_valid(self.order.delivery_pin))

    def test_valid_pin_rejects_when_pin_cleared(self):
        self.order.generate_delivery_pin()
        self.order.clear_delivery_pin()
        self.assertFalse(self.order.is_delivery_pin_valid('1234'))


class OrderSaveSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sigbuyer', password='pw12345678')
        self.restaurant = make_restaurant('Signal Kitchen')

    def make(self, **kwargs):
        return create_order(self.user, restaurant=self.restaurant, **kwargs)

    def test_status_change_triggers_notification_once(self):
        order = self.make(status='pending')
        with mock.patch.object(Order, 'send_status_update') as notify:
            order.status = 'confirmed'
            order.save()
            notify.assert_called_once()
            order.save()
            notify.assert_called_once()

    def test_create_triggers_notification_with_order_instance(self):
        with mock.patch.object(Order, 'send_status_update', autospec=True) as notify:
            order = self.make(status='pending')
            notify.assert_called_once()
            self.assertEqual(notify.call_args[0][0], order)

    def test_no_notification_thread_when_contact_empty(self):
        order = self.make(status='pending', customer_contact='')
        with mock.patch('user_app.models.threading.Thread') as thread_cls:
            order.send_status_update()
            thread_cls.assert_not_called()

    def test_notification_spawned_as_daemon_thread_for_known_status(self):
        order = self.make(status='pending', customer_contact='9876543210')
        with mock.patch('user_app.models.threading.Thread') as thread_cls:
            order.status = 'confirmed'
            order.save()
            thread_cls.assert_called_once()
            _, kwargs = thread_cls.call_args
            self.assertTrue(kwargs.get('daemon'))
            self.assertTrue(callable(kwargs.get('target')))
            thread_cls.return_value.start.assert_called_once()

    def test_unlisted_status_sends_no_notification(self):
        order = self.make(status='pending', customer_contact='9876543210')
        with mock.patch('user_app.models.threading.Thread') as thread_cls:
            order.send_status_update()
            thread_cls.assert_not_called()

    def capture_notify_target(self, order, new_status):
        captured = {}

        def factory(**kwargs):
            captured['target'] = kwargs['target']
            return mock.MagicMock()

        with mock.patch('user_app.models.threading.Thread', side_effect=factory):
            order.status = new_status
            order.save()
        return captured['target']

    def test_notify_uses_whatsapp_with_91_prefix_and_falls_back_to_sms(self):
        order = self.make(status='pending', customer_contact='+91 98765 43210')
        target = self.capture_notify_target(order, 'confirmed')

        with mock.patch('user_app.models.send_whatsapp', return_value=True) as wa, \
                mock.patch('user_app.models.send_sms') as sms:
            target()
            wa.assert_called_once()
            self.assertEqual(wa.call_args[0][0], '919876543210')
            self.assertIn('Order Confirmed', wa.call_args[0][1])
            self.assertIn('Order #', wa.call_args[0][1])
            sms.assert_not_called()

        with mock.patch('user_app.models.send_whatsapp', return_value=False) as wa, \
                mock.patch('user_app.models.send_sms') as sms:
            target()
            wa.assert_called_once()
            sms.assert_called_once()
            self.assertEqual(sms.call_args[0][0], '9876543210')
            self.assertEqual(sms.call_args[0][1], wa.call_args[0][1])

    def test_notify_normalizes_non_digit_contact_to_last_ten(self):
        order = self.make(status='pending', customer_contact='0091-98765-43210')
        target = self.capture_notify_target(order, 'ready')
        with mock.patch('user_app.models.send_whatsapp', return_value=True) as wa:
            target()
            self.assertEqual(wa.call_args[0][0], '919876543210')
            self.assertIn('Order Ready', wa.call_args[0][1])

    def test_notify_swallows_provider_exception(self):
        order = self.make(status='pending', customer_contact='9876543210')
        target = self.capture_notify_target(order, 'confirmed')
        with mock.patch('user_app.models.send_whatsapp', side_effect=RuntimeError('down')):
            with self.assertLogs('user_app.models', level='ERROR'):
                target()

    def test_out_for_delivery_message_reports_unknown_rider_without_assignment(self):
        order = self.make(status='pending', customer_contact='9876543210')
        target = self.capture_notify_target(order, 'out_for_delivery')
        with mock.patch('user_app.models.send_whatsapp', return_value=True) as wa:
            target()
            message = wa.call_args[0][1]
            self.assertIn('Order On The Way', message)
            self.assertIn('Rider: Unknown', message)
            self.assertIn('Contact: N/A', message)

    def test_delivered_message_contains_feedback_prompt(self):
        order = self.make(status='pending', customer_contact='9876543210')
        target = self.capture_notify_target(order, 'delivered')
        with mock.patch('user_app.models.send_whatsapp', return_value=True) as wa:
            target()
            self.assertIn('Enjoy your meal', wa.call_args[0][1])


class CustomerFeedbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='fbuyer', password='pw12345678')
        self.restaurant = make_restaurant('Feedback Kitchen')
        self.order = create_order(self.user, restaurant=self.restaurant, status='delivered')

    def make_feedback(self, **kwargs):
        defaults = {
            'order': self.order,
            'restaurant': self.restaurant,
            'customer': self.user,
        }
        defaults.update(kwargs)
        return CustomerFeedback.objects.create(**defaults)

    def test_str_includes_username_and_order(self):
        fb = self.make_feedback()
        self.assertEqual(str(fb), f'fbuyer - Order #{self.order.id}')

    def test_overall_rating_averages_all_present_subratings(self):
        fb = self.make_feedback(
            rating=4, item_quality=5, delivery_experience=3,
            restaurant_rating=4, rider_rating=5,
        )
        self.assertEqual(fb.overall_rating, 4.2)

    def test_overall_rating_skips_missing_subratings(self):
        fb = self.make_feedback(item_quality=5, rider_rating=4)
        self.assertEqual(fb.overall_rating, 4.5)

    def test_overall_rating_includes_per_item_ratings(self):
        fb = self.make_feedback(rating=5, item_ratings={11: 3, 12: 4})
        self.assertEqual(fb.overall_rating, 4.0)

    def test_overall_rating_none_when_nothing_rated(self):
        fb = self.make_feedback()
        self.assertIsNone(fb.overall_rating)

    def test_zero_valued_item_rating_counts_as_valid(self):
        fb = self.make_feedback(rating=4, item_ratings={11: 0})
        self.assertEqual(fb.overall_rating, 2.0)

    def test_one_feedback_per_order_enforced(self):
        self.make_feedback()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CustomerFeedback.objects.create(
                    order=self.order, restaurant=self.restaurant, customer=self.user,
                )

    def test_delete_feedback_keeps_order(self):
        fb = self.make_feedback()
        fb.delete()
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())


class UserProfileSignalTests(TestCase):
    def test_profile_created_with_user(self):
        user = User.objects.create_user(username='probuyer', password='pw12345678')
        self.assertTrue(hasattr(user, 'userprofile'))
        self.assertIsNone(user.userprofile.phone_number)

    def test_existing_profile_reused_not_duplicated(self):
        user = User.objects.create_user(username='probuyer2', password='pw12345678')
        user.save()
        from .models import UserProfile
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)

    def test_full_save_also_saves_profile(self):
        user = User.objects.create_user(username='probuyer3', password='pw12345678')
        with mock.patch('user_app.models.UserProfile.save') as profile_save:
            user.save()
            profile_save.assert_called()

    def test_update_fields_save_does_not_touch_profile(self):
        user = User.objects.create_user(username='probuyer4', password='pw12345678')
        profile = user.userprofile
        with mock.patch('user_app.models.UserProfile.save') as profile_save:
            user.save(update_fields=['last_login'])
            profile_save.assert_not_called()

    def test_profile_str_is_users_profile(self):
        user = User.objects.create_user(username='probuyer5', password='pw12345678')
        self.assertEqual(str(user.userprofile), "probuyer5's Profile")

    def test_profile_whatsapp_consent_defaults_false(self):
        user = User.objects.create_user(username='probuyer6', password='pw12345678')
        self.assertFalse(user.userprofile.whatsapp_consent)
