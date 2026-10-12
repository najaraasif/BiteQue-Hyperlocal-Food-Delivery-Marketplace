import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory

from .models import CustomerFeedback, Order, UserSupportTicket

TINY_GIF = (
    b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00'
    b'\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


def make_restaurant(name='Account Kitchen'):
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


def make_menu_item(restaurant, name='Test Burger'):
    size, _ = SizeCategory.objects.get_or_create(name=f'Regular {restaurant.name}')
    return RestaurantMenu.objects.create(
        restaurant=restaurant,
        name=name,
        category='Burgers',
        price=Decimal('100.00'),
        prep_time=10,
        sizes_categories=size,
        image=f'menu_images/{name.replace(" ", "").lower()}.jpg',
    )


def make_order(user, restaurant, status='pending'):
    return Order.objects.create(
        user=user, restaurant=restaurant, status=status,
        customer_name='Pat', customer_contact='', landmark='',
        delivery_address='1 Road', special_instructions='',
    )


def valid_registration(**overrides):
    data = {
        'username': 'registree1',
        'name': 'Pat Lee',
        'number': '9876543210',
        'email': 'registree1@example.com',
        'password': 'Abcd1234!',
        'retypePassword': 'Abcd1234!',
        'whatsapp_consent': 'on',
    }
    data.update(overrides)
    return data


def messages_of(response):
    return [m.message for m in get_messages(response.wsgi_request)]


class RegistrationViewTests(TestCase):
    def test_get_renders_form(self):
        resp = self.client.get(reverse('user_registration'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'userRegistration.html')
        self.assertIn('form', resp.context)

    def test_valid_post_creates_user_profile_and_logs_in(self):
        resp = self.client.post(reverse('user_registration'), valid_registration())
        self.assertRedirects(resp, reverse('registration_success'))
        user = User.objects.get(username='registree1')
        self.assertEqual(user.first_name, 'Pat')
        self.assertEqual(user.last_name, 'Lee')
        self.assertEqual(user.email, 'registree1@example.com')
        self.assertTrue(user.check_password('Abcd1234!'))
        self.assertEqual(user.userprofile.phone_number, '9876543210')
        self.assertTrue(user.userprofile.whatsapp_consent)
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    def test_single_word_name_leaves_last_name_blank(self):
        resp = self.client.post(
            reverse('user_registration'), valid_registration(name='Pat')
        )
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username='registree1')
        self.assertEqual(user.first_name, 'Pat')
        self.assertEqual(user.last_name, '')

    def test_whatsapp_consent_absent_stores_false(self):
        data = valid_registration()
        del data['whatsapp_consent']
        self.client.post(reverse('user_registration'), data)
        user = User.objects.get(username='registree1')
        self.assertFalse(user.userprofile.whatsapp_consent)

    def test_invalid_form_renders_with_field_errors(self):
        resp = self.client.post(
            reverse('user_registration'), valid_registration(username='ab')
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('username', resp.context['form'].errors)
        self.assertFalse(User.objects.filter(username='registree1').exists())

    def test_integrity_error_on_username_maps_to_field_error(self):
        with mock.patch(
            'user_app.views.User.objects.create_user',
            side_effect=IntegrityError('duplicate key: username taken'),
        ):
            resp = self.client.post(reverse('user_registration'), valid_registration())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context['form'].errors['username'], ['Username already exists']
        )

    def test_integrity_error_on_email_maps_to_field_error(self):
        with mock.patch(
            'user_app.views.User.objects.create_user',
            side_effect=IntegrityError('duplicate key: email taken'),
        ):
            resp = self.client.post(reverse('user_registration'), valid_registration())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context['form'].errors['email'], ['Email already exists']
        )

    def test_unrelated_integrity_error_maps_to_non_field_error(self):
        with mock.patch(
            'user_app.views.User.objects.create_user',
            side_effect=IntegrityError('check constraint violated'),
        ):
            resp = self.client.post(reverse('user_registration'), valid_registration())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context['form'].errors['__all__'],
            ['Registration error. Please try again.'],
        )

    def test_unexpected_exception_maps_to_non_field_error(self):
        with mock.patch(
            'user_app.views.User.objects.create_user',
            side_effect=RuntimeError('boom'),
        ):
            resp = self.client.post(reverse('user_registration'), valid_registration())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context['form'].errors['__all__'],
            ['An error occurred during registration. Please try again.'],
        )

    def test_authentication_failure_re_renders_without_login(self):
        with mock.patch('user_app.views.authenticate', return_value=None):
            resp = self.client.post(reverse('user_registration'), valid_registration())
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(User.objects.filter(username='registree1').exists())


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='loginuser', password='pw12345678'
        )

    def test_get_renders_login_form(self):
        resp = self.client.get(reverse('user_login'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'login.html')
        self.assertEqual(resp.context['next'], reverse('dashboard_home'))

    def test_get_with_next_keeps_target(self):
        resp = self.client.get(reverse('user_login'), {'next': reverse('checkout')})
        self.assertEqual(resp.context['next'], reverse('checkout'))

    def test_valid_post_logs_in_and_redirects_to_next(self):
        resp = self.client.post(reverse('user_login'), {
            'username': 'loginuser', 'password': 'pw12345678',
            'next': reverse('checkout'),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('checkout'))
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))

    def test_valid_post_without_next_goes_to_dashboard(self):
        resp = self.client.post(reverse('user_login'), {
            'username': 'loginuser', 'password': 'pw12345678',
        })
        self.assertEqual(resp.url, reverse('dashboard_home'))

    def test_next_from_query_string_is_honoured(self):
        resp = self.client.post(
            reverse('user_login') + '?next=' + reverse('view_cart'),
            {'username': 'loginuser', 'password': 'pw12345678'},
        )
        self.assertEqual(resp.url, reverse('view_cart'))

    def test_wrong_password_re_renders_with_errors(self):
        resp = self.client.post(reverse('user_login'), {
            'username': 'loginuser', 'password': 'wrongpass1',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_unknown_user_re_renders_with_errors(self):
        resp = self.client.post(reverse('user_login'), {
            'username': 'ghostuser', 'password': 'pw12345678',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)


class DashboardHomeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dashuser', password='pw12345678')
        self.restaurant = make_restaurant()
        self.other_user = User.objects.create_user(username='otherdash', password='pw12345678')

    def login(self):
        self.client.force_login(self.user)

    def test_login_required(self):
        resp = self.client.get(reverse('dashboard_home'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('next=' + reverse('dashboard_home'), resp.url)

    def test_counts_orders_by_status(self):
        for status in ('pending', 'confirmed', 'ready', 'out_for_delivery'):
            make_order(self.user, self.restaurant, status=status)
        make_order(self.user, self.restaurant, status='delivered')
        make_order(self.user, self.restaurant, status='delivered')
        make_order(self.other_user, self.restaurant, status='pending')
        self.login()
        resp = self.client.get(reverse('dashboard_home'))
        self.assertEqual(resp.context['total_orders'], 6)
        self.assertEqual(resp.context['ongoing_orders'], 4)
        self.assertEqual(resp.context['delivered_orders'], 2)

    def test_counts_only_open_support_tickets(self):
        UserSupportTicket.objects.create(
            user=self.user, subject='Open one', category='technical'
        )
        UserSupportTicket.objects.create(
            user=self.user, subject='Closed one', category='billing', status='closed'
        )
        UserSupportTicket.objects.create(
            user=self.other_user, subject='Foreign one', category='technical'
        )
        self.login()
        resp = self.client.get(reverse('dashboard_home'))
        self.assertEqual(len(resp.context['support_tickets']), 1)
        self.assertEqual(resp.context['support_tickets'][0].subject, 'Open one')

    def test_context_carries_profile_orders_and_feedback(self):
        order = make_order(self.user, self.restaurant, status='delivered')
        CustomerFeedback.objects.create(
            order=order, restaurant=self.restaurant, customer=self.user, rating=5
        )
        self.login()
        resp = self.client.get(reverse('dashboard_home'))
        self.assertEqual(resp.context['user_profile'], self.user.userprofile)
        self.assertEqual(len(resp.context['orders']), 1)
        self.assertEqual(len(resp.context['user_feedback']), 1)

    def test_empty_dashboard_starts_at_zero(self):
        self.login()
        resp = self.client.get(reverse('dashboard_home'))
        self.assertEqual(resp.context['total_orders'], 0)
        self.assertEqual(resp.context['ongoing_orders'], 0)
        self.assertEqual(resp.context['delivered_orders'], 0)
        self.assertEqual(list(resp.context['support_tickets']), [])
        self.assertEqual(list(resp.context['user_feedback']), [])

    def test_orders_sorted_newest_first(self):
        first = make_order(self.user, self.restaurant, status='delivered')
        second = make_order(self.user, self.restaurant, status='delivered')
        Order.objects.filter(pk=first.pk).update(
            created_at='2026-01-01T00:00:00Z'
        )
        Order.objects.filter(pk=second.pk).update(
            created_at='2026-02-01T00:00:00Z'
        )
        self.login()
        resp = self.client.get(reverse('dashboard_home'))
        ids = [o.id for o in resp.context['orders']]
        self.assertEqual(ids, [second.id, first.id])


class ProfileSectionTests(TestCase):
    def test_login_required(self):
        resp = self.client.get(reverse('profile-section'))
        self.assertEqual(resp.status_code, 302)

    def test_renders_profile_template(self):
        user = User.objects.create_user(username='sectuser', password='pw12345678')
        self.client.force_login(user)
        resp = self.client.get(reverse('profile-section'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'profile_section.html')


class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profuser', password='pw12345678',
            first_name='Old', last_name='Name',
        )
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('profile'))
        self.assertEqual(resp.status_code, 302)

    def test_get_prefills_names(self):
        resp = self.client.get(reverse('profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['form'].fields['first_name'].initial, 'Old')
        self.assertEqual(resp.context['form'].fields['last_name'].initial, 'Name')

    def test_post_updates_profile_and_user_names(self):
        resp = self.client.post(reverse('profile'), {
            'first_name': 'New',
            'last_name': 'Case',
            'phone_number': '9876543210',
            'address': '2 Hill Road',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('profile'))
        self.user.refresh_from_db()
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Case')
        self.assertEqual(self.user.userprofile.phone_number, '9876543210')
        self.assertEqual(self.user.userprofile.address, '2 Hill Road')
        self.assertIn('Profile updated successfully!', messages_of(resp))

    def test_post_with_invalid_avatar_re_renders_with_errors(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        resp = self.client.post(reverse('profile'), {
            'first_name': 'New', 'last_name': 'Case',
            'phone_number': '', 'address': '',
            'avatar': SimpleUploadedFile('notes.txt', b'plain', content_type='text/plain'),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('avatar', resp.context['form'].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Old')


class UpdateAvatarTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='biteque_media_')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.user = User.objects.create_user(username='avuser', password='pw12345678')
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.post(reverse('update_avatar'))
        self.assertEqual(resp.status_code, 302)

    def test_avatar_upload_saved_to_profile(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        resp = self.client.post(reverse('update_avatar'), {
            'avatar': SimpleUploadedFile('me.gif', TINY_GIF, content_type='image/gif'),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('profile'))
        self.user.userprofile.refresh_from_db()
        self.assertTrue(self.user.userprofile.avatar.name.startswith('avatars/'))
        self.assertIn('Avatar updated successfully!', messages_of(resp))

    def test_post_without_file_just_redirects(self):
        resp = self.client.post(reverse('update_avatar'), {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('profile'))
        self.user.userprofile.refresh_from_db()
        self.assertFalse(self.user.userprofile.avatar.name)

    def test_save_failure_reports_error_message(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        with mock.patch(
            'user_app.views.UserProfile.save',
            side_effect=RuntimeError('disk full'),
        ):
            resp = self.client.post(reverse('update_avatar'), {
                'avatar': SimpleUploadedFile('me.gif', TINY_GIF, content_type='image/gif'),
            })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('Error updating avatar: disk full', messages_of(resp))


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pwuser', password='pw12345678'
        )
        self.client.force_login(self.user)

    def form_data(self, old='pw12345678', new1='Newpass1234!', new2=None):
        return {
            'old_password': old,
            'new_password1': new1,
            'new_password2': new2 or new1,
        }

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('change_password'))
        self.assertEqual(resp.status_code, 302)

    def test_get_renders_change_form(self):
        resp = self.client.get(reverse('change_password'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'change_password.html')

    def test_valid_change_updates_password_and_redirects(self):
        resp = self.client.post(reverse('change_password'), self.form_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('profile'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Newpass1234!'))
        self.assertFalse(self.user.check_password('pw12345678'))
        self.assertIn('Your password was successfully updated!', messages_of(resp))

    def test_wrong_old_password_re_renders_with_error(self):
        resp = self.client.post(reverse('change_password'), self.form_data(old='nope1234'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('pw12345678'))

    def test_mismatched_new_passwords_rejected(self):
        resp = self.client.post(
            reverse('change_password'),
            self.form_data(new1='Newpass1234!', new2='Different1234!'),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('pw12345678'))


class UpdateProfileAliasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='aliasuser', password='pw12345678',
            first_name='Ann', last_name='Lee',
        )
        self.client.force_login(self.user)

    def test_alias_reverses_to_the_profile_update_path(self):
        self.assertEqual(reverse('update_profile'), '/profile/update/')

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('update_profile'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('next=', resp.url)

    def test_get_prefills_current_names_on_alias_path(self):
        resp = self.client.get(reverse('update_profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'profile_section.html')
        self.assertEqual(
            resp.context['form'].fields['first_name'].initial, 'Ann'
        )
        self.assertEqual(
            resp.context['form'].fields['last_name'].initial, 'Lee'
        )

    def test_post_on_alias_updates_names_and_profile_fields(self):
        resp = self.client.post(reverse('update_profile'), {
            'first_name': 'Anne',
            'last_name': 'Li',
            'phone_number': '9111222333',
            'address': '9 Alias Road',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('profile'))
        self.user.refresh_from_db()
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Anne')
        self.assertEqual(self.user.last_name, 'Li')
        self.assertEqual(
            self.user.userprofile.phone_number, '9111222333'
        )
        self.assertEqual(self.user.userprofile.address, '9 Alias Road')
        self.assertIn(
            'Profile updated successfully!', messages_of(resp)
        )

    def test_invalid_post_on_alias_renders_with_errors(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        resp = self.client.post(reverse('update_profile'), {
            'first_name': 'Anne',
            'last_name': 'Li',
            'phone_number': '',
            'address': '',
            'avatar': SimpleUploadedFile(
                'bad.txt', b'plain', content_type='text/plain'
            ),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('avatar', resp.context['form'].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ann')
