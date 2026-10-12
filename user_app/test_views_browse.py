from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, Review, SizeCategory

from .models import CustomerFeedback, Order


def make_restaurant(name='Browse Kitchen', is_approved=True, owner=None):
    if owner is None:
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
        is_approved=is_approved,
        image=f'restaurantImages/{name.replace(" ", "").lower()}.jpg',
    )


def make_menu_item(restaurant, name='Test Burger', category='Burgers',
                   price='100.00', veg=None, available=True):
    size, _ = SizeCategory.objects.get_or_create(name=f'Regular {restaurant.name}')
    return RestaurantMenu.objects.create(
        restaurant=restaurant,
        name=name,
        category=category,
        price=Decimal(price),
        prep_time=10,
        sizes_categories=size,
        veg_or_nonveg=veg,
        available=available,
        image=f'menu_images/{name.replace(" ", "").lower()}.jpg',
    )


def make_restaurant_feedback(restaurant, rating, username=None):
    buyer = User.objects.create_user(
        username=username or f'fb_{restaurant.id}_{rating}', password='pw12345678'
    )
    order = Order.objects.create(
        user=buyer, restaurant=restaurant,
        customer_name='Pat', customer_contact='', landmark='',
        delivery_address='1 Road', special_instructions='', status='delivered',
    )
    return CustomerFeedback.objects.create(
        order=order, restaurant=restaurant, customer=buyer, rating=rating,
    )


def make_review(restaurant, user, rating, comment='Nice'):
    return Review.objects.create(
        restaurant=restaurant, user=user, rating=rating, comment=comment,
    )


def make_feedback_for_item(item, rating_value):
    buyer = User.objects.create_user(
        username=f'fb_{item.id}_{rating_value}', password='pw12345678'
    )
    order = Order.objects.create(
        user=buyer, restaurant=item.restaurant,
        customer_name='Pat', customer_contact='', landmark='',
        delivery_address='1 Road', special_instructions='', status='delivered',
    )
    return CustomerFeedback.objects.create(
        order=order, restaurant=item.restaurant, customer=buyer,
        item_ratings={str(item.id): rating_value},
    )


class HomeViewTests(TestCase):
    def test_home_renders(self):
        resp = self.client.get(reverse('home'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'home.html')

    def test_home_lists_only_approved_restaurants(self):
        approved = make_restaurant('Approved Place')
        make_restaurant('Pending Place', is_approved=False)
        resp = self.client.get(reverse('home'))
        names = [r.name for r in resp.context['approved_restaurants']]
        self.assertIn('Approved Place', names)
        self.assertNotIn('Pending Place', names)

    def test_home_lists_only_items_of_approved_restaurants(self):
        approved = make_restaurant('Approved Place')
        hidden = make_restaurant('Pending Place', is_approved=False)
        make_menu_item(approved, name='Visible Item')
        make_menu_item(hidden, name='Hidden Item')
        resp = self.client.get(reverse('home'))
        item_names = [i.name for i in resp.context['items']]
        self.assertIn('Visible Item', item_names)
        self.assertNotIn('Hidden Item', item_names)

    def test_home_search_filters_by_name(self):
        approved = make_restaurant('Search Place')
        make_menu_item(approved, name='Pizza Margherita')
        make_menu_item(approved, name='Cheese Fries')
        resp = self.client.get(reverse('home'), {'q': 'pizza'})
        item_names = [i.name for i in resp.context['items']]
        self.assertEqual(item_names, ['Pizza Margherita'])

    def test_home_search_is_case_insensitive_and_matches_substring(self):
        approved = make_restaurant('Search Place')
        make_menu_item(approved, name='Double Cheese Burger')
        make_menu_item(approved, name='Salad Bowl')
        resp = self.client.get(reverse('home'), {'q': 'CHEESE'})
        item_names = [i.name for i in resp.context['items']]
        self.assertEqual(item_names, ['Double Cheese Burger'])

    def test_home_search_with_no_match_returns_empty(self):
        approved = make_restaurant('Search Place')
        make_menu_item(approved, name='Thali')
        resp = self.client.get(reverse('home'), {'q': 'zzzz'})
        self.assertEqual(list(resp.context['items']), [])

    def test_home_context_exposes_categories_and_sizes(self):
        approved = make_restaurant('Browse Kitchen')
        make_menu_item(approved, category='Burgers')
        size, _ = SizeCategory.objects.get_or_create(name='Regular Browse Kitchen')
        resp = self.client.get(reverse('home'))
        self.assertIn('Burgers', list(resp.context['categories']))
        self.assertIn(size, list(resp.context['size']))

    def test_home_annotates_average_rating(self):
        owner = User.objects.create_user(username='revowner', password='pw12345678')
        rated = make_restaurant('Rated Place', owner=owner)
        unrated = make_restaurant('Unrated Place')
        make_review(rated, owner, 4)
        make_review(rated, owner, 5)
        resp = self.client.get(reverse('home'))
        ratings = {r.name: r.avg_rating for r in resp.context['approved_restaurants']}
        self.assertEqual(ratings['Rated Place'], 4.5)
        self.assertEqual(ratings['Unrated Place'], 0)

    def test_home_annotates_unapproved_restaurant_but_hides_from_context(self):
        make_restaurant('Pending Place', is_approved=False)
        resp = self.client.get(reverse('home'))
        self.assertEqual(list(resp.context['approved_restaurants']), [])
        self.assertEqual(list(resp.context['items']), [])


class CategoryItemsViewTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant('Category Kitchen')
        self.burger = make_menu_item(self.restaurant, name='Zebra Burger', category='Burgers', price='150.00')
        self.fries = make_menu_item(self.restaurant, name='Alpha Fries', category='Sides', price='50.00')

    def url(self, slug='burgers'):
        return reverse('category_items', args=[slug])

    def test_known_category_renders_with_category_name(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'category_items.html')
        self.assertEqual(resp.context['category_name'], 'Burgers')

    def test_unknown_category_slug_renders_not_found_page(self):
        resp = self.client.get(self.url('no-such-category'))
        self.assertEqual(resp.status_code, 404)
        self.assertTemplateUsed(resp, '404.html')

    def test_lists_only_items_of_that_category(self):
        resp = self.client.get(self.url())
        names = [i.name for i in resp.context['items']]
        self.assertEqual(names, ['Zebra Burger'])

    def test_price_ascending_sort(self):
        make_menu_item(self.restaurant, name='Cheap Burger', category='Burgers', price='40.00')
        resp = self.client.get(self.url(), {'price': 'asc'})
        names = [i.name for i in resp.context['items']]
        self.assertEqual(names, ['Cheap Burger', 'Zebra Burger'])

    def test_price_descending_sort(self):
        make_menu_item(self.restaurant, name='Cheap Burger', category='Burgers', price='40.00')
        resp = self.client.get(self.url(), {'price': 'desc'})
        names = [i.name for i in resp.context['items']]
        self.assertEqual(names, ['Zebra Burger', 'Cheap Burger'])

    def test_no_price_param_keeps_default_ordering(self):
        make_menu_item(self.restaurant, name='Cheap Burger', category='Burgers', price='40.00')
        resp = self.client.get(self.url())
        self.assertEqual(len(resp.context['items']), 2)

    def test_rating_filter_keeps_only_items_of_highly_rated_restaurants(self):
        other = make_restaurant('Other Kitchen')
        make_restaurant_feedback(self.restaurant, 5, username='catrev1')
        make_restaurant_feedback(self.restaurant, 4, username='catrev2')
        make_restaurant_feedback(other, 2, username='catrev3')
        make_menu_item(other, name='Low Rated Burger', category='Burgers')
        resp = self.client.get(self.url(), {'rating': '4'})
        names = [i.name for i in resp.context['items']]
        self.assertIn('Zebra Burger', names)
        self.assertNotIn('Low Rated Burger', names)

    def test_rating_filter_below_threshold_excludes_restaurant(self):
        make_restaurant_feedback(self.restaurant, 2, username='catrev4')
        resp = self.client.get(self.url(), {'rating': '4'})
        self.assertEqual(list(resp.context['items']), [])

    def test_garbage_rating_param_is_ignored(self):
        resp = self.client.get(self.url(), {'rating': 'abc'})
        names = [i.name for i in resp.context['items']]
        self.assertEqual(names, ['Zebra Burger'])

    def test_veg_filter(self):
        make_menu_item(self.restaurant, name='Veg Burger', category='Burgers', veg='veg')
        make_menu_item(self.restaurant, name='Nonveg Burger', category='Burgers', veg='nonveg')
        resp = self.client.get(self.url(), {'veg_filter': 'veg'})
        names = [i.name for i in resp.context['items']]
        self.assertIn('Veg Burger', names)
        self.assertNotIn('Zebra Burger', names)
        self.assertNotIn('Nonveg Burger', names)

    def test_nonveg_filter(self):
        make_menu_item(self.restaurant, name='Veg Burger', category='Burgers', veg='veg')
        make_menu_item(self.restaurant, name='Nonveg Burger', category='Burgers', veg='nonveg')
        resp = self.client.get(self.url(), {'veg_filter': 'nonveg'})
        names = [i.name for i in resp.context['items']]
        self.assertEqual(names, ['Nonveg Burger'])

    def test_unknown_veg_filter_value_shows_everything(self):
        make_menu_item(self.restaurant, name='Veg Burger', category='Burgers', veg='veg')
        resp = self.client.get(self.url(), {'veg_filter': 'maybe'})
        self.assertEqual(len(resp.context['items']), 2)

    def test_item_average_rating_from_item_ratings_json(self):
        make_feedback_for_item(self.burger, 5)
        make_feedback_for_item(self.burger, 4)
        resp = self.client.get(self.url())
        items = {i.name: i for i in resp.context['items']}
        self.assertEqual(items['Zebra Burger'].average_rating, 4.5)

    def test_item_average_rating_of_sibling_category_item(self):
        make_feedback_for_item(self.fries, 3)
        resp = self.client.get(reverse('category_items', args=['sides']))
        items = {i.name: i for i in resp.context['items']}
        self.assertEqual(items['Alpha Fries'].average_rating, 3.0)

    def test_item_average_rating_none_without_feedback(self):
        resp = self.client.get(self.url())
        items = {i.name: i for i in resp.context['items']}
        self.assertIsNone(items['Zebra Burger'].average_rating)

    def test_item_average_rating_ignores_non_numeric_values(self):
        buyer = User.objects.create_user(username='weirdfb', password='pw12345678')
        order = Order.objects.create(
            user=buyer, restaurant=self.restaurant,
            customer_name='Pat', customer_contact='', landmark='',
            delivery_address='1 Road', special_instructions='', status='delivered',
        )
        CustomerFeedback.objects.create(
            order=order, restaurant=self.restaurant, customer=buyer,
            item_ratings={str(self.burger.id): 'not-a-number'},
        )
        resp = self.client.get(self.url())
        items = {i.name: i for i in resp.context['items']}
        self.assertIsNone(items['Zebra Burger'].average_rating)

    def test_rating_options_context_offers_five_levels(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.context['rating_options'], [5, 4, 3, 2, 1])


class StaticPageTests(TestCase):
    def test_simple_pages_render_expected_templates(self):
        cases = [
            ('about', 'about.html'),
            ('contact', 'contact.html'),
            ('privacy', 'privacy.html'),
            ('careers', 'careers.html'),
            ('add-restaurant', 'addRestaurant.html'),
            ('ride-with-us', 'rideWithUs.html'),
            ('responsible-disclosure', 'ResponsibleDisclosure.html'),
            ('terms-and-conditions', 'Terms&Conditions.html'),
            ('registration_success', 'user_registration_success.html'),
        ]
        for name, template in cases:
            with self.subTest(page=name):
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 200)
                self.assertTemplateUsed(resp, template)


class UserViewMenuTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant('Menu Kitchen')
        self.burger = make_menu_item(self.restaurant, name='House Burger', price='120.00')
        self.hidden = make_menu_item(self.restaurant, name='Off Menu', available=False)
        self.sides = make_menu_item(self.restaurant, name='Onion Rings', category='Sides')

    def url(self):
        return reverse('user_view_menu', args=[self.restaurant.id])

    def test_menu_renders_for_existing_restaurant(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'view_menu.html')
        self.assertEqual(resp.context['restaurant'].id, self.restaurant.id)

    def test_unknown_restaurant_returns_404(self):
        resp = self.client.get(reverse('user_view_menu', args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_hides_unavailable_items(self):
        resp = self.client.get(self.url())
        names = [m.name for m in resp.context['menus']]
        self.assertIn('House Burger', names)
        self.assertNotIn('Off Menu', names)

    def test_category_query_filters_items(self):
        resp = self.client.get(self.url(), {'category': 'Sides'})
        names = [m.name for m in resp.context['menus']]
        self.assertEqual(names, ['Onion Rings'])

    def test_search_query_filters_by_name(self):
        resp = self.client.get(self.url(), {'q': 'burger'})
        names = [m.name for m in resp.context['menus']]
        self.assertEqual(names, ['House Burger'])

    def test_categories_context_lists_distinct_categories(self):
        resp = self.client.get(self.url())
        self.assertCountEqual(resp.context['categories'], ['Burgers', 'Sides'])

    def test_average_rating_zero_without_reviews(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.context['average_rating'], 0)

    def test_average_rating_rounded_to_one_decimal(self):
        owner = self.restaurant.owner
        make_review(self.restaurant, owner, 4)
        make_review(self.restaurant, owner, 5)
        resp = self.client.get(self.url())
        self.assertEqual(resp.context['average_rating'], 4.5)

    def test_average_rating_reflects_only_this_restaurant(self):
        owner = self.restaurant.owner
        other = make_restaurant('Other Menu Kitchen')
        make_review(other, owner, 1)
        make_review(other, owner, 1)
        resp = self.client.get(self.url())
        self.assertEqual(resp.context['average_rating'], 0)
