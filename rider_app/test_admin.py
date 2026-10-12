from datetime import date
from decimal import Decimal
from unittest import mock

import zlib

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase

from .admin import RiderAdmin, RiderEarningAdmin, OrderAssignmentAdmin
from .models import OrderAssignment, Rider, RiderBankAccount, RiderEarning, Transaction


def make_rider(username, approved=True, available=True):
    user = User.objects.create_user(username=username, password='pw12345678')
    aadhar = str(10_000_000_000 + zlib.crc32(username.encode()) % 10**11)
    return Rider.objects.create(
        user=user,
        phone='9876543210',
        gender='Male',
        aadhar_number=aadhar,
        driving_license=f'DL-{username}'[:20],
        address='1 Street',
        area='Area',
        pincode='123456',
        profile_photo='riders/profiles/p.jpg',
        aadhar_front='riders/aadhar/f.jpg',
        license_copy='riders/license/l.jpg',
        is_approved=approved,
        is_available=available,
    )


class RiderAdminRegistrationTests(TestCase):
    def test_expected_models_are_registered(self):
        for model in (Rider, RiderEarning, OrderAssignment, Transaction):
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)

    def test_rider_bank_account_is_only_an_inline(self):
        self.assertNotIn(RiderBankAccount, admin.site._registry)
        model_admin = admin.site._registry[Rider]
        inline_models = [inline.model for inline in model_admin.inlines]
        self.assertIn(RiderBankAccount, inline_models)

    def test_rider_admin_configuration(self):
        model_admin = admin.site._registry[Rider]
        self.assertIsInstance(model_admin, RiderAdmin)
        self.assertIn('is_approved', model_admin.list_editable)
        self.assertIn('is_available', model_admin.list_editable)
        self.assertEqual(
            model_admin.list_filter, ('is_approved', 'is_available', 'gender')
        )
        self.assertIn('user__username', model_admin.search_fields)
        for readonly in (
            'total_earnings_display', 'completed_orders_display',
            'acceptance_rate_display', 'registration_date',
        ):
            with self.subTest(field=readonly):
                self.assertIn(readonly, model_admin.readonly_fields)

    def test_rider_admin_actions_are_declared(self):
        model_admin = admin.site._registry[Rider]
        self.assertEqual(
            model_admin.actions,
            ['approve_riders', 'make_available', 'make_unavailable'],
        )

    def test_assignment_admin_configuration(self):
        model_admin = admin.site._registry[OrderAssignment]
        self.assertIsInstance(model_admin, OrderAssignmentAdmin)
        self.assertEqual(model_admin.list_filter, ('status',))
        self.assertIn('rider__user__username', model_admin.search_fields)
        self.assertIn('assigned_at', model_admin.readonly_fields)


class RiderAdminAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='rider_admin_super', password='pw12345678'
        )
        self.client.force_login(self.superuser)

    def test_changelists_render(self):
        for slug in ('rider', 'riderearning', 'orderassignment', 'transaction'):
            with self.subTest(slug=slug):
                resp = self.client.get(f'/admin/rider_app/{slug}/')
                self.assertEqual(resp.status_code, 200)

    def test_rider_change_form_renders_with_fieldsets(self):
        rider = make_rider('change_form_rider')
        resp = self.client.get(
            f'/admin/rider_app/rider/{rider.pk}/change/'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Verification Documents')
        self.assertContains(resp, 'Performance Metrics')

    def test_anonymous_visitor_is_redirected(self):
        self.client.logout()
        resp = self.client.get('/admin/rider_app/rider/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp.url)


class RiderAdminActionTests(TestCase):
    def setUp(self):
        self.model_admin = admin.site._registry[Rider]
        self.request = mock.Mock()

    @mock.patch.object(RiderAdmin, 'message_user')
    def test_approve_riders_action_marks_selected(self, message_user):
        first = make_rider('action_one', approved=False)
        second = make_rider('action_two', approved=False)

        self.model_admin.approve_riders(
            self.request, Rider.objects.filter(pk__in=[first.pk, second.pk])
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_approved)
        self.assertTrue(second.is_approved)
        message_user.assert_called_once_with(
            self.request, '2 riders were approved'
        )

    @mock.patch.object(RiderAdmin, 'message_user')
    def test_make_available_action(self, message_user):
        rider = make_rider('action_avail', available=False)
        self.model_admin.make_available(
            self.request, Rider.objects.filter(pk=rider.pk)
        )
        rider.refresh_from_db()
        self.assertTrue(rider.is_available)
        message_user.assert_called_once_with(
            self.request, '1 riders were marked available'
        )

    @mock.patch.object(RiderAdmin, 'message_user')
    def test_make_unavailable_action(self, message_user):
        rider = make_rider('action_busy', available=True)
        self.model_admin.make_unavailable(
            self.request, Rider.objects.filter(pk=rider.pk)
        )
        rider.refresh_from_db()
        self.assertFalse(rider.is_available)
        message_user.assert_called_once_with(
            self.request, '1 riders were marked unavailable'
        )


class RiderDisplayColumnTests(TestCase):
    def setUp(self):
        self.model_admin = admin.site._registry[Rider]
        self.rider = make_rider('display_rider')

    def test_total_earnings_without_history(self):
        rendered = self.model_admin.total_earnings_display(self.rider)
        self.assertIn('0.00', rendered)

    def test_total_earnings_includes_recorded_amounts(self):
        RiderEarning.objects.create(
            rider=self.rider, date=date(2026, 1, 5),
            total_earnings=Decimal('1500.50'), orders_completed=3,
        )
        rendered = self.model_admin.total_earnings_display(self.rider)
        self.assertIn('1,500.50', rendered)
        self.assertEqual(
            self.model_admin.total_earnings_display.short_description,
            'Total',
        )

    def test_current_balance_reflects_processed_payments(self):
        self.assertEqual(
            self.model_admin.current_balance_display(self.rider),
            self.model_admin.total_earnings_display(self.rider),
        )
        RiderEarning.objects.create(
            rider=self.rider, date=date(2026, 1, 6),
            total_earnings=Decimal('500.00'), orders_completed=2,
        )
        Transaction.objects.create(
            rider=self.rider, amount=Decimal('200.00'),
            transaction_type='payment', description='Cash out',
            processed=True,
        )
        rendered = self.model_admin.current_balance_display(self.rider)
        self.assertIn('300.00', rendered)

    def test_acceptance_rate_defaults_to_zero(self):
        self.assertEqual(
            self.model_admin.acceptance_rate_display(self.rider), '0.0%'
        )

    def test_completed_orders_counts_deliveries(self):
        self.assertEqual(
            self.model_admin.completed_orders_display(self.rider), 0
        )

    def test_registration_date_format(self):
        rendered = self.model_admin.registration_date(self.rider)
        self.assertEqual(
            rendered, self.rider.created_at.strftime('%b %d, %Y')
        )

    def test_today_earnings_defaults_to_zero(self):
        self.assertIn('0.00', self.model_admin.today_earnings_display(self.rider))

    def test_photo_previews_render_placeholders_when_empty(self):
        self.rider.profile_photo = ''
        self.rider.aadhar_front = ''
        self.rider.license_copy = ''
        self.assertEqual(
            self.model_admin.profile_photo_preview(self.rider), '-'
        )
        self.assertEqual(
            self.model_admin.aadhar_front_preview(self.rider), '-'
        )
        self.assertEqual(
            self.model_admin.license_copy_preview(self.rider), '-'
        )

    def test_photo_previews_render_image_tags_when_set(self):
        html = self.model_admin.profile_photo_preview(self.rider)
        self.assertIn('<img', html)
        self.assertIn('riders/profiles/p.jpg', html)

    def test_earning_admin_earnings_column(self):
        earning = RiderEarning.objects.create(
            rider=self.rider, date=date(2026, 2, 1),
            total_earnings=Decimal('40.00'), orders_completed=1,
        )
        earning_admin = admin.site._registry[RiderEarning]
        self.assertIn('40.00', earning_admin.total_earnings_display(earning))
        self.assertEqual(
            earning_admin.total_earnings_display.short_description,
            'Earnings',
        )
