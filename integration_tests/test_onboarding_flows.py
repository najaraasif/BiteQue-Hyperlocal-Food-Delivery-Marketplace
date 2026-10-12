import io
import os
import shutil
import tempfile
import zlib
from decimal import Decimal

from PIL import Image as PILImage
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from merchant_app.models import (
    BankAccount,
    Restaurant,
    RestaurantMenu,
    merchantRegistration,
)
from rider_app.models import Rider


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


def png_upload(name):
    buffer = io.BytesIO()
    PILImage.new('RGB', (8, 8), (200, 40, 40)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class MerchantOnboardingTests(TestCase):
    """Registration -> approval -> restaurant -> menu -> bank account,
    asserted as one continuous journey with a customer watching."""

    def setUp(self):
        self.merchant_client = self.client_class()
        self.customer = User.objects.create_user(
            username='onb_customer', password='pw12345678'
        )
        self.customer_client = self.client_class()
        self.customer_client.force_login(self.customer)

    @property
    def merchant(self):
        return User.objects.get(username='onb_merchant')

    def register(self):
        return self.merchant_client.post(reverse('merchant_register'), {
            'username': 'onb_merchant',
            'name': 'Onboard Merchant',
            'number': '9876543210',
            'email': 'onb_merchant@example.com',
            'password': 'Str0ngPass!',
            'retypePassword': 'Str0ngPass!',
        })

    def approve_registration(self):
        merchantRegistration.objects.filter(
            username=self.merchant
        ).update(is_approved=True)

    def create_restaurant(self, **overrides):
        data = {
            'name': 'Onboard Kitchen',
            'email': 'onboard@example.com',
            'contact_number': '9876543210',
            'address': '1 Onboard Road',
            'city': 'Testville',
        }
        data.update(overrides)
        resp = self.merchant_client.post(reverse('add_restaurant'), data)
        Restaurant.objects.filter(name=data['name']).update(
            image=f'restaurantImages/{data["name"].lower().replace(" ", "")}.jpg'
        )
        return resp

    def approve_restaurant(self):
        Restaurant.objects.filter(name='Onboard Kitchen').update(
            is_approved=True
        )

    def test_registration_starts_unapproved(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_register_success'))
        registration = merchantRegistration.objects.get(
            username=self.merchant
        )
        self.assertFalse(registration.is_approved)

    def test_new_merchant_is_funneled_to_the_approval_notice(self):
        self.register()
        self.merchant_client.force_login(self.merchant)

        status_page = self.merchant_client.get(reverse('post-login-redirect'))
        self.assertEqual(status_page.url, reverse('add_restaurant'))

        add_page = self.merchant_client.get(reverse('add_restaurant'))
        self.assertEqual(add_page.status_code, 302)
        self.assertEqual(add_page.url, reverse('merchant_approval'))

        notice = self.merchant_client.get(reverse('merchant_approval'))
        self.assertEqual(notice.status_code, 200)
        self.assertTemplateUsed(notice, 'merchant_approval.html')

    def test_restaurant_creation_blocked_before_registration_approval(self):
        self.register()
        self.merchant_client.force_login(self.merchant)
        resp = self.create_restaurant()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('merchant_approval'))
        self.assertEqual(Restaurant.objects.count(), 0)

    def test_created_restaurant_is_hidden_until_approved(self):
        self.register()
        self.approve_registration()
        self.merchant_client.force_login(self.merchant)

        resp = self.create_restaurant()
        self.assertEqual(resp.url, reverse('restaurant_success'))
        restaurant = Restaurant.objects.get(name='Onboard Kitchen')
        self.assertFalse(restaurant.is_approved)

        home = self.customer_client.get(reverse('home'))
        listed = [r.pk for r in home.context['approved_restaurants']]
        self.assertNotIn(restaurant.pk, listed)

        awaiting = self.merchant_client.get(reverse('post-login-redirect'))
        self.assertEqual(awaiting.status_code, 200)
        self.assertTemplateUsed(awaiting, 'awaitingApproval.html')

    def test_approval_opens_dashboard_and_customer_listing(self):
        self.register()
        self.approve_registration()
        self.merchant_client.force_login(self.merchant)
        self.create_restaurant()
        self.approve_restaurant()

        go = self.merchant_client.get(reverse('post-login-redirect'))
        self.assertEqual(go.url, reverse('merchant_dashboard'))

        dashboard = self.merchant_client.get(reverse('merchant_dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context['total_orders_today'], 0)

        home = self.customer_client.get(reverse('home'))
        listed = [r.pk for r in home.context['approved_restaurants']]
        self.assertEqual(len(listed), 1)
        self.assertEqual(
            Restaurant.objects.get(name='Onboard Kitchen').pk, listed[0]
        )

    def test_menu_item_added_by_merchant_reaches_customer_menu(self):
        from merchant_app.models import SizeCategory
        self.register()
        self.approve_registration()
        self.merchant_client.force_login(self.merchant)
        self.create_restaurant()
        self.approve_restaurant()
        restaurant = Restaurant.objects.get(name='Onboard Kitchen')
        size, _ = SizeCategory.objects.get_or_create(name='Onboard Size')

        resp = self.merchant_client.post(reverse('add_item'), {
            'name': 'Onboard Bowl',
            'sizes_categories': size.pk,
            'category': 'Bowls',
            'description': 'Fresh',
            'price': '199.00',
            'available': True,
            'prep_time': 7,
            'veg_or_nonveg': 'veg',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('menu_dashboard'))

        menu = self.customer_client.get(
            reverse('user_view_menu', args=[restaurant.pk])
        )
        self.assertEqual(menu.status_code, 200)
        names = [i.name for i in menu.context['menus']]
        self.assertIn('Onboard Bowl', names)

    def test_bank_account_starts_pending_and_splits_correctly(self):
        self.register()
        self.approve_registration()
        self.merchant_client.force_login(self.merchant)

        added = self.merchant_client.post(reverse('add_bank_account'), {
            'bank_name': 'Onboard Bank',
            'account_holder_name': 'Holder',
            'account_number': '444444444444',
            'ifsc_code': 'O1IN0000001',
            'is_primary': True,
        })
        self.assertEqual(added.status_code, 302)

        listing = self.merchant_client.get(reverse('bank_account_list'))
        self.assertEqual(len(listing.context['pending_accounts']), 1)
        self.assertEqual(len(listing.context['approved_accounts']), 0)

        account = BankAccount.objects.get(account_number='444444444444')
        BankAccount.objects.filter(pk=account.pk).update(is_approved=True)
        listing = self.merchant_client.get(reverse('bank_account_list'))
        self.assertEqual(len(listing.context['pending_accounts']), 0)
        self.assertEqual(len(listing.context['approved_accounts']), 1)

    def test_menu_items_can_be_staged_before_restaurant_approval(self):
        from merchant_app.models import SizeCategory
        self.register()
        self.approve_registration()
        self.merchant_client.force_login(self.merchant)
        self.create_restaurant()
        restaurant = Restaurant.objects.get(name='Onboard Kitchen')
        size, _ = SizeCategory.objects.get_or_create(name='Staged Size')

        resp = self.merchant_client.post(reverse('add_item'), {
            'name': 'Staged Item',
            'sizes_categories': size.pk,
            'category': 'Bowls',
            'price': '50.00',
            'available': True,
            'prep_time': 5,
            'veg_or_nonveg': 'veg',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(RestaurantMenu.objects.count(), 1)

        home = self.customer_client.get(reverse('home'))
        listed = [r.pk for r in home.context['approved_restaurants']]
        self.assertNotIn(restaurant.pk, listed)

        menu = self.customer_client.get(
            reverse('user_view_menu', args=[restaurant.pk])
        )
        self.assertEqual(
            [i.name for i in menu.context['menus']], ['Staged Item']
        )


class RiderOnboardingTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.client = self.client_class()

    def payload(self, **overrides):
        data = {
            'username': 'onb_rider',
            'email': 'onb_rider@example.com',
            'password1': 'CarrotCake99!',
            'password2': 'CarrotCake99!',
            'full_name': 'Rita Onboard',
            'phone': '9876543210',
            'gender': 'M',
            'aadhar_number': '556677889900',
            'driving_license': 'DL-ONB-112233',
            'address': '1 Test Street',
            'area': 'Test Area',
            'pincode': '123456',
            'profile_photo': png_upload('profile.png'),
            'aadhar_front': png_upload('aadhar_front.png'),
            'aadhar_back': png_upload('aadhar_back.png'),
            'license_copy': png_upload('license.png'),
        }
        data.update(overrides)
        return data

    def register(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            resp = self.client.post(
                reverse('rider:registration'), self.payload()
            )
        assert resp.status_code == 302, resp.content
        return resp

    def approve(self):
        Rider.objects.filter(user__username='onb_rider').update(
            is_approved=True
        )

    def test_registration_form_renders(self):
        resp = self.client.get(reverse('rider:registration'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)

    def test_valid_registration_creates_pending_rider_and_user(self):
        resp = self.register()
        self.assertEqual(resp.url, reverse('rider:registration_success'))
        self.assertTrue(any(
            'Registration successful' in m for m in messages_of(resp)
        ))
        user = User.objects.get(username='onb_rider')
        self.assertEqual(user.first_name, 'Rita')
        rider = Rider.objects.get(user=user)
        self.assertFalse(rider.is_approved)
        self.assertFalse(rider.is_available)
        self.assertEqual(rider.aadhar_number, '556677889900')
        self.assertTrue(
            rider.profile_photo.name.startswith('riders/profiles/')
        )

    def test_registration_success_page_renders(self):
        resp = self.client.get(reverse('rider:registration_success'))
        self.assertEqual(resp.status_code, 200)

    def test_pending_rider_cannot_log_in(self):
        self.register()
        resp = self.client.post(reverse('rider:rider-login'), {
            'username': 'onb_rider', 'password': 'CarrotCake99!',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_plain_user_sent_to_registration_from_dashboard(self):
        plain = User.objects.create_user(
            username='onb_plain', password='pw12345678'
        )
        self.client.force_login(plain)
        resp = self.client.get(reverse('rider:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:registration'))
        self.assertTrue(any(
            'Rider profile not found' in m for m in messages_of(resp)
        ))

    def test_approval_unlocks_login_and_dashboard(self):
        self.register()
        self.approve()

        resp = self.client.post(reverse('rider:rider-login'), {
            'username': 'onb_rider', 'password': 'CarrotCake99!',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:dashboard'))

        dashboard = self.client.get(reverse('rider:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertTemplateUsed(dashboard, 'rider_app/dashboard.html')
        ctx = dashboard.context
        self.assertEqual(ctx['total_earnings'], 0)
        self.assertEqual(ctx['today_earnings'], 0)
        self.assertEqual(len(ctx['active_orders']), 0)
        self.assertEqual(len(ctx['completed_orders']), 0)
        self.assertEqual(ctx['acceptance_rate'], 0.0)

    def test_availability_toggle_roundtrip(self):
        self.register()
        self.approve()
        self.client.post(reverse('rider:rider-login'), {
            'username': 'onb_rider', 'password': 'CarrotCake99!',
        })

        first = self.client.post(reverse('rider:update_availability'))
        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertEqual(payload['status'], 'success')
        self.assertTrue(payload['is_available'])
        self.assertEqual(payload['button_text'], 'Available')

        second = self.client.post(reverse('rider:update_availability'))
        self.assertFalse(second.json()['is_available'])
        self.assertEqual(second.json()['button_text'], 'Not Available')

        rider = Rider.objects.get(user__username='onb_rider')
        self.assertFalse(rider.is_available)

    def test_availability_toggle_requires_authentication(self):
        resp = self.client.post(reverse('rider:update_availability'))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['status'], 'error')

    def test_logout_route_is_shadowed_by_the_user_logout_url(self):
        self.register()
        self.approve()
        self.client.post(reverse('rider:rider-login'), {
            'username': 'onb_rider', 'password': 'CarrotCake99!',
        })
        resp = self.client.get(reverse('rider:logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('user_login'))
        self.assertNotIn('_auth_user_id', self.client.session)


class CustomerOnboardingTests(TestCase):
    def setUp(self):
        self.client = self.client_class()

    def register(self, **overrides):
        data = {
            'username': 'onb_buyer',
            'name': 'Pat Onboard',
            'number': '9876543210',
            'email': 'onb_buyer@example.com',
            'password': 'Abcd1234!',
            'retypePassword': 'Abcd1234!',
            'whatsapp_consent': 'on',
        }
        data.update(overrides)
        return self.client.post(reverse('user_registration'), data)

    def test_registration_logs_in_and_lands_on_success_page(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('registration_success'))
        self.assertIn('_auth_user_id', self.client.session)

        success = self.client.get(reverse('registration_success'))
        self.assertEqual(success.status_code, 200)
        self.assertTemplateUsed(success, 'user_registration_success.html')

    def test_new_customer_dashboard_starts_at_zero(self):
        self.register()
        resp = self.client.get(reverse('user-dashboard'))
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertEqual(ctx['total_orders'], 0)
        self.assertEqual(ctx['ongoing_orders'], 0)
        self.assertEqual(ctx['delivered_orders'], 0)
        self.assertEqual(list(ctx['support_tickets']), [])
        self.assertEqual(list(ctx['user_feedback']), [])

    def test_profile_is_auto_created_for_new_customer(self):
        self.register()
        user = User.objects.get(username='onb_buyer')
        self.assertTrue(hasattr(user, 'userprofile'))
        self.assertTrue(user.userprofile.whatsapp_consent)
        self.assertEqual(user.userprofile.phone_number, '9876543210')

        page = self.client.get(reverse('profile'))
        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, 'profile_section.html')
