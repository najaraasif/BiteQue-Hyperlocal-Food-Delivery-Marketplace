from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory

from .forms import (
    ComprehensiveFeedbackForm,
    UserTicketCreateForm,
    UserTicketMessageForm,
    UserProfileForm,
    userRegistrationForm,
)
from .models import Order, UserProfile


TINY_GIF = (
    b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00'
    b'\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


def valid_registration(**overrides):
    data = {
        'username': 'newuser1',
        'name': 'Pat Lee',
        'number': '9876543210',
        'email': 'pat@example.com',
        'password': 'Abcd1234!',
        'retypePassword': 'Abcd1234!',
        'whatsapp_consent': 'on',
    }
    data.update(overrides)
    return data


def make_restaurant(name='Form Kitchen'):
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


def make_menu_item(restaurant, name, price='100.00'):
    size, _ = SizeCategory.objects.get_or_create(name=f'Regular {restaurant.name}')
    return RestaurantMenu.objects.create(
        restaurant=restaurant,
        name=name,
        category='Burgers',
        price=Decimal(price),
        prep_time=10,
        sizes_categories=size,
    )


class UserRegistrationFormTests(TestCase):
    def test_valid_data_passes(self):
        form = userRegistrationForm(data=valid_registration())
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['username'], 'newuser1')
        self.assertEqual(form.cleaned_data['whatsapp_consent'], True)

    def test_whatsapp_consent_is_optional(self):
        data = valid_registration()
        del data['whatsapp_consent']
        form = userRegistrationForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data['whatsapp_consent'])

    def test_username_rejects_spaces(self):
        form = userRegistrationForm(data=valid_registration(username='bad user'))
        self.assertFalse(form.is_valid())
        self.assertIn('Username contains invalid characters.', form.errors['username'])

    def test_username_rejects_short_names(self):
        form = userRegistrationForm(data=valid_registration(username='abc'))
        self.assertFalse(form.is_valid())
        self.assertIn('Username must be at least 4 characters long.', form.errors['username'])

    def test_username_rejects_duplicates(self):
        User.objects.create_user(username='taken1', password='pw12345678')
        form = userRegistrationForm(data=valid_registration(username='taken1'))
        self.assertFalse(form.is_valid())
        self.assertIn('Username already exists.', form.errors['username'])

    def test_username_allows_dots_at_plus_dash_underscore(self):
        form = userRegistrationForm(data=valid_registration(username='a.b_c+d-e@f'))
        self.assertTrue(form.is_valid())

    def test_name_rejects_digits(self):
        form = userRegistrationForm(data=valid_registration(name='Pat 2Lee'))
        self.assertFalse(form.is_valid())
        self.assertIn('Name should contain only letters and spaces.', form.errors['name'])

    def test_name_rejects_hyphens(self):
        form = userRegistrationForm(data=valid_registration(name='Pat-Lee'))
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_name_accepts_single_word(self):
        form = userRegistrationForm(data=valid_registration(name='Pat'))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['name'], 'Pat')

    def test_number_field_rejects_formatted_input_longer_than_ten_chars(self):
        form = userRegistrationForm(data=valid_registration(number='98765-43210'))
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)

    def test_number_accepts_exactly_ten_digits(self):
        form = userRegistrationForm(data=valid_registration(number='9876543210'))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['number'], '9876543210')

    def test_number_with_non_digits_inside_ten_chars_is_rejected(self):
        form = userRegistrationForm(data=valid_registration(number='98765x4321'))
        self.assertFalse(form.is_valid())
        self.assertIn('Enter a valid 10-digit phone number.', form.errors['number'])

    def test_number_rejects_wrong_length(self):
        form = userRegistrationForm(data=valid_registration(number='987654321'))
        self.assertFalse(form.is_valid())
        self.assertIn('Enter a valid 10-digit phone number.', form.errors['number'])

    def test_number_rejects_country_code_prefix(self):
        form = userRegistrationForm(data=valid_registration(number='+91 98765 43210'))
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)

    def test_email_rejects_duplicates(self):
        User.objects.create_user(username='other1', password='pw12345678', email='pat@example.com')
        form = userRegistrationForm(data=valid_registration())
        self.assertFalse(form.is_valid())
        self.assertIn('Email already exists.', form.errors['email'])

    def test_email_rejects_malformed(self):
        form = userRegistrationForm(data=valid_registration(email='not-an-email'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_password_rejects_short(self):
        form = userRegistrationForm(data=valid_registration(password='Ab1!', retypePassword='Ab1!'))
        self.assertFalse(form.is_valid())
        self.assertIn('Password must be at least 8 characters long.', form.errors['password'])

    def test_password_requires_digit(self):
        form = userRegistrationForm(data=valid_registration(password='Abcdefgh!', retypePassword='Abcdefgh!'))
        self.assertFalse(form.is_valid())
        self.assertIn('Password must contain at least one digit.', form.errors['password'])

    def test_password_requires_uppercase(self):
        form = userRegistrationForm(data=valid_registration(password='abcdefgh1!', retypePassword='abcdefgh1!'))
        self.assertFalse(form.is_valid())
        self.assertIn('Password must contain at least one uppercase letter.', form.errors['password'])

    def test_password_requires_lowercase(self):
        form = userRegistrationForm(data=valid_registration(password='ABCDEFGH1!', retypePassword='ABCDEFGH1!'))
        self.assertFalse(form.is_valid())
        self.assertIn('Password must contain at least one lowercase letter.', form.errors['password'])

    def test_password_requires_special_character(self):
        form = userRegistrationForm(data=valid_registration(password='Abcdefgh12', retypePassword='Abcdefgh12'))
        self.assertFalse(form.is_valid())
        self.assertIn('Password must contain at least one special character.', form.errors['password'])

    def test_password_mismatch_reported_on_retype(self):
        form = userRegistrationForm(data=valid_registration(retypePassword='Other1234!'))
        self.assertFalse(form.is_valid())
        self.assertIn('Passwords do not match.', form.errors['retypePassword'])

    def test_all_errors_reported_together_when_password_itself_valid(self):
        form = userRegistrationForm(data=valid_registration(
            username='x', name='Pat2', number='12',
            password='Abcd1234!', retypePassword='Abcd9999!',
        ))
        self.assertFalse(form.is_valid())
        for field in ('username', 'name', 'number', 'retypePassword'):
            self.assertIn(field, form.errors)
        self.assertNotIn('password', form.errors)

    def test_mismatch_check_skipped_when_password_invalid(self):
        form = userRegistrationForm(data=valid_registration(
            password='weak', retypePassword='weak2',
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)
        self.assertNotIn('retypePassword', form.errors)


class ComprehensiveFeedbackFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ffbuyer', password='pw12345678')
        self.restaurant = make_restaurant('Feedback Form Kitchen')
        self.order = Order.objects.create(
            user=self.user, restaurant=self.restaurant,
            customer_name='Pat', customer_contact='', landmark='',
            delivery_address='1 Road', special_instructions='',
        )
        self.item_a = make_menu_item(self.restaurant, 'Burger')
        self.item_b = make_menu_item(self.restaurant, 'Fries')

    def add_items(self, item):
        from .models import OrderMenuItem
        OrderMenuItem.objects.create(
            order=self.order, menu_item=item, quantity=1, price=item.price
        )

    def test_adds_rating_field_per_order_item(self):
        self.add_items(self.item_a)
        self.add_items(self.item_b)
        form = ComprehensiveFeedbackForm(order=self.order)
        self.assertIn(f'item_rating_{self.item_a.id}', form.fields)
        self.assertIn(f'item_rating_{self.item_b.id}', form.fields)
        self.assertEqual(
            form.fields[f'item_rating_{self.item_a.id}'].label,
            f'Rating for {self.item_a.name}',
        )

    def test_no_dynamic_fields_without_order(self):
        form = ComprehensiveFeedbackForm()
        self.assertFalse(any(name.startswith('item_rating_') for name in form.fields))

    def test_rating_fields_are_optional_choices_1_to_5(self):
        self.add_items(self.item_a)
        form = ComprehensiveFeedbackForm(order=self.order)
        field = form.fields[f'item_rating_{self.item_a.id}']
        self.assertFalse(field.required)
        self.assertEqual([c[0] for c in field.choices], [1, 2, 3, 4, 5])

    def test_valid_submission_without_any_ratings(self):
        form = ComprehensiveFeedbackForm(data={'additional_comments': 'nice'}, order=self.order)
        self.assertTrue(form.is_valid())

    def test_rejects_out_of_range_item_rating(self):
        self.add_items(self.item_a)
        form = ComprehensiveFeedbackForm(
            data={f'item_rating_{self.item_a.id}': '6'}, order=self.order
        )
        self.assertFalse(form.is_valid())

    def test_get_item_ratings_maps_ids_to_ints(self):
        self.add_items(self.item_a)
        self.add_items(self.item_b)
        form = ComprehensiveFeedbackForm(data={
            f'item_rating_{self.item_a.id}': '4',
            f'item_rating_{self.item_b.id}': '',
            'item_quality': '5',
        }, order=self.order)
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.get_item_ratings(),
            {self.item_a.id: 4},
        )

    def test_get_item_ratings_skips_unfilled_fields(self):
        form = ComprehensiveFeedbackForm(data={'additional_comments': 'x'}, order=self.order)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_item_ratings(), {})

    def test_main_rating_fields_accept_five_and_reject_six(self):
        good = ComprehensiveFeedbackForm(data={
            'item_quality': '5', 'delivery_experience': '4',
            'restaurant_rating': '3', 'rider_rating': '2',
        }, order=self.order)
        self.assertTrue(good.is_valid())

        bad = ComprehensiveFeedbackForm(data={'item_quality': '6'}, order=self.order)
        self.assertFalse(bad.is_valid())


class UserTicketFormsTests(TestCase):
    def test_ticket_create_valid(self):
        form = UserTicketCreateForm(data={'subject': 'App broken', 'category': 'technical'})
        self.assertTrue(form.is_valid())

    def test_ticket_create_requires_subject(self):
        form = UserTicketCreateForm(data={'subject': '', 'category': 'technical'})
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)

    def test_ticket_create_rejects_unknown_category(self):
        form = UserTicketCreateForm(data={'subject': 'Hi', 'category': 'urgent'})
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_message_form_accepts_text_only(self):
        form = UserTicketMessageForm(data={'message': 'Hello there'})
        self.assertTrue(form.is_valid())

    def test_message_form_requires_message(self):
        form = UserTicketMessageForm(data={'message': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_message_form_accepts_image_upload(self):
        form = UserTicketMessageForm(
            data={'message': 'See attached'},
            files={'image': SimpleUploadedFile('shot.gif', TINY_GIF, content_type='image/gif')},
        )
        self.assertTrue(form.is_valid())

    def test_message_form_rejects_non_image_upload(self):
        form = UserTicketMessageForm(
            data={'message': 'See attached'},
            files={'image': SimpleUploadedFile('notes.txt', b'plain text', content_type='text/plain')},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)


class UserProfileFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profile1', password='pw12345678',
            first_name='Old', last_name='Name',
        )
        self.profile = self.user.userprofile

    def test_initials_populated_from_user(self):
        form = UserProfileForm(instance=self.profile)
        self.assertEqual(form.fields['first_name'].initial, 'Old')
        self.assertEqual(form.fields['last_name'].initial, 'Name')

    def test_valid_save_updates_profile_and_user_names(self):
        form = UserProfileForm(data={
            'first_name': 'New',
            'last_name': 'Case',
            'phone_number': '9876543210',
            'address': '2 Hill Road',
        }, instance=self.profile)
        self.assertTrue(form.is_valid())
        form.save()
        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.profile.phone_number, '9876543210')
        self.assertEqual(self.profile.address, '2 Hill Road')
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Case')

    def test_names_left_along_when_blank(self):
        form = UserProfileForm(data={
            'first_name': '', 'last_name': '',
            'phone_number': '1111111111', 'address': 'x',
        }, instance=self.profile)
        self.assertTrue(form.is_valid())
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertEqual(self.user.last_name, '')

    def test_address_and_phone_are_optional(self):
        form = UserProfileForm(data={
            'first_name': 'A', 'last_name': 'B',
            'phone_number': '', 'address': '',
        }, instance=self.profile)
        self.assertTrue(form.is_valid())

    def test_avatar_upload_accepted(self):
        form = UserProfileForm(
            data={'first_name': 'A', 'last_name': 'B', 'phone_number': '', 'address': ''},
            files={'avatar': SimpleUploadedFile('me.gif', TINY_GIF, content_type='image/gif')},
            instance=self.profile,
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data['avatar'].name.endswith('.gif'))

    def test_declared_field_set_matches_model_and_user_names(self):
        form = UserProfileForm(instance=self.profile)
        self.assertEqual(
            set(form.fields),
            {'first_name', 'last_name', 'phone_number', 'address', 'avatar'},
        )
