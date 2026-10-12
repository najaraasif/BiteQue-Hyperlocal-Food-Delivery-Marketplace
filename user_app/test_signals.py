import zlib

from django.contrib.auth.models import User
from django.test import TestCase

from rider_app.models import OrderAssignment, Rider
from user_app.models import Order

from .signals import create_assignments


def make_restaurant(name='Signal Kitchen'):
    from merchant_app.models import Restaurant
    owner = User.objects.create_user(
        username=f'sig_{name}'.replace(' ', '').lower(),
        password='pw12345678',
    )
    return Restaurant.objects.create(
        owner=owner,
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Road',
        city='Town',
        image=f'restaurantImages/{name.replace(" ", "").lower()}.jpg',
    )


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


def make_order(restaurant, user, status='ready'):
    return Order.objects.create(
        user=user,
        restaurant=restaurant,
        customer_name='Signal Customer',
        customer_contact='',
        landmark='',
        delivery_address='1 Road',
        special_instructions='',
        status=status,
    )


class CreateAssignmentsSignalTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant()
        self.customer = User.objects.create_user(
            username='signal_customer', password='pw12345678'
        )

    def test_ready_order_creates_pending_assignments(self):
        rider = make_rider('signal_ready')
        order = make_order(self.restaurant, self.customer, status='ready')
        assignment = OrderAssignment.objects.get(order=order, rider=rider)
        self.assertEqual(assignment.status, 'pending')

    def test_non_ready_statuses_create_no_assignments(self):
        rider = make_rider('signal_other')
        for status in ('pending', 'confirmed', 'out_for_delivery',
                       'delivered', 'cancelled'):
            order = make_order(self.restaurant, self.customer, status=status)
            self.assertFalse(
                OrderAssignment.objects.filter(
                    order=order, rider=rider
                ).exists()
            )

    def test_only_approved_and_available_riders_receive_assignments(self):
        eligible = make_rider('signal_eligible')
        unapproved = make_rider('signal_unapproved', approved=False)
        unavailable = make_rider('signal_unavailable', available=False)

        order = make_order(self.restaurant, self.customer, status='ready')

        riders_with_assignment = set(
            OrderAssignment.objects.filter(
                order=order
            ).values_list('rider_id', flat=True)
        )
        self.assertEqual(riders_with_assignment, {eligible.pk})
        self.assertFalse(
            OrderAssignment.objects.filter(rider=unapproved).exists()
        )
        self.assertFalse(
            OrderAssignment.objects.filter(rider=unavailable).exists()
        )

    def test_saving_the_ready_order_again_does_not_duplicate(self):
        rider = make_rider('signal_twice')
        order = make_order(self.restaurant, self.customer, status='ready')
        order.save()
        order.save()
        self.assertEqual(
            OrderAssignment.objects.filter(order=order, rider=rider).count(),
            1,
        )

    def test_transition_into_ready_creates_assignments_late(self):
        rider = make_rider('signal_late')
        order = make_order(self.restaurant, self.customer, status='confirmed')
        self.assertEqual(OrderAssignment.objects.count(), 0)

        order.status = 'ready'
        order.save()

        self.assertEqual(
            OrderAssignment.objects.filter(
                order=order, rider=rider, status='pending'
            ).count(),
            1,
        )

    def test_order_without_eligible_riders_creates_nothing(self):
        order = make_order(self.restaurant, self.customer, status='ready')
        self.assertEqual(OrderAssignment.objects.filter(order=order).count(), 0)

    def test_receiver_is_registered_for_the_order_model(self):
        from django.db.models.signals import post_save
        self.assertTrue(post_save.has_listeners(Order))

    def test_direct_invocation_matches_post_save_behavior(self):
        rider = make_rider('signal_direct')
        order = make_order(self.restaurant, self.customer, status='pending')
        create_assignments(Order, order, created=True, raw=False)
        self.assertEqual(OrderAssignment.objects.count(), 0)

        order.status = 'ready'
        create_assignments(Order, order, created=False, raw=False)
        self.assertEqual(
            OrderAssignment.objects.filter(order=order, rider=rider).count(),
            1,
        )
        create_assignments(Order, order, created=False, raw=False)
        self.assertEqual(
            OrderAssignment.objects.filter(order=order, rider=rider).count(),
            1,
        )
