from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

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


def make_owner(username='rest_owner'):
    return User.objects.create_user(username=username, password='pw12345678')


def make_restaurant(owner=None, name='Model Kitchen', city='Testville'):
    return Restaurant.objects.create(
        owner=owner or make_owner(),
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Main Road',
        city=city,
    )


class RestaurantModelTests(TestCase):
    def test_str_shows_name_and_city(self):
        restaurant = make_restaurant(name='Spice Hub', city='Pune')
        self.assertEqual(str(restaurant), 'Spice Hub - Pune')

    def test_defaults_are_unapproved_and_unavailable(self):
        restaurant = make_restaurant()
        self.assertFalse(restaurant.is_approved)
        self.assertFalse(restaurant.is_available)
        self.assertFalse(restaurant.image)

    def test_optional_geo_and_compliance_fields_default_blank(self):
        restaurant = make_restaurant()
        self.assertIsNone(restaurant.lat)
        self.assertIsNone(restaurant.lon)
        self.assertEqual(restaurant.pan_number, '')
        self.assertEqual(restaurant.gstin_number, '')
        self.assertEqual(restaurant.fssai_number, '')
        self.assertIsNone(restaurant.player_id)


class SizeCategoryAndMenuTests(TestCase):
    def test_size_category_str(self):
        size = SizeCategory.objects.create(name='Large Plate')
        self.assertEqual(str(size), 'Large Plate')

    def test_size_category_name_is_unique(self):
        SizeCategory.objects.create(name='Large Plate')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SizeCategory.objects.create(name='Large Plate')

    def test_menu_item_str_shows_item_and_restaurant(self):
        restaurant = make_restaurant(name='Noodle Bar')
        size = SizeCategory.objects.create(name='Bowl')
        item = RestaurantMenu.objects.create(
            restaurant=restaurant,
            name='Ramen',
            category='Asian',
            price=Decimal('199.00'),
            prep_time=15,
            sizes_categories=size,
        )
        self.assertEqual(str(item), 'Ramen - Noodle Bar')

    def test_menu_item_availability_defaults_true(self):
        restaurant = make_restaurant()
        size = SizeCategory.objects.create(name='Bowl')
        item = RestaurantMenu.objects.create(
            restaurant=restaurant,
            name='Ramen',
            category='Asian',
            price=Decimal('199.00'),
            prep_time=15,
            sizes_categories=size,
        )
        self.assertTrue(item.available)
        self.assertIsNone(item.veg_or_nonveg)

    def test_menu_item_belongs_to_related_name_menus(self):
        restaurant = make_restaurant()
        size = SizeCategory.objects.create(name='Bowl')
        RestaurantMenu.objects.create(
            restaurant=restaurant,
            name='Ramen',
            category='Asian',
            price=Decimal('199.00'),
            prep_time=15,
            sizes_categories=size,
        )
        self.assertEqual(restaurant.menus.count(), 1)


class BankAccountModelTests(TestCase):
    def make_account(self, merchant, number, primary=False, **kwargs):
        defaults = dict(
            merchant=merchant,
            bank_name='First Bank',
            account_holder_name='Holder',
            account_number=number,
            ifsc_code='B1IN0000001',
            is_primary=primary,
        )
        defaults.update(kwargs)
        return BankAccount.objects.create(**defaults)

    def test_str_shows_bank_and_number(self):
        account = self.make_account(make_owner(), '111222333444')
        self.assertEqual(str(account), 'First Bank - 111222333444')

    def test_marking_new_primary_demotes_previous_primary(self):
        merchant = make_owner()
        first = self.make_account(merchant, '111111111111', primary=True)
        second = self.make_account(merchant, '222222222222', primary=True)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(second.is_primary)
        self.assertFalse(first.is_primary)

    def test_primary_flag_only_scoped_to_owning_merchant(self):
        merchant_a = make_owner('bank_a')
        merchant_b = make_owner('bank_b')
        a_primary = self.make_account(merchant_a, '111111111111', primary=True)
        self.make_account(merchant_b, '222222222222', primary=True)
        a_primary.refresh_from_db()
        self.assertTrue(a_primary.is_primary)

    def test_account_number_is_unique_across_merchants(self):
        self.make_account(make_owner('uniq_a'), '555555555555')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_account(make_owner('uniq_b'), '555555555555')

    def test_secondary_accounts_can_share_primary_flag_value(self):
        merchant = make_owner()
        self.make_account(merchant, '111111111111', primary=True)
        self.make_account(merchant, '222222222222', primary=False)
        self.make_account(merchant, '333333333333', primary=False)
        self.assertEqual(
            BankAccount.objects.filter(merchant=merchant).count(), 3
        )


class MerchantPaymentAndEarningTests(TestCase):
    def test_payment_str_contains_restaurant_amount_and_date(self):
        owner = make_owner()
        restaurant = make_restaurant(owner=owner, name='Pay Kitchen')
        payment = MerchantPayment.objects.create(
            merchant=owner,
            restaurant=restaurant,
            amount_paid=Decimal('2500.00'),
        )
        text = str(payment)
        self.assertIn('Pay Kitchen', text)
        self.assertIn('2500.00', text)
        self.assertIn(str(payment.payment_date.strftime('%Y-%m-%d')), text)

    def test_payment_date_is_automatic(self):
        owner = make_owner()
        restaurant = make_restaurant(owner=owner)
        payment = MerchantPayment.objects.create(
            merchant=owner,
            restaurant=restaurant,
            amount_paid=Decimal('10.00'),
        )
        self.assertIsNotNone(payment.payment_date)

    def test_earning_defaults_are_zero(self):
        owner = make_owner()
        restaurant = make_restaurant(owner=owner)
        earning = MerchantEarning.objects.create(
            merchant=owner, restaurant=restaurant
        )
        self.assertEqual(earning.net_sales, Decimal('0.00'))
        self.assertEqual(earning.weekly_sales, Decimal('0.00'))
        self.assertEqual(earning.amount_paid, Decimal('0.00'))
        self.assertEqual(earning.amount_pending, Decimal('0.00'))
        self.assertIsNotNone(earning.last_updated)

    def test_earning_unique_per_merchant_and_restaurant(self):
        owner = make_owner()
        restaurant = make_restaurant(owner=owner)
        MerchantEarning.objects.create(
            merchant=owner, restaurant=restaurant
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MerchantEarning.objects.create(
                    merchant=owner, restaurant=restaurant
                )

    def test_earning_str_mentions_restaurant_and_merchant(self):
        owner = make_owner()
        restaurant = make_restaurant(owner=owner, name='Earn Kitchen')
        earning = MerchantEarning.objects.create(
            merchant=owner, restaurant=restaurant
        )
        self.assertEqual(str(earning), 'Earnings for Earn Kitchen - rest_owner')

    def test_two_restaurants_can_have_separate_earnings(self):
        owner = make_owner()
        first = make_restaurant(owner=owner, name='A')
        second = make_restaurant(owner=owner, name='B')
        MerchantEarning.objects.create(merchant=owner, restaurant=first)
        MerchantEarning.objects.create(merchant=owner, restaurant=second)
        self.assertEqual(
            MerchantEarning.objects.filter(merchant=owner).count(), 2
        )


class ReviewModelTests(TestCase):
    def make_review(self, rating=5, comment='Nice'):
        owner = make_owner()
        restaurant = make_restaurant(owner=owner)
        user = User.objects.create_user(
            username=f'reviewer_{rating}', password='pw12345678'
        )
        return Review.objects.create(
            restaurant=restaurant, user=user, rating=rating, comment=comment
        )

    def test_str_names_reviewer_and_restaurant(self):
        review = self.make_review()
        text = str(review)
        self.assertIn('reviewer_5', text)
        self.assertIn('Model Kitchen', text)

    def test_created_at_is_automatic(self):
        review = self.make_review()
        self.assertIsNotNone(review.created_at)

    def test_rating_outside_choice_range_persists_at_db_level(self):
        review = self.make_review(rating=7)
        review.refresh_from_db()
        self.assertEqual(review.rating, 7)


class TicketModelTests(TestCase):
    def make_ticket(self, subject='Cannot login', username='tick_owner'):
        merchant = User.objects.create_user(
            username=username, password='pw12345678'
        )
        return Ticket.objects.create(
            merchant=merchant, subject=subject, category='technical'
        )

    def test_str_contains_id_subject_and_status(self):
        ticket = self.make_ticket()
        text = str(ticket)
        self.assertIn(ticket.ticket_id, text)
        self.assertIn('Cannot login', text)
        self.assertIn('Open', text)

    def test_ticket_id_is_seven_digit_string_and_unique(self):
        tickets = [self.make_ticket(username=f'tick_{i}') for i in range(5)]
        ids = [t.ticket_id for t in tickets]
        for ticket_id in ids:
            self.assertEqual(len(ticket_id), 7)
            self.assertTrue(ticket_id.isdigit())
        self.assertEqual(len(set(ids)), 5)

    def test_status_defaults_to_open(self):
        ticket = self.make_ticket()
        self.assertEqual(ticket.status, 'open')

    def test_created_and_updated_timestamps_populated(self):
        ticket = self.make_ticket()
        self.assertIsNotNone(ticket.created_at)
        self.assertIsNotNone(ticket.updated_at)

    def test_ticket_message_str_and_ordering(self):
        merchant = User.objects.create_user(
            username='msg_owner', password='pw12345678'
        )
        ticket = Ticket.objects.create(
            merchant=merchant, subject='Help', category='billing'
        )
        first = TicketMessage.objects.create(
            ticket=ticket, sender=merchant, message='First'
        )
        second = TicketMessage.objects.create(
            ticket=ticket, sender=merchant, message='Second'
        )
        messages = list(ticket.messages.all())
        self.assertEqual(
            [m.pk for m in messages], [first.pk, second.pk]
        )
        self.assertIn('msg_owner', str(first))
        self.assertIn(second.created_at.strftime('%Y-%m-%d'), str(second))

    def test_ticket_messages_cascade_on_delete(self):
        merchant = User.objects.create_user(
            username='cascade_owner', password='pw12345678'
        )
        ticket = Ticket.objects.create(
            merchant=merchant, subject='Bye', category='general'
        )
        TicketMessage.objects.create(
            ticket=ticket, sender=merchant, message='Only'
        )
        ticket.delete()
        self.assertEqual(TicketMessage.objects.count(), 0)


class MerchantRegistrationModelTests(TestCase):
    def test_registration_links_to_user_with_approval_default(self):
        user = User.objects.create_user(
            username='mreg_owner', password='pw12345678'
        )
        registration = merchantRegistration.objects.create(
            username=user,
            name='Merchant Person',
            number=Decimal('9876543210.0'),
        )
        self.assertEqual(registration.username.pk, user.pk)
        self.assertFalse(registration.is_approved)
        self.assertEqual(registration.name, 'Merchant Person')

    def test_user_can_only_register_once(self):
        user = User.objects.create_user(
            username='mreg_dup', password='pw12345678'
        )
        merchantRegistration.objects.create(
            username=user, name='First', number=Decimal('9876543210.0')
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                merchantRegistration.objects.create(
                    username=user, name='Second',
                    number=Decimal('9876543211.0'),
                )

    def test_registration_cascade_deletes_with_user(self):
        user = User.objects.create_user(
            username='mreg_cascade', password='pw12345678'
        )
        merchantRegistration.objects.create(
            username=user, name='Gone Soon', number=Decimal('9876543212.0')
        )
        user.delete()
        self.assertEqual(merchantRegistration.objects.count(), 0)
