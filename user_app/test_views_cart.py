from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory

from .models import Order


def make_restaurant(name='Cart Kitchen'):
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


class AddToCartTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant, price='150.00')
        self.other_restaurant = make_restaurant('Other Cart Kitchen')
        self.other_item = make_menu_item(self.other_restaurant, name='Other Burger', price='90.00')
        self.user = User.objects.create_user(username='cartuser', password='pw12345678')
        self.client.force_login(self.user)

    def add(self, item, referer=None, **extra):
        kwargs = dict(extra)
        if referer is not None:
            kwargs['HTTP_REFERER'] = referer
        return self.client.get(reverse('add_to_cart', args=[item.id]), **kwargs)

    def cart(self):
        return self.client.session.get('cart', {})

    def test_new_item_added_with_quantity_one(self):
        self.add(self.item)
        self.assertEqual(self.cart(), {str(self.item.id): {'quantity': 1}})

    def test_repeated_add_increments_quantity(self):
        self.add(self.item)
        self.add(self.item)
        self.assertEqual(self.cart()[str(self.item.id)]['quantity'], 2)

    def test_add_two_items_from_same_restaurant(self):
        sibling = make_menu_item(self.restaurant, name='Second Burger')
        self.add(self.item)
        self.add(sibling)
        self.assertEqual(len(self.cart()), 2)
        self.assertEqual(self.cart()[str(sibling.id)]['quantity'], 1)

    def test_cross_restaurant_add_is_rejected_and_keeps_original_cart(self):
        self.add(self.item)
        self.add(self.other_item, referer='/menu/1/')
        self.assertEqual(list(self.cart()), [str(self.item.id)])

    def test_cross_restaurant_add_sets_alert_flag(self):
        self.add(self.item)
        resp = self.add(self.other_item, referer='/menu/1/')
        self.assertTrue(self.client.session['show_single_restaurant_alert'])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/menu/1/')

    def test_cross_restaurant_add_without_referer_redirects_home(self):
        self.add(self.item)
        resp = self.add(self.other_item)
        self.assertEqual(resp.url, '/')

    def test_successful_add_does_not_set_alert_flag(self):
        self.add(self.item)
        self.assertNotIn('show_single_restaurant_alert', self.client.session)

    def test_add_unknown_item_returns_404(self):
        resp = self.client.get(reverse('add_to_cart', args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_alert_flag_not_set_when_cart_already_from_same_restaurant(self):
        self.add(self.item)
        sibling = make_menu_item(self.restaurant, name='Third Burger')
        self.add(sibling, referer='/menu/2/')
        self.assertNotIn('show_single_restaurant_alert', self.client.session)


class ViewCartTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant, price='150.00')
        self.fries = make_menu_item(self.restaurant, name='Fries', price='50.00')
        self.user = User.objects.create_user(username='viewcartuser', password='pw12345678')
        self.client.force_login(self.user)

    def set_cart(self, cart):
        session = self.client.session
        session['cart'] = cart
        session.save()

    def test_empty_cart_renders_with_zero_total(self):
        resp = self.client.get(reverse('view_cart'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'your_cart.html')
        self.assertEqual(resp.context['cart_items'], [])
        self.assertEqual(resp.context['total'], 0)

    def test_cart_items_carry_quantity_and_line_subtotal(self):
        self.set_cart({str(self.item.id): {'quantity': 2}})
        resp = self.client.get(reverse('view_cart'))
        entries = resp.context['cart_items']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['quantity'], 2)
        self.assertEqual(entries[0]['subtotal'], Decimal('300.00'))
        self.assertEqual(entries[0]['item'].id, self.item.id)
        self.assertEqual(resp.context['total'], Decimal('300.00'))

    def test_multiple_lines_sum_to_total(self):
        self.set_cart({
            str(self.item.id): {'quantity': 1},
            str(self.fries.id): {'quantity': 3},
        })
        resp = self.client.get(reverse('view_cart'))
        self.assertEqual(resp.context['total'], Decimal('300.00'))
        self.assertEqual(len(resp.context['cart_items']), 2)

    def test_quantity_defaults_to_one_when_key_missing(self):
        self.set_cart({str(self.item.id): {}})
        resp = self.client.get(reverse('view_cart'))
        self.assertEqual(resp.context['cart_items'][0]['quantity'], 1)
        self.assertEqual(resp.context['total'], Decimal('150.00'))

    def test_cart_referencing_deleted_item_returns_404(self):
        self.set_cart({str(self.item.id): {'quantity': 1}})
        RestaurantMenu.objects.all().delete()
        resp = self.client.get(reverse('view_cart'))
        self.assertEqual(resp.status_code, 404)


class RemoveFromCartTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant)
        self.fries = make_menu_item(self.restaurant, name='Fries', price='50.00')
        self.user = User.objects.create_user(username='removeuser', password='pw12345678')
        self.client.force_login(self.user)

    def set_cart(self, cart):
        session = self.client.session
        session['cart'] = cart
        session.save()

    def test_remove_deletes_only_requested_item(self):
        self.set_cart({
            str(self.item.id): {'quantity': 1},
            str(self.fries.id): {'quantity': 1},
        })
        resp = self.client.get(reverse('remove_from_cart', args=[self.item.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('view_cart'))
        self.assertEqual(list(self.client.session['cart']), [str(self.fries.id)])

    def test_remove_absent_item_is_a_no_op(self):
        self.set_cart({str(self.fries.id): {'quantity': 1}})
        self.client.get(reverse('remove_from_cart', args=[self.item.id]))
        self.assertEqual(list(self.client.session['cart']), [str(self.fries.id)])

    def test_remove_from_empty_cart_still_redirects(self):
        resp = self.client.get(reverse('remove_from_cart', args=[self.item.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session.get('cart', {}), {})


class ChangeQuantityTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant)
        self.user = User.objects.create_user(username='qtyuser', password='pw12345678')
        self.client.force_login(self.user)

    def set_qty(self, quantity):
        session = self.client.session
        session['cart'] = {str(self.item.id): {'quantity': quantity}}
        session.save()

    def change(self, action):
        return self.client.get(
            reverse('change_quantity', args=[self.item.id, action])
        )

    def qty(self):
        return self.client.session['cart'][str(self.item.id)]['quantity']

    def test_increase_adds_one(self):
        self.set_qty(2)
        self.change('increase')
        self.assertEqual(self.qty(), 3)

    def test_decrease_removes_one(self):
        self.set_qty(3)
        self.change('decrease')
        self.assertEqual(self.qty(), 2)

    def test_decrease_below_one_deletes_entry(self):
        self.set_qty(1)
        resp = self.change('decrease')
        self.assertEqual(resp.url, reverse('view_cart'))
        self.assertEqual(self.client.session['cart'], {})

    def test_unknown_action_leaves_quantity_alone(self):
        self.set_qty(2)
        self.change('multiply')
        self.assertEqual(self.qty(), 2)

    def test_unknown_action_does_not_remove_entry(self):
        self.set_qty(1)
        self.change('sideways')
        self.assertIn(str(self.item.id), self.client.session['cart'])

    def test_item_not_in_cart_is_no_op(self):
        session = self.client.session
        session['cart'] = {}
        session.save()
        resp = self.change('increase')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session['cart'], {})


class ClearAlertFlagTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alertuser', password='pw12345678')
        self.client.force_login(self.user)

    def test_post_clears_flag(self):
        session = self.client.session
        session['show_single_restaurant_alert'] = True
        session.save()
        resp = self.client.post(reverse('clear_alert_flag'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'ok'})
        self.assertNotIn('show_single_restaurant_alert', self.client.session)

    def test_post_without_flag_still_succeeds(self):
        resp = self.client.post(reverse('clear_alert_flag'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'ok'})

    def test_get_is_not_allowed(self):
        resp = self.client.get(reverse('clear_alert_flag'))
        self.assertEqual(resp.status_code, 405)


class OrderNowTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.item = make_menu_item(self.restaurant)
        self.second = make_menu_item(self.restaurant, name='Second Burger')
        self.user = User.objects.create_user(username='ordernowuser', password='pw12345678')

    def test_login_required(self):
        resp = self.client.get(reverse('order_now', args=[self.item.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('user_login'), resp.url)
        self.assertIn('next=', resp.url)

    def test_replaces_existing_cart_with_single_item(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['cart'] = {str(self.second.id): {'quantity': 5}}
        session.save()
        resp = self.client.get(reverse('order_now', args=[self.item.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assertEqual(
            self.client.session['cart'],
            {str(self.item.id): {'quantity': 1}},
        )

    def test_order_now_unknown_item_returns_404(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('order_now', args=[999999]))
        self.assertEqual(resp.status_code, 404)


class LogoutTests(TestCase):
    def test_logout_ends_session_and_redirects(self):
        user = User.objects.create_user(username='logoutuser', password='pw12345678')
        self.client.force_login(user)
        resp = self.client.get(reverse('user_logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('user_login'))
        self.assertNotIn('_auth_user_id', self.client.session)
