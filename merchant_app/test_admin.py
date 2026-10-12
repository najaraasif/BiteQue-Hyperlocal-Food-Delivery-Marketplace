from decimal import Decimal
from unittest import mock

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase

from .admin import (
    MerchantEarningAdmin,
    MerchantPaymentAdmin,
    TicketAdmin,
    TicketMessageAdmin,
    merchantRegistrationAdmin,
)
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


class MerchantAdminRegistrationTests(TestCase):
    def test_expected_models_are_registered(self):
        expected = [
            merchantRegistration, Restaurant, RestaurantMenu, BankAccount,
            MerchantPayment, MerchantEarning, SizeCategory, Review,
            Ticket, TicketMessage,
        ]
        for model in expected:
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)

    def test_registration_and_restaurant_use_custom_admins(self):
        self.assertIsInstance(
            admin.site._registry[merchantRegistration],
            merchantRegistrationAdmin,
        )
        from .admin import RestaurantAdmin
        self.assertIsInstance(
            admin.site._registry[Restaurant], RestaurantAdmin
        )

    def test_merchant_payment_admin_searches_related_fields(self):
        model_admin = admin.site._registry[MerchantPayment]
        self.assertIn('merchant__username', model_admin.search_fields)
        self.assertIn('restaurant__name', model_admin.search_fields)
        self.assertIn('screenshot_preview', model_admin.readonly_fields)

    def test_ticket_admin_is_readonly_on_timestamps(self):
        model_admin = admin.site._registry[Ticket]
        self.assertEqual(
            model_admin.readonly_fields,
            ('ticket_id', 'created_at', 'updated_at'),
        )
        self.assertIn('ticket_id', model_admin.search_fields)

    def test_merchant_registration_list_configuration(self):
        model_admin = admin.site._registry[merchantRegistration]
        self.assertEqual(
            model_admin.list_display,
            ['username', 'name', 'number', 'is_approved'],
        )


class MerchantAdminAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='merch_admin', email='merch_admin@example.com',
            password='pw12345678',
        )
        self.client.force_login(self.superuser)

    def test_admin_index_lists_merchant_models(self):
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp,
            '/admin/merchant_app/merchantregistration/',
        )

    def test_changelists_render(self):
        slugs = [
            'merchantregistration', 'restaurant', 'restaurantmenu',
            'bankaccount', 'merchantpayment', 'merchantearning',
            'sizecategory', 'review', 'ticket', 'ticketmessage',
        ]
        for slug in slugs:
            with self.subTest(slug=slug):
                resp = self.client.get(f'/admin/merchant_app/{slug}/')
                self.assertEqual(resp.status_code, 200)

    def test_anonymous_cannot_open_changelist(self):
        self.client.logout()
        resp = self.client.get('/admin/merchant_app/restaurant/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp.url)


class MerchantRegistrationApprovalEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='approval_owner', email='approval_owner@example.com',
            password='pw12345678',
        )
        self.merchant = merchantRegistration.objects.create(
            username=self.user, name='Approval Owner',
            number='9876543210.0', is_approved=False,
        )
        self.model_admin = admin.site._registry[merchantRegistration]
        self.request = mock.Mock()

    @mock.patch('merchant_app.admin.send_merchant_verification_email')
    def test_flipping_to_approved_sends_the_email(self, send_email):
        obj = merchantRegistration.objects.get(pk=self.merchant.pk)
        obj.is_approved = True
        form = mock.Mock()

        self.model_admin.save_model(self.request, obj, form, change=True)

        send_email.assert_called_once()
        self.merchant.refresh_from_db()
        self.assertTrue(self.merchant.is_approved)

    @mock.patch('merchant_app.admin.send_merchant_verification_email')
    def test_saving_without_approval_flip_does_not_send(self, send_email):
        obj = merchantRegistration.objects.get(pk=self.merchant.pk)
        obj.name = 'Renamed Owner'
        form = mock.Mock()

        self.model_admin.save_model(self.request, obj, form, change=True)
        send_email.assert_not_called()

    @mock.patch('merchant_app.admin.send_merchant_verification_email')
    def test_creating_a_new_merchant_does_not_send(self, send_email):
        fresh_user = User.objects.create_user(
            username='fresh_merchant', email='fresh@example.com',
            password='pw12345678',
        )
        obj = merchantRegistration(
            username=fresh_user, name='Fresh Merchant',
            number='1212121212.0', is_approved=True,
        )
        form = mock.Mock()
        self.model_admin.save_model(self.request, obj, form, change=False)
        send_email.assert_not_called()

    @mock.patch('merchant_app.admin.send_merchant_verification_email')
    def test_revoking_approval_does_not_send(self, send_email):
        self.merchant.is_approved = True
        self.merchant.save()
        obj = merchantRegistration.objects.get(pk=self.merchant.pk)
        obj.is_approved = False
        form = mock.Mock()

        self.model_admin.save_model(self.request, obj, form, change=True)
        send_email.assert_not_called()


class RestaurantApprovalEmailTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='rest_approver', password='pw12345678'
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Flip Kitchen',
            email='flip@example.com', contact_number='9876543210',
            address='1 Road', city='Town', is_approved=False,
        )
        self.model_admin = admin.site._registry[Restaurant]
        self.request = mock.Mock()

    @mock.patch('merchant_app.admin.send_merchant_restaurant_email')
    def test_flipping_restaurant_to_approved_sends_email(self, send_email):
        obj = Restaurant.objects.get(pk=self.restaurant.pk)
        obj.is_approved = True
        self.model_admin.save_model(self.request, obj, mock.Mock(),
                                    change=True)
        send_email.assert_called_once()

    @mock.patch('merchant_app.admin.send_merchant_restaurant_email')
    def test_saving_without_flip_does_not_send(self, send_email):
        obj = Restaurant.objects.get(pk=self.restaurant.pk)
        obj.city = 'New Town'
        self.model_admin.save_model(self.request, obj, mock.Mock(),
                                    change=True)
        send_email.assert_not_called()


class MerchantEarningPermissionTests(TestCase):
    def setUp(self):
        self.model_admin = admin.site._registry[MerchantEarning]
        self.request = mock.Mock()

    def test_earning_records_cannot_be_added_changed_or_deleted(self):
        self.assertFalse(
            self.model_admin.has_add_permission(self.request)
        )
        self.assertFalse(
            self.model_admin.has_change_permission(self.request)
        )
        self.assertFalse(
            self.model_admin.has_delete_permission(self.request)
        )

    def test_earning_admin_exposes_readonly_columns(self):
        for field in (
            'net_sales', 'weekly_sales', 'amount_paid', 'amount_pending',
            'last_updated',
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.model_admin.readonly_fields)


class MerchantPaymentScreenshotPreviewTests(TestCase):
    def setUp(self):
        self.merchant = User.objects.create_user(
            username='preview_owner', password='pw12345678'
        )
        restaurant = Restaurant.objects.create(
            owner=self.merchant, name='Preview Rest',
            email='preview@example.com', contact_number='9876543210',
            address='1 Road', city='Town',
        )
        self.payment = MerchantPayment.objects.create(
            merchant=self.merchant, restaurant=restaurant,
            amount_paid=Decimal('100.00'),
            payment_screenshot='payment_screenshots/proof.jpg',
        )
        self.model_admin = admin.site._registry[MerchantPayment]

    def test_preview_renders_an_image_tag_when_screenshot_exists(self):
        html = self.model_admin.screenshot_preview(self.payment)
        self.assertIn('<img', html)
        self.assertIn('payment_screenshots/proof.jpg', html)
        self.assertIn('width="100"', html)

    def test_preview_reports_absence_without_screenshot(self):
        self.payment.payment_screenshot = ''
        self.assertEqual(
            self.model_admin.screenshot_preview(self.payment),
            'No Screenshot',
        )


class TicketAdminBehaviorTests(TestCase):
    def setUp(self):
        self.merchant = User.objects.create_user(
            username='ticket_admin_user', password='pw12345678'
        )
        self.model_admin = admin.site._registry[TicketMessage]

    def test_short_message_keeps_short_text_intact(self):
        message = TicketMessage(
            ticket=None, sender=self.merchant, message='All good here'
        )
        self.assertEqual(
            self.model_admin.short_message(message), 'All good here'
        )

    def test_short_message_truncates_past_75_characters(self):
        long_text = 'x' * 100
        message = TicketMessage(
            ticket=None, sender=self.merchant, message=long_text
        )
        preview = self.model_admin.short_message(message)
        self.assertEqual(preview, 'x' * 75 + '...')

    def test_short_message_column_description(self):
        self.assertEqual(
            self.model_admin.short_message.short_description,
            'Message Preview',
        )

    def test_ticket_model_auto_generates_ticket_ids(self):
        first = Ticket.objects.create(
            merchant=self.merchant, category='technical',
            subject='First',
        )
        second = Ticket.objects.create(
            merchant=self.merchant, category='billing', subject='Second'
        )
        self.assertEqual(len(first.ticket_id), 7)
        self.assertTrue(first.ticket_id.isdigit())
        self.assertNotEqual(first.ticket_id, second.ticket_id)

    def test_ticket_changelist_search_matches_message_body(self):
        ticket = Ticket.objects.create(
            merchant=self.merchant, category='general',
            subject='Refund question',
        )
        TicketMessage.objects.create(
            ticket=ticket, sender=self.merchant,
            message='My refund is still missing',
        )
        superuser = User.objects.create_superuser(
            username='ticket_super', password='pw12345678'
        )
        self.client.force_login(superuser)
        resp = self.client.get(
            '/admin/merchant_app/ticketmessage/',
            {'q': 'still missing'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My refund is still missing')
