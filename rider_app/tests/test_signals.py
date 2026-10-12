from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from merchant_app.models import Restaurant
from user_app.models import Order

from rider_app.models import OrderAssignment, Rider

from .test_assignment_flow import make_order, make_rider, make_user


class ApprovalEmailTests(TestCase):
    def test_created_approved_rider_sends_no_email(self):
        with mock.patch('rider_app.signals.send_brevo_email') as emailer:
            make_rider('mail_created', approved=True)

        emailer.assert_not_called()

    def test_approval_transition_sends_welcome_email_exactly_once(self):
        rider = make_rider('mail_rider', approved=False)
        rider.user.email = 'mail_rider@example.com'
        rider.user.save()

        with mock.patch('rider_app.signals.send_brevo_email') as emailer:
            emailer.assert_not_called()

            rider.is_approved = True
            rider.save()
            emailer.assert_called_once()

            kwargs = emailer.call_args.kwargs
            self.assertEqual(
                kwargs['subject'], 'Welcome to BiteQue, mail_rider!'
            )
            self.assertEqual(
                kwargs['recipient_email'], 'mail_rider@example.com'
            )
            self.assertEqual(kwargs['recipient_name'], 'mail_rider')
            self.assertIn(
                'Your rider account has been approved.',
                kwargs['html_content'],
            )

            rider.is_available = True
            rider.save()
            emailer.assert_called_once()


class AcceptanceStatsTests(TestCase):
    def test_total_assignments_tracks_created_assignments(self):
        rider = make_rider('stats_rider')
        first_order = make_order(make_user('stats_cust_1'))
        second_order = make_order(make_user('stats_cust_2'))

        OrderAssignment.objects.create(
            order=first_order, rider=rider, status='pending'
        )
        rider.refresh_from_db()
        self.assertEqual(rider.total_assignments, 1)

        OrderAssignment.objects.create(
            order=second_order, rider=rider, status='rejected'
        )
        rider.refresh_from_db()
        self.assertEqual(rider.total_assignments, 2)

    def test_desynced_counter_is_repaired_on_next_assignment(self):
        rider = make_rider('stats_fix')
        first_order = make_order(make_user('stats_fix_cust_1'))
        second_order = make_order(make_user('stats_fix_cust_2'))

        OrderAssignment.objects.create(
            order=first_order, rider=rider, status='pending'
        )
        Rider.objects.filter(pk=rider.pk).update(total_assignments=99)

        OrderAssignment.objects.create(
            order=second_order, rider=rider, status='pending'
        )
        rider.refresh_from_db()
        self.assertEqual(rider.total_assignments, 2)


class GeocodeSignalTests(TestCase):
    def test_order_geocode_short_circuits_under_test(self):
        with mock.patch('rider_app.signals.requests.get') as get:
            order = make_order(make_user('geo_short'))

        get.assert_not_called()
        self.assertIsNone(order.dest_lat)
        self.assertIsNone(order.dest_lon)

    def test_restaurant_geocode_short_circuits_and_skips_set_coords(self):
        owner = make_user('geo_rest_owner')
        with mock.patch('rider_app.signals.requests.get') as get:
            restaurant = Restaurant.objects.create(
                owner=owner,
                name='Geo Kitchen',
                email='geo@example.com',
                contact_number='9876543210',
                address='1 Main Road',
                city='Testville',
            )

        get.assert_not_called()
        self.assertIsNone(restaurant.lat)
        self.assertIsNone(restaurant.lon)

        with mock.patch(
            'rider_app.signals.geocode_address_google'
        ) as geocoder:
            Restaurant.objects.create(
                owner=owner,
                name='Geo Kitchen 2',
                email='geo2@example.com',
                contact_number='9876543211',
                address='1 Main Road',
                city='Testville',
                lat=Decimal('12.5000000'),
                lon=Decimal('77.5000000'),
            )

        geocoder.assert_not_called()

    def test_order_geocode_skips_unchanged_address_and_existing_coords(self):
        with mock.patch(
            'rider_app.signals.geocode_address_google'
        ) as geocoder:
            geocoder.return_value = (None, None)
            order = make_order(make_user('geo_skip'))
            called_addresses = [call.args[0] for call in geocoder.call_args_list]
            self.assertIn('1 Delivery Road', called_addresses)
            baseline = geocoder.call_count

            order.save()
            self.assertEqual(geocoder.call_count, baseline)

            Order.objects.filter(pk=order.pk).update(
                dest_lat='12.9716000', dest_lon='77.5946000'
            )
            order.refresh_from_db()
            order.save()
            self.assertEqual(geocoder.call_count, baseline)

    def test_geocoded_coordinates_are_written_to_instances(self):
        with mock.patch(
            'rider_app.signals.geocode_address_google'
        ) as geocoder:
            geocoder.return_value = (12.9716, 77.5946)
            order = make_order(make_user('geo_store'))

        order.refresh_from_db()
        self.assertEqual(float(order.dest_lat), 12.9716)
        self.assertEqual(float(order.dest_lon), 77.5946)
        self.assertEqual(float(order.restaurant.lat), 12.9716)
        self.assertEqual(float(order.restaurant.lon), 77.5946)


class AcceptanceScoreTests(TestCase):
    TIER_CASES = [
        (0, 100),
        (60, 100),
        (61, 90),
        (120, 90),
        (121, 80),
        (180, 80),
        (181, 70),
        (240, 70),
        (241, 50),
        (300, 50),
        (301, 0),
        (1200, 0),
    ]

    def setUp(self):
        self.rider = make_rider('score_rider')
        self.order = make_order(make_user('score_cust'), status='ready')

    def accept_after(self, seconds):
        fixed = timezone.now()
        with mock.patch(
            'rider_app.signals.timezone.now', return_value=fixed
        ):
            return OrderAssignment.objects.create(
                order=self.order,
                rider=self.rider,
                status='accepted',
                assigned_at=fixed - timedelta(seconds=seconds),
            )

    def test_score_tier_boundaries(self):
        for seconds, expected in self.TIER_CASES:
            with self.subTest(seconds=seconds):
                assignment = self.accept_after(seconds)
                self.assertEqual(float(assignment.acceptance_score), expected)
                self.assertEqual(
                    assignment.response_time, timedelta(seconds=seconds)
                )
                assignment.delete()

    def test_existing_scores_and_pending_rows_are_not_recomputed(self):
        assignment = self.accept_after(45)
        self.assertEqual(assignment.response_time, timedelta(seconds=45))

        OrderAssignment.objects.filter(pk=assignment.pk).update(
            acceptance_score=Decimal('12.00')
        )
        reloaded = OrderAssignment.objects.get(pk=assignment.pk)
        reloaded.save()
        reloaded.refresh_from_db()
        self.assertEqual(float(reloaded.acceptance_score), 12.0)

        pending = OrderAssignment.objects.create(
            order=self.order,
            rider=self.rider,
            status='pending',
            assigned_at=timezone.now() - timedelta(hours=3),
        )
        rejected = OrderAssignment.objects.create(
            order=self.order,
            rider=self.rider,
            status='rejected',
            assigned_at=timezone.now() - timedelta(hours=3),
        )
        self.assertIsNone(pending.response_time)
        self.assertEqual(float(pending.acceptance_score), 0.0)
        self.assertIsNone(rejected.response_time)
        self.assertEqual(float(rejected.acceptance_score), 0.0)


class OrderAssignmentChangeTests(TestCase):
    def setUp(self):
        self.rider_one = make_rider('sig_r1')
        self.rider_two = make_rider('sig_r2')
        self.order = make_order(make_user('sig_cust'), status='ready')

    def test_accepted_moves_order_forward_and_rejects_competitors(self):
        first = OrderAssignment.objects.create(
            order=self.order, rider=self.rider_one, status='pending'
        )
        rival = OrderAssignment.objects.create(
            order=self.order, rider=self.rider_two, status='pending'
        )

        first.status = 'accepted'
        first.save()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')
        self.assertIsNotNone(self.order.delivery_pin)
        self.assertEqual(len(self.order.delivery_pin), 4)
        self.assertTrue(self.order.delivery_pin.isdigit())

        first.refresh_from_db()
        rival.refresh_from_db()
        self.assertEqual(first.status, 'accepted')
        self.assertEqual(rival.status, 'rejected')

    def test_accepted_generates_pin_when_order_already_out_for_delivery(self):
        Order.objects.filter(pk=self.order.pk).update(
            status='out_for_delivery'
        )
        self.order.refresh_from_db()

        OrderAssignment.objects.create(
            order=self.order, rider=self.rider_one, status='accepted'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')
        self.assertIsNotNone(self.order.delivery_pin)
        self.assertEqual(len(self.order.delivery_pin), 4)

    def test_accepted_preserves_an_existing_pin(self):
        Order.objects.filter(pk=self.order.pk).update(
            status='out_for_delivery',
            delivery_pin='1357',
            delivery_pin_generated_at=timezone.now(),
        )
        self.order.refresh_from_db()

        OrderAssignment.objects.create(
            order=self.order, rider=self.rider_one, status='accepted'
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')
        self.assertEqual(self.order.delivery_pin, '1357')

    def test_delivered_marks_order_and_clears_pin_idempotently(self):
        assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider_one, status='accepted'
        )
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivery_pin)

        assignment.status = 'delivered'
        assignment.save()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertIsNone(self.order.delivery_pin)
        self.assertIsNone(self.order.delivery_pin_generated_at)
        self.assertEqual(self.order.delivery_pin_attempts, 0)

        assignment.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertIsNone(self.order.delivery_pin)

    def test_pending_and_rejected_statuses_leave_order_untouched(self):
        assignment = OrderAssignment.objects.create(
            order=self.order, rider=self.rider_one, status='pending'
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready')
        self.assertIsNone(self.order.delivery_pin)

        assignment.status = 'rejected'
        assignment.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready')
        self.assertIsNone(self.order.delivery_pin)
