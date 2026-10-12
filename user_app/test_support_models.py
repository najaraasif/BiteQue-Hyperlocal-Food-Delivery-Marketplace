from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import (
    MerchantNotification,
    UserSupportMessage,
    UserSupportTicket,
    generate_ticket_id,
)


class UserSupportTicketModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ticket_holder', password='pw12345678'
        )

    def make_ticket(self, **kwargs):
        defaults = dict(
            user=self.user, category='technical', subject='Broken item'
        )
        defaults.update(kwargs)
        return UserSupportTicket.objects.create(**defaults)

    def test_default_ticket_id_is_seven_ascii_digits(self):
        ticket = self.make_ticket()
        self.assertEqual(len(ticket.ticket_id), 7)
        self.assertTrue(ticket.ticket_id.isdigit())

    def test_generated_ticket_ids_stay_unique_across_many_tickets(self):
        ids = [self.make_ticket().ticket_id for _ in range(10)]
        self.assertEqual(len(set(ids)), 10)

    def test_generator_retries_once_when_candidate_already_exists(self):
        self.make_ticket(ticket_id='1234567')
        with mock.patch(
            'user_app.models.random.choices',
            side_effect=[list('1234567'), list('7654321')],
        ) as choices:
            generated = generate_ticket_id()
        self.assertEqual(generated, '7654321')
        self.assertEqual(choices.call_count, 2)

    def test_ticket_id_field_is_not_editable(self):
        field = UserSupportTicket._meta.get_field('ticket_id')
        self.assertFalse(field.editable)

    def test_status_defaults_to_open(self):
        ticket = self.make_ticket()
        self.assertEqual(ticket.status, 'open')
        self.assertEqual(ticket.get_status_display(), 'Open')

    def test_every_category_choice_round_trips_to_its_display(self):
        for value, display in UserSupportTicket.CATEGORY_CHOICES:
            with self.subTest(category=value):
                ticket = self.make_ticket(
                    category=value, subject=f'subject {value}'
                )
                self.assertEqual(ticket.get_category_display(), display)

    def test_str_is_id_subject_and_status(self):
        ticket = self.make_ticket(subject='Refund missing')
        self.assertEqual(
            str(ticket),
            f'{ticket.ticket_id} - Refund missing (Open)',
        )

    def test_created_and_updated_timestamps_populate_automatically(self):
        ticket = self.make_ticket()
        self.assertIsNotNone(ticket.created_at)
        self.assertIsNotNone(ticket.updated_at)
        self.assertLessEqual(ticket.created_at, ticket.updated_at)

    def test_updated_at_bumps_when_ticket_is_saved_later(self):
        ticket = self.make_ticket()
        UserSupportTicket.objects.filter(pk=ticket.pk).update(
            updated_at=datetime(2020, 1, 1, tzinfo=dt_timezone.utc)
        )
        ticket.refresh_from_db()
        ticket.save()
        ticket.refresh_from_db()
        self.assertGreater(
            ticket.updated_at, datetime(2021, 1, 1, tzinfo=dt_timezone.utc)
        )

    def test_deleting_user_cascades_their_tickets(self):
        self.make_ticket()
        self.make_ticket(subject='Second issue')
        self.assertEqual(self.user.user_tickets.count(), 2)
        self.user.delete()
        self.assertEqual(UserSupportTicket.objects.count(), 0)

    def test_deleting_ticket_cascades_its_messages(self):
        ticket = self.make_ticket()
        UserSupportMessage.objects.create(
            ticket=ticket, sender=self.user, message='First reply'
        )
        ticket.delete()
        self.assertEqual(UserSupportMessage.objects.count(), 0)


class UserSupportMessageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='msg_sender', password='pw12345678'
        )
        self.ticket = UserSupportTicket.objects.create(
            user=self.user, category='billing', subject='Overcharged'
        )

    def make_message(self, message='Hello support'):
        return UserSupportMessage.objects.create(
            ticket=self.ticket, sender=self.user, message=message
        )

    def test_messages_are_ordered_by_created_at_ascending(self):
        first = self.make_message(message='older wins')
        second = self.make_message(message='newer loses')
        UserSupportMessage.objects.filter(pk=second.pk).update(
            created_at=datetime(2019, 5, 5, tzinfo=dt_timezone.utc)
        )
        ordered = list(
            UserSupportMessage.objects.filter(
                ticket=self.ticket
            ).values_list('message', flat=True)
        )
        self.assertEqual(ordered, ['newer loses', 'older wins'])
        self.assertNotEqual(first.pk, second.pk)

    def test_str_names_sender_and_timestamp(self):
        message = self.make_message()
        expected = (
            f'Message by {self.user.username} on '
            f"{message.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
        self.assertEqual(str(message), expected)

    def test_image_field_is_optional(self):
        message = self.make_message()
        self.assertIsNone(message.image.name)

    def test_ticket_exposes_ordered_messages_related_name(self):
        self.make_message(message='one')
        self.make_message(message='two')
        self.assertEqual(self.ticket.messages.count(), 2)

    def test_deleting_sender_cascades_their_messages(self):
        other = User.objects.create_user(
            username='other_sender', password='pw12345678'
        )
        message = UserSupportMessage.objects.create(
            ticket=self.ticket, sender=other, message='from other'
        )
        other.delete()
        self.assertFalse(
            UserSupportMessage.objects.filter(pk=message.pk).exists()
        )

    def test_created_at_is_automatic(self):
        message = self.make_message()
        self.assertIsNotNone(message.created_at)
        self.assertLess(message.created_at, timezone.now() + timedelta(seconds=1))


class MerchantNotificationModelTests(TestCase):
    def setUp(self):
        self.merchant = User.objects.create_user(
            username='notif_merchant', password='pw12345678'
        )

    def make_notification(self, **kwargs):
        defaults = dict(
            merchant=self.merchant, message='New order received'
        )
        defaults.update(kwargs)
        return MerchantNotification.objects.create(**defaults)

    def test_notifications_start_unread(self):
        notification = self.make_notification()
        self.assertFalse(notification.is_read)

    def test_marking_read_persists(self):
        notification = self.make_notification()
        notification.is_read = True
        notification.save()
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_message_is_stored_verbatim(self):
        notification = self.make_notification(message='Order #42 accepted')
        notification.refresh_from_db()
        self.assertEqual(notification.message, 'Order #42 accepted')

    def test_created_at_is_automatic(self):
        notification = self.make_notification()
        self.assertIsNotNone(notification.created_at)

    def test_deleting_merchant_cascades_notifications(self):
        self.make_notification()
        self.make_notification(message='Order ready')
        self.assertEqual(
            MerchantNotification.objects.filter(
                merchant=self.merchant
            ).count(),
            2,
        )
        self.merchant.delete()
        self.assertEqual(MerchantNotification.objects.count(), 0)
