import os
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from merchant_app.models import (
    MerchantPayment,
    Ticket,
    TicketMessage,
)
from user_app.models import UserSupportMessage, UserProfile


class ProtectedMediaTests(TestCase):
    """The media catch-all serves public prefixes to anyone, private
    documents only to their owner (or staff), and short-circuits to
    open serving while DEBUG is on."""

    FILES = {
        'payment_screenshots/proof.jpg': b'payment-proof-bytes',
        'support_images/ticket.jpg': b'ticket-image-bytes',
        'user_support_images/ask.jpg': b'support-image-bytes',
        'avatars/me.jpg': b'avatar-bytes',
        'restaurantImages/open.jpg': b'restaurant-photo-bytes',
        'riders/profiles/private.jpg': b'rider-profile-bytes',
        'riders/aadhar/doc.jpg': b'rider-aadhar-bytes',
    }

    @staticmethod
    def body(response):
        return b''.join(response.streaming_content)

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        for rel_path in self.FILES:
            full = os.path.join(self.media_root, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as handle:
                handle.write(self.FILES[rel_path])

        self.owner = User.objects.create_user(
            username='media_owner', password='pw12345678'
        )
        self.stranger = User.objects.create_user(
            username='media_stranger', password='pw12345678'
        )
        self.staff = User.objects.create_user(
            username='media_staff', password='pw12345678',
            is_staff=True,
        )

        payment_restaurant = self.make_restaurant()
        self.payment = MerchantPayment.objects.create(
            merchant=self.owner,
            restaurant=payment_restaurant,
            amount_paid=10,
            payment_screenshot='payment_screenshots/proof.jpg',
        )
        ticket = Ticket.objects.create(
            merchant=self.owner, category='technical',
            subject='Screenshot ticket',
        )
        self.ticket_message = TicketMessage.objects.create(
            ticket=ticket, sender=self.owner, message='See attached',
            image='support_images/ticket.jpg',
        )
        from user_app.models import UserSupportTicket
        support_ticket = UserSupportTicket.objects.create(
            user=self.owner, category='technical',
            subject='Help with order',
        )
        self.support_message = UserSupportMessage.objects.create(
            ticket=support_ticket, sender=self.owner, message='Hello',
            image='user_support_images/ask.jpg',
        )
        UserProfile.objects.filter(user=self.owner).update(
            avatar='avatars/me.jpg'
        )
        from rider_app.models import Rider
        self.rider_user = User.objects.create_user(
            username='media_rider', password='pw12345678'
        )
        Rider.objects.create(
            user=self.rider_user,
            phone='9876543210',
            gender='Male',
            aadhar_number='908070605040',
            driving_license='DL-MEDIA-1',
            address='1 Road',
            area='Town',
            pincode='123456',
            profile_photo='riders/profiles/private.jpg',
            aadhar_front='riders/aadhar/doc.jpg',
            license_copy='riders/license/lic.jpg',
        )

    def make_restaurant(self):
        from merchant_app.models import Restaurant
        return Restaurant.objects.create(
            owner=self.owner,
            name='Media Kitchen',
            email='media@example.com',
            contact_number='9876543210',
            address='1 Road',
            city='Town',
            image='restaurantImages/open.jpg',
        )

    def fetch(self, path, user=None):
        if user is not None:
            self.client.force_login(user)
        else:
            self.client.logout()
        with self.settings(DEBUG=False, MEDIA_ROOT=self.media_root):
            return self.client.get(f'/media/{path}')

    def test_owner_receives_payment_screenshot(self):
        resp = self.fetch('payment_screenshots/proof.jpg', self.owner)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'payment-proof-bytes')

    def test_stranger_cannot_fetch_payment_screenshot(self):
        resp = self.fetch('payment_screenshots/proof.jpg', self.stranger)
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_cannot_fetch_payment_screenshot(self):
        resp = self.fetch('payment_screenshots/proof.jpg')
        self.assertEqual(resp.status_code, 404)

    def test_owner_receives_support_ticket_image(self):
        resp = self.fetch('support_images/ticket.jpg', self.owner)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'ticket-image-bytes')

    def test_stranger_cannot_fetch_support_ticket_image(self):
        resp = self.fetch('support_images/ticket.jpg', self.stranger)
        self.assertEqual(resp.status_code, 404)

    def test_owner_receives_user_support_image(self):
        resp = self.fetch('user_support_images/ask.jpg', self.owner)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'support-image-bytes')

    def test_stranger_cannot_fetch_user_support_image(self):
        resp = self.fetch('user_support_images/ask.jpg', self.stranger)
        self.assertEqual(resp.status_code, 404)

    def test_staff_receives_private_documents(self):
        resp = self.fetch('payment_screenshots/proof.jpg', self.staff)
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_avatar_folder_is_open_to_members(self):
        resp = self.fetch('avatars/me.jpg', self.stranger)
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_avatar_fetch_is_denied(self):
        resp = self.fetch('avatars/me.jpg')
        self.assertEqual(resp.status_code, 404)

    def test_public_restaurant_images_serve_anonymously(self):
        resp = self.fetch('restaurantImages/open.jpg')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'restaurant-photo-bytes')

    def test_traversal_segments_are_rejected(self):
        resp = self.fetch('../BITEQUE/settings.py', self.staff)
        self.assertEqual(resp.status_code, 404)

    def test_rider_profile_folder_is_open_to_authenticated_members(self):
        resp = self.fetch('riders/profiles/private.jpg', self.stranger)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'rider-profile-bytes')

    def test_rider_documents_served_only_to_owning_rider(self):
        resp = self.fetch('riders/aadhar/doc.jpg', self.rider_user)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'rider-aadhar-bytes')

        resp = self.fetch('riders/aadhar/doc.jpg', self.stranger)
        self.assertEqual(resp.status_code, 404)

    @override_settings(DEBUG=True)
    def test_debug_mode_serves_private_files_without_checks(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            self.client.logout()
            resp = self.client.get(
                '/media/payment_screenshots/proof.jpg'
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.body(resp), b'payment-proof-bytes')
