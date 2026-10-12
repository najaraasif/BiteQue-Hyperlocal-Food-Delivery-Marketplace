from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .forms import (
    BankAccountForm,
    MerchantRegistrationForm,
    RestaurantForm,
    RestaurantMenuForm,
    ReviewForm,
    TicketCreateForm,
    TicketMessageForm,
)
from .models import BankAccount, Restaurant, RestaurantMenu, SizeCategory


def valid_registration(**overrides):
    data = {
        'username': 'newmerchant',
        'name': 'New Merchant',
        'number': '9876543210',
        'email': 'new@example.com',
        'password': 'Str0ngPass!',
        'retypePassword': 'Str0ngPass!',
    }
    data.update(overrides)
    return data


class MerchantRegistrationFormTests(TestCase):
    def test_valid_data_passes(self):
        form = MerchantRegistrationForm(data=valid_registration())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_country_code_prefix_is_stripped(self):
        form = MerchantRegistrationForm(
            data=valid_registration(number='+919876543210')
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_double_nine_one_prefix_without_plus_is_stripped(self):
        form = MerchantRegistrationForm(
            data=valid_registration(number='919876543210')
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_number_starting_with_five_is_rejected(self):
        form = MerchantRegistrationForm(
            data=valid_registration(number='5876543210')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)

    def test_number_with_letters_is_rejected(self):
        form = MerchantRegistrationForm(
            data=valid_registration(number='98765abc3210')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)

    def test_username_with_spaces_is_rejected(self):
        form = MerchantRegistrationForm(
            data=valid_registration(username='bad name')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_username_shorter_than_four_is_rejected(self):
        form = MerchantRegistrationForm(
            data=valid_registration(username='abc')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(username='takenname', password='pw12345678')
        form = MerchantRegistrationForm(
            data=valid_registration(username='takenname')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_name_rejects_digits_and_punctuation(self):
        for bad in ('Per1son', 'Per-son', 'Per.son'):
            with self.subTest(name=bad):
                form = MerchantRegistrationForm(
                    data=valid_registration(name=bad)
                )
                self.assertFalse(form.is_valid())
                self.assertIn('name', form.errors)

    def test_name_accepts_spaces(self):
        form = MerchantRegistrationForm(
            data=valid_registration(name='Two Words Here')
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(
            username='emailowner', password='pw12345678',
            email='new@example.com',
        )
        form = MerchantRegistrationForm(data=valid_registration())
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_malformed_email_is_rejected(self):
        form = MerchantRegistrationForm(
            data=valid_registration(email='not-an-email')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_short_password_is_rejected(self):
        form = MerchantRegistrationForm(
            data=valid_registration(password='Ab1!', retypePassword='Ab1!')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)

    def test_password_requires_digit_upper_lower_and_special(self):
        cases = {
            'password': 'NoDigits!!',
            'password2': 'lowercase1!',
            'password3': 'UPPERCASE1!',
            'password4': 'NoSpecial12',
        }
        for key, password in cases.items():
            with self.subTest(password=password):
                form = MerchantRegistrationForm(
                    data=valid_registration(
                        password=password, retypePassword=password
                    )
                )
                self.assertFalse(form.is_valid())
                self.assertIn('password', form.errors)

    def test_password_mismatch_reported_on_retype(self):
        form = MerchantRegistrationForm(
            data=valid_registration(retypePassword='OtherStr0ng!')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('retypePassword', form.errors)


class RestaurantFormTests(TestCase):
    def valid_data(self, **overrides):
        data = {
            'name': 'Form Kitchen',
            'email': 'form@example.com',
            'contact_number': '9876543210',
            'address': '1 Main Road',
            'city': 'Testville',
        }
        data.update(overrides)
        return data

    def test_valid_data_passes(self):
        form = RestaurantForm(data=self.valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_excludes_owner_approval_and_availability(self):
        form = RestaurantForm()
        self.assertNotIn('owner', form.fields)
        self.assertNotIn('is_approved', form.fields)
        self.assertNotIn('is_available', form.fields)

    def test_contact_number_accepts_plus_91_prefix(self):
        form = RestaurantForm(
            data=self.valid_data(contact_number='+919876543210')
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_contact_number_rejects_wrong_prefix_length(self):
        form = RestaurantForm(
            data=self.valid_data(contact_number='876543210')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('contact_number', form.errors)

    def test_contact_number_rejects_landline(self):
        form = RestaurantForm(data=self.valid_data(contact_number='0112345678'))
        self.assertFalse(form.is_valid())
        self.assertIn('contact_number', form.errors)

    def test_blank_pan_is_allowed(self):
        form = RestaurantForm(data=self.valid_data(pan_number=''))
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_pan_is_accepted(self):
        form = RestaurantForm(
            data=self.valid_data(pan_number='ABCDE1234F')
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_malformed_pan_is_rejected(self):
        for bad in ('abcde1234f', 'ABCDE1234', 'AB12341234'):
            with self.subTest(pan=bad):
                form = RestaurantForm(data=self.valid_data(pan_number=bad))
                self.assertFalse(form.is_valid())
                self.assertIn('pan_number', form.errors)

    def test_valid_gstin_is_accepted(self):
        form = RestaurantForm(
            data=self.valid_data(gstin_number='22AAAAA0000A1Z5')
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_malformed_gstin_is_rejected(self):
        for bad in ('22aaaaa0000a1z5', '22AAAAA0000A1', 'ABCDE0000A1Z5'):
            with self.subTest(gstin=bad):
                form = RestaurantForm(data=self.valid_data(gstin_number=bad))
                self.assertFalse(form.is_valid())
                self.assertIn('gstin_number', form.errors)

    def test_fourteen_digit_fssai_is_accepted(self):
        form = RestaurantForm(
            data=self.valid_data(fssai_number='12345678901234')
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_thirteen_digit_fssai_is_rejected(self):
        form = RestaurantForm(
            data=self.valid_data(fssai_number='1234567890123')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('fssai_number', form.errors)

    def test_missing_required_fields_are_reported_together(self):
        form = RestaurantForm(data={})
        self.assertFalse(form.is_valid())
        for field in ('name', 'email', 'contact_number', 'address', 'city'):
            self.assertIn(field, form.errors)


class RestaurantMenuFormTests(TestCase):
    def setUp(self):
        self.size = SizeCategory.objects.create(name='Regular Form Size')

    def valid_data(self, **overrides):
        data = {
            'name': 'Menu Item',
            'sizes_categories': self.size.pk,
            'category': 'Burgers',
            'description': 'Tasty',
            'price': '199.99',
            'available': True,
            'prep_time': 12,
            'veg_or_nonveg': 'veg',
        }
        data.update(overrides)
        return data

    def test_valid_data_passes(self):
        form = RestaurantMenuForm(data=self.valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_declared_field_set_matches_meta(self):
        form = RestaurantMenuForm()
        self.assertEqual(
            set(form.fields),
            {
                'name', 'sizes_categories', 'category', 'description',
                'image', 'price', 'available', 'prep_time', 'veg_or_nonveg',
            },
        )
        self.assertNotIn('restaurant', form.fields)

    def test_veg_and_nonveg_values_are_accepted(self):
        for value in ('veg', 'nonveg'):
            with self.subTest(value=value):
                form = RestaurantMenuForm(
                    data=self.valid_data(veg_or_nonveg=value)
                )
                self.assertTrue(form.is_valid(), form.errors)

    def test_veg_value_outside_choices_is_rejected(self):
        form = RestaurantMenuForm(data=self.valid_data(veg_or_nonveg='vegan'))
        self.assertFalse(form.is_valid())
        self.assertIn('veg_or_nonveg', form.errors)

    def test_missing_price_and_prep_time_are_rejected(self):
        data = self.valid_data()
        del data['price']
        del data['prep_time']
        form = RestaurantMenuForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)
        self.assertIn('prep_time', form.errors)

    def test_zero_prep_time_is_accepted(self):
        form = RestaurantMenuForm(data=self.valid_data(prep_time=0))
        self.assertTrue(form.is_valid(), form.errors)

    def test_negative_prep_time_is_rejected(self):
        form = RestaurantMenuForm(data=self.valid_data(prep_time=-5))
        self.assertFalse(form.is_valid())
        self.assertIn('prep_time', form.errors)

    def test_non_image_upload_is_rejected(self):
        data = self.valid_data()
        form = RestaurantMenuForm(
            data=data,
            files={'image': SimpleUploadedFile('note.txt', b'hello', 'text/plain')},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)


class BankAccountFormTests(TestCase):
    def setUp(self):
        self.merchant = User.objects.create_user(
            username='bank_form_owner', password='pw12345678'
        )

    def valid_data(self, **overrides):
        data = {
            'bank_name': 'Form Bank',
            'account_holder_name': 'Holder Name',
            'account_number': '123456789012',
            'ifsc_code': 'IN000123456',
            'is_primary': True,
        }
        data.update(overrides)
        return data

    def test_valid_data_passes(self):
        form = BankAccountForm(data=self.valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_approval_field_is_not_exposed(self):
        form = BankAccountForm()
        self.assertNotIn('is_approved', form.fields)
        self.assertIn('is_primary', form.fields)

    def test_missing_required_fields_are_reported(self):
        form = BankAccountForm(data={})
        self.assertFalse(form.is_valid())
        for field in (
            'bank_name', 'account_holder_name', 'account_number', 'ifsc_code'
        ):
            self.assertIn(field, form.errors)

    def test_saving_assigns_merchant_and_defaults(self):
        form = BankAccountForm(data=self.valid_data(is_primary=False))
        self.assertTrue(form.is_valid(), form.errors)
        account = form.save(commit=False)
        account.merchant = self.merchant
        account.save()
        self.assertEqual(account.merchant.pk, self.merchant.pk)
        self.assertFalse(account.is_primary)
        self.assertFalse(account.is_approved)

    def test_is_primary_checkbox_accepts_false(self):
        form = BankAccountForm(data=self.valid_data(is_primary=False))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data['is_primary'])


class ReviewFormTests(TestCase):
    def test_rating_five_passes(self):
        form = ReviewForm(data={'rating': 5, 'comment': 'Great'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_rating_six_is_rejected(self):
        form = ReviewForm(data={'rating': 6, 'comment': 'Too good'})
        self.assertFalse(form.is_valid())
        self.assertIn('rating', form.errors)

    def test_rating_zero_is_rejected(self):
        form = ReviewForm(data={'rating': 0, 'comment': 'Bad'})
        self.assertFalse(form.is_valid())
        self.assertIn('rating', form.errors)

    def test_comment_is_required(self):
        form = ReviewForm(data={'rating': 4, 'comment': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('comment', form.errors)


class TicketFormsTests(TestCase):
    def test_ticket_create_requires_subject_and_valid_category(self):
        form = TicketCreateForm(data={'subject': '', 'category': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)
        self.assertIn('category', form.errors)

    def test_ticket_create_accepts_known_categories(self):
        for category in ('technical', 'billing', 'general', 'other'):
            with self.subTest(category=category):
                form = TicketCreateForm(
                    data={'subject': 'Help me', 'category': category}
                )
                self.assertTrue(form.is_valid(), form.errors)

    def test_ticket_create_rejects_unknown_category(self):
        form = TicketCreateForm(
            data={'subject': 'Help me', 'category': 'refund'}
        )
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_message_form_requires_message(self):
        form = TicketMessageForm(data={'message': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_message_form_accepts_text_only(self):
        form = TicketMessageForm(data={'message': 'Plain text reply'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_message_form_accepts_image_upload(self):
        gif = SimpleUploadedFile(
            'shot.gif', b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00'
            b'\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
            content_type='image/gif',
        )
        form = TicketMessageForm(
            data={'message': 'With picture'}, files={'image': gif}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_message_form_rejects_non_image_upload(self):
        form = TicketMessageForm(
            data={'message': 'With file'},
            files={'image': SimpleUploadedFile('doc.txt', b'x', 'text/plain')},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)


class CrossFormIntegrationTests(TestCase):
    def test_restaurant_form_uniqueness_is_not_enforced_by_form(self):
        owner = User.objects.create_user(
            username='uniq_rest_owner', password='pw12345678'
        )
        Restaurant.objects.create(
            owner=owner, name='Dup', email='dup@example.com',
            contact_number='9876543210', address='1 Road', city='Town',
        )
        form = RestaurantForm(data={
            'name': 'Dup', 'email': 'dup@example.com',
            'contact_number': '9876543210', 'address': '1 Road',
            'city': 'Town',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_menu_form_bound_to_instance_returns_current_values(self):
        owner = User.objects.create_user(
            username='bound_owner', password='pw12345678'
        )
        restaurant = Restaurant.objects.create(
            owner=owner, name='Bound', email='bound@example.com',
            contact_number='9876543210', address='1 Road', city='Town',
        )
        size = SizeCategory.objects.create(name='Bound Size')
        item = RestaurantMenu.objects.create(
            restaurant=restaurant, name='Old Name', category='Bowls',
            price=Decimal('99.00'), prep_time=5, sizes_categories=size,
        )
        form = RestaurantMenuForm(instance=item)
        self.assertEqual(form.initial['name'], 'Old Name')
        self.assertEqual(form.initial['price'], Decimal('99.00'))
