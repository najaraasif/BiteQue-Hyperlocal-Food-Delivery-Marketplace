import io
import os
import shutil
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from PIL import Image as PILImage

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from user_app.models import Order

from rider_app.forms import BankDetailsForm
from rider_app.models import (
    OrderAssignment,
    Rider,
    RiderBankAccount,
    RiderEarning,
    Transaction,
)

from .test_assignment_flow import make_order, make_rider, make_user


def make_order_index(index, status='confirmed', **kwargs):
    return make_order(make_user(f'rview_cust_{index}'), status=status, **kwargs)


def message_list(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


def message_text(response):
    return ' '.join(message_list(response))


def close_response(response):
    if getattr(response, 'streaming', False):
        for _ in response:
            pass
    if hasattr(response, 'close'):
        response.close()


def png_upload(name):
    buffer = io.BytesIO()
    PILImage.new('RGB', (8, 8), (200, 40, 40)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class RiderDashboardTests(TestCase):
    def test_requires_login_and_rider_profile(self):
        anonymous = self.client.get(reverse('rider:dashboard'))
        self.assertEqual(anonymous.status_code, 302)

        plain = make_user('dash_noprofile')
        self.client.force_login(plain)
        resp = self.client.get(reverse('rider:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:registration'))
        self.assertIn('Rider profile not found', message_text(resp))

    def test_context_aggregates_and_weekly_window(self):
        today = datetime.now().date()
        rider = make_rider('dash_ctx', today_earnings=Decimal('7.00'))
        RiderEarning.objects.create(
            rider=rider,
            date=today,
            total_earnings=Decimal('99.00'),
            orders_completed=1,
        )
        RiderEarning.objects.create(
            rider=rider,
            date=today - timedelta(days=2),
            total_earnings=Decimal('55.50'),
            orders_completed=2,
        )
        RiderEarning.objects.create(
            rider=rider,
            date=today - timedelta(days=10),
            total_earnings=Decimal('30.00'),
            orders_completed=1,
        )
        Transaction.objects.create(
            rider=rider,
            amount=Decimal('40.00'),
            transaction_type='payment',
            description='payout',
            processed=True,
        )
        OrderAssignment.objects.create(
            order=make_order_index(1, status='ready'),
            rider=rider,
            status='accepted',
            response_time=timedelta(seconds=30),
            acceptance_score=Decimal('100.00'),
        )
        OrderAssignment.objects.create(
            order=make_order_index(2, status='ready'),
            rider=rider,
            status='delivered',
        )

        self.client.force_login(rider.user)
        resp = self.client.get(reverse('rider:dashboard'))
        self.assertEqual(resp.status_code, 200)
        context = resp.context

        self.assertEqual(context['rider'], rider)
        self.assertEqual(context['total_earnings'], Decimal('184.50'))
        self.assertEqual(context['today_earnings'], Decimal('7.00'))
        self.assertEqual(context['current_balance'], Decimal('144.50'))
        self.assertEqual(context['total_orders'], 1)
        self.assertEqual(context['acceptance_rate'], 50.0)
        self.assertEqual(context['acceptance_stats']['score'], 50.0)

        weekly = context['weekly_earnings']
        expected_dates = [
            today - timedelta(days=offset) for offset in range(7, 0, -1)
        ]
        self.assertEqual(len(weekly), 7)
        self.assertEqual([entry['date'] for entry in weekly], expected_dates)
        self.assertEqual(weekly[5]['earnings'], 55.5)
        self.assertEqual(weekly[0]['earnings'], 0)
        self.assertEqual(weekly[6]['earnings'], 0)

        self.assertEqual(context['earnings'][0].date, today)

    def test_active_orders_only_include_live_orders(self):
        ready_order = make_order_index(3, status='ready')
        confirmed_order = make_order_index(4, status='confirmed')
        rejected_order = make_order_index(5, status='ready')
        out_for_delivery_order = make_order_index(6, status='out_for_delivery')
        rider = make_rider('dash_active')
        ready_pending = OrderAssignment.objects.create(
            order=ready_order, rider=rider, status='pending',
        )
        OrderAssignment.objects.create(
            order=confirmed_order, rider=rider, status='pending',
        )
        OrderAssignment.objects.create(
            order=rejected_order, rider=rider, status='rejected',
        )
        accepted = OrderAssignment.objects.create(
            order=out_for_delivery_order, rider=rider, status='accepted',
        )

        self.client.force_login(rider.user)
        resp = self.client.get(reverse('rider:dashboard'))
        active_ids = {row.order_id for row in resp.context['active_orders']}
        self.assertEqual(
            active_ids, {ready_pending.order_id, accepted.order_id}
        )

    def test_recent_lists_are_capped_at_five(self):
        today = datetime.now().date()
        rider = make_rider('dash_cap')
        for index in range(6):
            OrderAssignment.objects.create(
                order=make_order_index(60 + index, status='ready'),
                rider=rider,
                status='delivered',
            )
        for offset in range(6):
            RiderEarning.objects.create(
                rider=rider,
                date=today - timedelta(days=offset),
                total_earnings=Decimal('10.00'),
                orders_completed=1,
            )

        self.client.force_login(rider.user)
        resp = self.client.get(reverse('rider:dashboard'))
        completed = list(resp.context['completed_orders'])
        self.assertEqual(len(completed), 5)
        self.assertTrue(
            all(row.status == 'delivered' for row in completed)
        )
        earnings = list(resp.context['earnings'])
        self.assertEqual(len(earnings), 5)
        self.assertEqual(earnings[0].date, today)
        self.assertEqual(earnings[4].date, today - timedelta(days=4))


class RiderEarningsPageTests(TestCase):
    def test_requires_login_and_exposes_earnings_context(self):
        anonymous = self.client.get(reverse('rider:earnings'))
        self.assertEqual(anonymous.status_code, 302)

        rider = make_rider('earn_ctx')
        fresh = OrderAssignment.objects.create(
            order=make_order_index(7, status='ready'),
            rider=rider,
            status='delivered',
        )
        stale = OrderAssignment.objects.create(
            order=make_order_index(8, status='ready'),
            rider=rider,
            status='delivered',
        )
        OrderAssignment.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timedelta(days=9)
        )
        RiderEarning.objects.create(
            rider=rider,
            date=datetime.now().date(),
            total_earnings=Decimal('70.00'),
            orders_completed=3,
        )
        old_tx = Transaction.objects.create(
            rider=rider,
            amount=Decimal('10.00'),
            transaction_type='payment',
            description='old',
            processed=True,
        )
        new_tx = Transaction.objects.create(
            rider=rider,
            amount=Decimal('20.00'),
            transaction_type='pending',
            description='new',
        )

        self.client.force_login(rider.user)
        resp = self.client.get(reverse('rider:earnings'))
        self.assertEqual(resp.status_code, 200)
        context = resp.context

        self.assertEqual(context['rider'], rider)
        self.assertEqual(list(context['weekly_orders']), [fresh])
        self.assertEqual(context['total_orders'], 1)
        self.assertEqual(list(context['transactions']), [new_tx, old_tx])
        self.assertEqual(context['total_earnings'], Decimal('70.00'))
        self.assertEqual(context['current_balance'], Decimal('60.00'))
        self.assertEqual(
            list(context['earnings']),
            list(RiderEarning.objects.filter(rider=rider)),
        )

    def test_internal_error_redirects_to_dashboard(self):
        rider = make_rider('earn_err')
        self.client.force_login(rider.user)
        with mock.patch(
            'rider_app.views.get_object_or_404',
            side_effect=RuntimeError('boom'),
        ):
            with self.assertLogs('rider_app.views', level='ERROR'):
                resp = self.client.get(reverse('rider:earnings'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:dashboard'))
        self.assertIn('Error loading earnings page', message_list(resp))


class EarningDetailsApiTests(TestCase):
    def test_requires_login_and_returns_exact_payload(self):
        rider = make_rider('ed_rider')
        earning = RiderEarning.objects.create(
            rider=rider,
            date=date(2026, 3, 5),
            total_earnings=Decimal('123.45'),
            orders_completed=3,
            distance_km=Decimal('6.50'),
            distance_earning=Decimal('50.00'),
            commission_earning=Decimal('73.45'),
        )

        anonymous = self.client.get(
            reverse('rider:earning_details', args=[earning.pk])
        )
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(rider.user)
        resp = self.client.get(
            reverse('rider:earning_details', args=[earning.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {
            'status': 'success',
            'distance_km': 6.5,
            'distance_earning': 50.0,
            'commission_earning': 73.45,
            'total_earning': 123.45,
            'orders_completed': 3,
            'date': 'Mar 05, 2026',
        })

    def test_foreign_earning_returns_404_payload(self):
        owner = make_rider('ed_owner')
        stranger = make_rider('ed_stranger')
        earning = RiderEarning.objects.create(
            rider=owner,
            date=date(2026, 3, 5),
            total_earnings=Decimal('10.00'),
            orders_completed=1,
        )
        self.client.force_login(stranger.user)
        resp = self.client.get(
            reverse('rider:earning_details', args=[earning.pk])
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json(), {
            'status': 'error',
            'message': 'Earning record not found',
        })


class OrderEarningDetailsApiTests(TestCase):
    def test_requires_login_and_returns_exact_payload(self):
        rider = make_rider('oe_rider')
        order = make_order_index(9)
        OrderAssignment.objects.create(
            order=order, rider=rider, status='delivered'
        )
        Order.objects.filter(pk=order.pk).update(
            commission=Decimal('16.00'), total_earning=Decimal('56.00')
        )
        order.refresh_from_db()

        anonymous = self.client.get(
            reverse('rider:order_earning_details', args=[order.pk])
        )
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(rider.user)
        resp = self.client.get(
            reverse('rider:order_earning_details', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {
            'status': 'success',
            'date': order.created_at.strftime('%b %d, %Y'),
            'order_id': order.pk,
            'distance_km': 4.0,
            'distance_earning': 40.0,
            'commission_earning': 16.0,
            'total_earning': 56.0,
            'restaurant': 'Test Kitchen',
            'customer': 'Test Customer',
            'delivery_address': '1 Delivery Road',
        })

    def test_order_not_delivered_by_caller_returns_404(self):
        rider = make_rider('oe_r1')
        other = make_rider('oe_r2')
        own_pending = make_order_index(10)
        OrderAssignment.objects.create(
            order=own_pending, rider=rider, status='accepted'
        )
        foreign = make_order_index(11)
        OrderAssignment.objects.create(
            order=foreign, rider=other, status='delivered'
        )

        self.client.force_login(rider.user)
        resp = self.client.get(
            reverse('rider:order_earning_details', args=[own_pending.pk])
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json(), {
            'status': 'error',
            'message': 'Order not found or not delivered by you',
        })

        resp = self.client.get(
            reverse('rider:order_earning_details', args=[foreign.pk])
        )
        self.assertEqual(resp.status_code, 404)


class RiderOrderDetailTests(TestCase):
    def test_accepted_assignment_renders_detail_page(self):
        rider = make_rider('od_r1')
        order = make_order_index(12, status='out_for_delivery')
        assignment = OrderAssignment.objects.create(
            order=order, rider=rider, status='accepted'
        )

        self.client.force_login(rider.user)
        resp = self.client.get(
            reverse('rider:rider_order_detail', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('dest_lat', resp.context)
        self.assertEqual(resp.context['order'], order)
        self.assertEqual(resp.context['assignment'], assignment)
        self.assertEqual(resp.context['rider'], rider)
        self.assertEqual(resp.context['dest_lat'], order.dest_lat)
        self.assertEqual(
            resp.context['delivery_fee'], order.distance_earning
        )

    def test_pending_assignment_renders_acceptance_prompt(self):
        order = make_order_index(13, status='ready')
        rider = make_rider('od_r2')
        assignment = OrderAssignment.objects.create(
            order=order, rider=rider, status='pending'
        )

        self.client.force_login(rider.user)
        resp = self.client.get(
            reverse('rider:rider_order_detail', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('dest_lat', resp.context)
        self.assertEqual(resp.context['assignment'], assignment)
        self.assertEqual(
            resp.context['delivery_fee'], order.distance_earning
        )

    def test_foreign_assignment_404_and_missing_profile_redirects(self):
        order = make_order_index(14, status='ready')
        rider = make_rider('od_r3')
        OrderAssignment.objects.create(
            order=order, rider=make_rider('od_r4'), status='pending'
        )

        self.client.force_login(rider.user)
        resp = self.client.get(
            reverse('rider:rider_order_detail', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 404)

        plain = make_user('od_plain')
        self.client.force_login(plain)
        resp = self.client.get(
            reverse('rider:rider_order_detail', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:dashboard'))
        self.assertIn('Rider profile not found', message_list(resp))


class AcceptAssignmentActionTests(TestCase):
    def test_pending_assignment_is_accepted_with_confirmation(self):
        order = make_order_index(15, status='ready')
        rider = make_rider('aa_r1')
        assignment = OrderAssignment.objects.create(
            order=order, rider=rider, status='pending'
        )

        self.client.force_login(rider.user)
        resp = self.client.post(
            reverse('rider:accept_order_assignment_action', args=[order.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse('rider:rider_order_detail', args=[order.pk]),
        )
        self.assertEqual(message_list(resp), ['Order accepted successfully!'])
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, 'accepted')

    def test_already_accepted_status_reports_info(self):
        rider = make_rider('aa_r2')
        accepted_order = make_order_index(16, status='out_for_delivery')
        accepted = OrderAssignment.objects.create(
            order=accepted_order, rider=rider, status='accepted'
        )

        self.client.force_login(rider.user)
        resp = self.client.post(
            reverse(
                'rider:accept_order_assignment_action',
                args=[accepted_order.pk],
            )
        )
        self.assertEqual(message_list(resp), ['Order was already accepted.'])

        accepted.refresh_from_db()
        self.assertEqual(accepted.status, 'accepted')

    def test_rejected_status_reports_error(self):
        rejected_order = make_order_index(17, status='ready')
        rider = make_rider('aa_r2b')
        rejected = OrderAssignment.objects.create(
            order=rejected_order, rider=rider, status='rejected'
        )

        self.client.force_login(rider.user)
        resp = self.client.post(
            reverse(
                'rider:accept_order_assignment_action',
                args=[rejected_order.pk],
            )
        )
        self.assertEqual(
            message_list(resp),
            ['Order cannot be accepted. Current status: rejected'],
        )

        rejected.refresh_from_db()
        self.assertEqual(rejected.status, 'rejected')

    def test_login_method_and_missing_assignment_guards(self):
        order = make_order_index(18, status='ready')
        anonymous = self.client.post(
            reverse('rider:accept_order_assignment_action', args=[order.pk])
        )
        self.assertEqual(anonymous.status_code, 302)

        rider = make_rider('aa_r3')
        self.client.force_login(rider.user)
        get_resp = self.client.get(
            reverse('rider:accept_order_assignment_action', args=[order.pk])
        )
        self.assertEqual(get_resp.status_code, 405)

        missing = self.client.post(
            reverse('rider:accept_order_assignment_action', args=[987654])
        )
        self.assertEqual(missing.status_code, 302)
        self.assertEqual(
            missing.url,
            reverse('rider:rider_order_detail', args=[987654]),
        )
        self.assertEqual(message_list(missing), ['Order assignment not found.'])


class BankAccountManagementTests(TestCase):
    def valid_payload(self, **overrides):
        payload = {
            'account_holder_name': 'Rider Holder',
            'account_number': '12345678901',
            'bank_name': 'State Bank',
            'ifsc_code': 'SBIN0000123',
        }
        payload.update(overrides)
        return payload

    def test_requires_login_and_lists_accounts(self):
        anonymous = self.client.get(reverse('rider:bank_details_list'))
        self.assertEqual(anonymous.status_code, 302)

        rider = make_rider('bk_r1')
        account = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Rider Holder',
            account_number='9876543210123456',
            bank_name='State Bank',
            ifsc_code='SBIN0000123',
        )
        self.client.force_login(rider.user)
        resp = self.client.get(reverse('rider:bank_details_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.context['form'], BankDetailsForm)
        self.assertEqual(resp.context['rider'], rider)
        self.assertEqual(list(resp.context['bank_accounts']), [account])

    def test_posting_keeps_exactly_one_primary_account(self):
        rider = make_rider('bk_r2')
        self.client.force_login(rider.user)

        first = self.client.post(
            reverse('rider:bank_details_list'),
            self.valid_payload(account_number='11112222333'),
        )
        self.assertEqual(first.status_code, 302)
        self.assertIn('Bank account added successfully', message_text(first))
        first_account = RiderBankAccount.objects.get(
            account_number='11112222333'
        )
        self.assertTrue(first_account.is_primary)

        second = self.client.post(
            reverse('rider:bank_details_list'),
            self.valid_payload(account_number='22223334444'),
        )
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            RiderBankAccount.objects.filter(rider=rider).count(), 2
        )
        first_account.refresh_from_db()
        self.assertTrue(first_account.is_primary)
        second_account = RiderBankAccount.objects.get(
            account_number='22223334444'
        )
        self.assertFalse(second_account.is_primary)

        third = self.client.post(
            reverse('rider:bank_details_list'),
            self.valid_payload(account_number='33334445555', is_primary='on'),
        )
        self.assertEqual(third.status_code, 302)
        third_account = RiderBankAccount.objects.get(
            account_number='33334445555'
        )
        self.assertTrue(third_account.is_primary)
        first_account.refresh_from_db()
        second_account.refresh_from_db()
        self.assertFalse(first_account.is_primary)
        self.assertFalse(second_account.is_primary)
        self.assertEqual(
            RiderBankAccount.objects.filter(
                rider=rider, is_primary=True
            ).count(),
            1,
        )

    def test_invalid_post_renders_form_errors_without_saving(self):
        rider = make_rider('bk_r3')
        self.client.force_login(rider.user)
        resp = self.client.post(
            reverse('rider:bank_details_list'),
            self.valid_payload(account_number='123'),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('account_number', resp.context['form'].errors)
        self.assertEqual(
            RiderBankAccount.objects.filter(rider=rider).count(), 0
        )
        self.assertIn('correct the errors', message_text(resp))

    def test_delete_guards_primary_foreign_and_method(self):
        rider = make_rider('bk_r4')
        primary = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Holder One',
            account_number='111222333444',
            bank_name='Bank One',
            ifsc_code='B1IN0000001',
            is_primary=True,
        )
        secondary = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Holder Two',
            account_number='555666777888',
            bank_name='Bank Two',
            ifsc_code='B2IN0000002',
        )
        other = make_rider('bk_other')
        foreign = RiderBankAccount.objects.create(
            rider=other,
            account_holder_name='Holder Three',
            account_number='999888777666',
            bank_name='Bank Three',
            ifsc_code='B3IN0000003',
        )

        self.client.force_login(rider.user)
        foreign_resp = self.client.get(
            reverse('rider:delete_bank_account', args=[foreign.pk])
        )
        self.assertEqual(foreign_resp.status_code, 405)

        method_resp = self.client.get(
            reverse('rider:delete_bank_account', args=[secondary.pk])
        )
        self.assertEqual(method_resp.status_code, 405)

        foreign_post = self.client.post(
            reverse('rider:delete_bank_account', args=[foreign.pk])
        )
        self.assertEqual(foreign_post.status_code, 404)
        self.assertTrue(
            RiderBankAccount.objects.filter(pk=foreign.pk).exists()
        )

        blocked = self.client.post(
            reverse('rider:delete_bank_account', args=[primary.pk])
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(
            RiderBankAccount.objects.filter(pk=primary.pk).exists()
        )
        self.assertIn(
            'cannot delete your primary', message_text(blocked)
        )

        removed = self.client.post(
            reverse('rider:delete_bank_account', args=[secondary.pk])
        )
        self.assertEqual(removed.status_code, 302)
        self.assertFalse(
            RiderBankAccount.objects.filter(pk=secondary.pk).exists()
        )
        self.assertIn('Bank account deleted', message_text(removed))

    def test_set_primary_demotes_previous_and_blocks_foreign(self):
        rider = make_rider('bk_r5')
        primary = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Holder One',
            account_number='12121212121',
            bank_name='Bank One',
            ifsc_code='B1IN0000011',
            is_primary=True,
        )
        secondary = RiderBankAccount.objects.create(
            rider=rider,
            account_holder_name='Holder Two',
            account_number='34343434343',
            bank_name='Bank Two',
            ifsc_code='B2IN0000012',
        )
        other = make_rider('bk_other2')
        foreign = RiderBankAccount.objects.create(
            rider=other,
            account_holder_name='Holder Three',
            account_number='56565656565',
            bank_name='Bank Three',
            ifsc_code='B3IN0000013',
        )

        self.client.force_login(rider.user)
        method_resp = self.client.get(
            reverse('rider:set_primary_bank_account', args=[secondary.pk])
        )
        self.assertEqual(method_resp.status_code, 405)

        resp = self.client.post(
            reverse('rider:set_primary_bank_account', args=[secondary.pk])
        )
        self.assertEqual(resp.status_code, 302)
        secondary.refresh_from_db()
        primary.refresh_from_db()
        self.assertTrue(secondary.is_primary)
        self.assertFalse(primary.is_primary)
        self.assertIn(secondary.account_number, message_text(resp))
        self.assertIn('primary', message_text(resp))

        foreign_resp = self.client.post(
            reverse('rider:set_primary_bank_account', args=[foreign.pk])
        )
        self.assertEqual(foreign_resp.status_code, 404)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_primary)
        self.assertEqual(
            RiderBankAccount.objects.filter(
                rider=rider, is_primary=True
            ).count(),
            1,
        )


class RiderRegistrationTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def payload(self, **overrides):
        data = {
            'username': 'reg_rider_one',
            'email': 'reg_one@example.com',
            'password1': 'CarrotCake99!',
            'password2': 'CarrotCake99!',
            'full_name': 'Maria Gonzalez Cruz',
            'phone': '9876543210',
            'gender': 'M',
            'aadhar_number': '445566778899',
            'driving_license': 'DL-REG-998877',
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

    def test_get_renders_registration_form(self):
        resp = self.client.get(reverse('rider:registration'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)

    def test_valid_post_creates_pending_rider_with_documents(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            resp = self.client.post(
                reverse('rider:registration'), self.payload()
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:registration_success'))
        self.assertIn('Registration successful', message_text(resp))

        user = User.objects.get(username='reg_rider_one')
        self.assertEqual(user.first_name, 'Maria')
        self.assertEqual(user.last_name, 'Gonzalez Cruz')

        rider = Rider.objects.get(user=user)
        self.assertFalse(rider.is_approved)
        self.assertFalse(rider.is_available)
        self.assertEqual(rider.aadhar_number, '445566778899')
        self.assertEqual(rider.driving_license, 'DL-REG-998877')
        self.assertTrue(
            rider.profile_photo.name.startswith('riders/profiles/')
        )
        self.assertTrue(
            rider.aadhar_front.name.startswith('riders/aadhar/')
        )
        self.assertTrue(
            rider.license_copy.name.startswith('riders/license/')
        )
        self.assertTrue(
            os.path.exists(
                os.path.join(self.media_root, rider.aadhar_front.name)
            )
        )
        self.assertTrue(
            os.path.exists(
                os.path.join(self.media_root, rider.profile_photo.name)
            )
        )

    def test_invalid_post_creates_no_user_or_rider(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            resp = self.client.post(
                reverse('rider:registration'),
                self.payload(aadhar_number='123'),
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn('aadhar_number', resp.context['form'].errors)
        self.assertFalse(User.objects.filter(username='reg_rider_one').exists())
        self.assertFalse(Rider.objects.filter(aadhar_number='123').exists())


class RiderLoginLogoutTests(TestCase):
    def test_approved_rider_logs_in_to_dashboard(self):
        make_rider('lg_rider')
        resp = self.client.post(
            reverse('rider:rider-login'),
            {'username': 'lg_rider', 'password': 'pw12345678'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:dashboard'))

    def test_pending_rider_and_plain_user_are_rejected(self):
        make_rider('lg_pending', approved=False)
        resp = self.client.post(
            reverse('rider:rider-login'),
            {'username': 'lg_pending', 'password': 'pw12345678'},
        )
        self.assertEqual(resp.status_code, 200)
        errors = [
            str(error)
            for error in resp.context['form'].non_field_errors()
        ]
        self.assertTrue(any('pending approval' in error for error in errors))
        self.assertNotIn('_auth_user_id', self.client.session)

        make_user('lg_plain')
        resp = self.client.post(
            reverse('rider:rider-login'),
            {'username': 'lg_plain', 'password': 'pw12345678'},
        )
        self.assertEqual(resp.status_code, 200)
        errors = [
            str(error)
            for error in resp.context['form'].non_field_errors()
        ]
        self.assertTrue(
            any('rider profile' in error for error in errors)
        )

    def test_logout_clears_session(self):
        rider = make_rider('lg_out')
        self.client.force_login(rider.user)
        resp = self.client.get(reverse('rider:logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('user_login'))
        self.assertNotIn('_auth_user_id', self.client.session)


class RiderPasswordResetTests(TestCase):
    def test_reset_request_sends_single_mail_to_rider(self):
        rider = make_rider('pr_rider')
        rider.user.email = 'pr_rider@example.com'
        rider.user.save()

        page = self.client.get(reverse('rider:password_reset'))
        self.assertEqual(page.status_code, 200)

        resp = self.client.post(
            reverse('rider:password_reset'),
            {'email': 'pr_rider@example.com'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['pr_rider@example.com'])
        self.assertEqual(message.subject, 'Password Reset Request')
        self.assertIn('pr_rider', message.body)
        self.assertIn('password-reset-confirm', message.body)

        rejected = self.client.post(
            reverse('rider:password_reset'), {'email': 'nobody@example.com'}
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertIn('email', rejected.context['form'].errors)
        self.assertEqual(len(mail.outbox), 1)


class RiderDocumentServingTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.kyc_path = 'riders/aadhar/ut_probe.jpg'
        self.profile_path = 'riders/profiles/ut_probe.jpg'
        self.license_path = 'riders/license/ut_probe.jpg'
        self.public_path = 'menu_images/ut_probe.jpg'
        for relative in (
            self.kyc_path,
            self.profile_path,
            self.license_path,
            self.public_path,
        ):
            absolute = os.path.join(self.media_root, relative)
            os.makedirs(os.path.dirname(absolute), exist_ok=True)
            with open(absolute, 'wb') as handle:
                handle.write(b'probe-bytes')
        self.owner = make_rider(
            'media_owner',
            profile_photo=self.profile_path,
            aadhar_front=self.kyc_path,
            license_copy=self.license_path,
        )

    def fetch(self, path, user=None):
        with self.settings(DEBUG=False, MEDIA_ROOT=self.media_root):
            if user is not None:
                self.client.force_login(user)
            return self.client.get(path)

    def test_anonymous_users_only_reach_public_media(self):
        self.assertEqual(
            self.fetch(f'/media/{self.kyc_path}').status_code, 404
        )
        self.assertEqual(
            self.fetch(f'/media/{self.profile_path}').status_code, 404
        )
        public = self.fetch(f'/media/{self.public_path}')
        self.assertEqual(public.status_code, 200)
        close_response(public)

    def test_non_owner_and_traversal_are_blocked(self):
        stranger = make_user('media_stranger')
        self.assertEqual(
            self.fetch(f'/media/{self.kyc_path}', user=stranger).status_code,
            404,
        )
        self.assertEqual(
            self.fetch('/media/../BITEQUE/urls.py').status_code, 404
        )

    def test_owner_receives_own_documents(self):
        for relative in (
            self.kyc_path,
            self.license_path,
            self.profile_path,
        ):
            response = self.fetch(
                f'/media/{relative}', user=self.owner.user
            )
            self.assertEqual(response.status_code, 200)
            close_response(response)

    def test_staff_receives_kyc_documents(self):
        staff = make_user('media_staff', is_staff=True)
        response = self.fetch(f'/media/{self.kyc_path}', user=staff)
        self.assertEqual(response.status_code, 200)
        close_response(response)

    def test_profile_directory_open_to_any_signed_in_user(self):
        other = make_rider('media_other')
        response = self.fetch(
            f'/media/{self.profile_path}', user=other.user
        )
        self.assertEqual(response.status_code, 200)
        close_response(response)


class AcceptOrderErrorMappingTests(TestCase):
    def setUp(self):
        self.rider = make_rider('uc_rider')
        self.order = make_order_index(19)
        self.assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider, status='pending'
        )
        self.client.force_login(self.rider.user)

    def test_unique_violation_maps_to_conflict(self):
        with mock.patch.object(
            OrderAssignment,
            'save',
            side_effect=IntegrityError('UNIQUE constraint failed'),
        ):
            resp = self.client.post(
                reverse('rider:accept_order', args=[self.order.pk])
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json(), {
            'status': 'error',
            'message': 'Order was just accepted by another rider.',
        })
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'pending')

    def test_unexpected_error_maps_to_500_payload(self):
        with mock.patch.object(
            OrderAssignment, 'save', side_effect=RuntimeError('boom')
        ):
            with self.assertLogs('rider_app.views', level='ERROR'):
                resp = self.client.post(
                    reverse('rider:accept_order', args=[self.order.pk])
                )
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json(), {
            'status': 'error',
            'message': 'Unable to accept order.',
        })


class MarkDeliveredPageTests(TestCase):
    def setUp(self):
        self.rider = make_rider('nd_rider')
        self.order = make_order_index(20, status='out_for_delivery')
        self.assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider, status='accepted'
        )
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivery_pin)

    def test_get_renders_pin_form_page(self):
        anonymous = self.client.get(
            reverse('rider:mark_delivered', args=[self.order.pk])
        )
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(self.rider.user)
        resp = self.client.get(
            reverse('rider:mark_delivered', args=[self.order.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['order'], self.order)
        self.assertEqual(resp.context['assignment'], self.assignment)
        self.assertIn('form', resp.context)

    def test_non_ajax_post_success_redirects_to_dashboard(self):
        self.client.force_login(self.rider.user)
        resp = self.client.post(
            reverse('rider:mark_delivered', args=[self.order.pk]),
            {'otp': self.order.delivery_pin},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('rider:dashboard'))
        self.assertIn('marked as delivered', message_text(resp))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'delivered')
