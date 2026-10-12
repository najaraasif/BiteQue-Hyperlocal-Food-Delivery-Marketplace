from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory

from .models import CustomerFeedback, Order, OrderMenuItem, UserSupportMessage, UserSupportTicket

TINY_GIF = (
    b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00'
    b'\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


def make_restaurant(name='Support Kitchen'):
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


def make_order(user, restaurant, status='delivered'):
    return Order.objects.create(
        user=user, restaurant=restaurant, status=status,
        customer_name='Pat', customer_contact='', landmark='',
        delivery_address='1 Road', special_instructions='',
    )


def messages_of(response):
    return [m.message for m in get_messages(response.wsgi_request)]


class UserSupportPortalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='supporter', password='pw12345678')
        self.other = User.objects.create_user(username='stranger', password='pw12345678')
        self.client.force_login(self.user)

    def create_ticket(self, user=None, subject='Broken app', category='technical', **kwargs):
        return UserSupportTicket.objects.create(
            user=user or self.user, subject=subject, category=category, **kwargs
        )

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('user_support_portal'))
        self.assertEqual(resp.status_code, 302)

    def test_get_without_tickets_shows_empty_state(self):
        resp = self.client.get(reverse('user_support_portal'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'partials/user_support.html')
        self.assertTrue(resp.context['no_tickets'])
        self.assertIsNone(resp.context['selected_ticket'])
        self.assertEqual(list(resp.context['messages']), [])

    def test_get_lists_only_own_tickets_newest_updated_first(self):
        older = self.create_ticket(subject='Older')
        newer = self.create_ticket(subject='Newer')
        UserSupportTicket.objects.filter(pk=older.pk).update(updated_at='2026-01-01T00:00:00Z')
        UserSupportTicket.objects.filter(pk=newer.pk).update(updated_at='2026-02-01T00:00:00Z')
        self.create_ticket(user=self.other, subject='Foreign')
        resp = self.client.get(reverse('user_support_portal'))
        subjects = [t.subject for t in resp.context['tickets']]
        self.assertEqual(subjects, ['Newer', 'Older'])
        self.assertFalse(resp.context['no_tickets'])

    def test_get_selects_most_recent_ticket_by_default(self):
        first = self.create_ticket(subject='First')
        self.create_ticket(subject='Second')
        UserSupportTicket.objects.filter(pk=first.pk).update(updated_at='2026-01-01T00:00:00Z')
        resp = self.client.get(reverse('user_support_portal'))
        self.assertEqual(resp.context['selected_ticket'].subject, 'Second')

    def test_ticket_id_param_selects_that_ticket(self):
        self.create_ticket(subject='First')
        target = self.create_ticket(subject='Target')
        resp = self.client.get(
            reverse('user_support_portal'), {'ticket_id': target.ticket_id}
        )
        self.assertEqual(resp.context['selected_ticket'].ticket_id, target.ticket_id)

    def test_foreign_ticket_id_falls_back_to_own_first_ticket(self):
        own = self.create_ticket(subject='Mine')
        foreign = self.create_ticket(user=self.other, subject='Theirs')
        resp = self.client.get(
            reverse('user_support_portal'), {'ticket_id': foreign.ticket_id}
        )
        self.assertEqual(resp.context['selected_ticket'].ticket_id, own.ticket_id)

    def test_create_ticket_persists_ticket_and_initial_message(self):
        resp = self.client.post(reverse('user_support_portal'), {
            'create_ticket': '1',
            'subject': 'Payment failed',
            'category': 'billing',
            'message': 'My card was charged twice',
        })
        self.assertEqual(resp.status_code, 302)
        ticket = UserSupportTicket.objects.get(subject='Payment failed')
        self.assertEqual(ticket.user, self.user)
        self.assertEqual(ticket.status, 'open')
        self.assertTrue(any(f'Ticket created successfully with ID #{ticket.ticket_id}' in m for m in messages_of(resp)))
        self.assertIn(f'/user/support/?ticket_id={ticket.ticket_id}', resp.url)
        message = UserSupportMessage.objects.get(ticket=ticket)
        self.assertEqual(message.sender, self.user)
        self.assertEqual(message.message, 'My card was charged twice')

    def test_create_ticket_with_image_upload(self):
        import shutil
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        media_root = tempfile.mkdtemp(prefix='biteque_support_')
        self.addCleanup(shutil.rmtree, media_root, True)
        with override_settings(MEDIA_ROOT=media_root):
            resp = self.client.post(reverse('user_support_portal'), {
                'create_ticket': '1',
                'subject': 'With image',
                'category': 'technical',
                'message': 'See screenshot',
                'image': SimpleUploadedFile('shot.gif', TINY_GIF, content_type='image/gif'),
            })
        self.assertEqual(resp.status_code, 302)
        message = UserSupportMessage.objects.get(message='See screenshot')
        self.assertTrue(message.image.name.startswith('user_support_images/'))

    def test_invalid_create_ticket_re_renders_with_error_message(self):
        resp = self.client.post(reverse('user_support_portal'), {
            'create_ticket': '1',
            'subject': '',
            'category': 'not-a-category',
            'message': 'hello',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('Please fix the form errors below.' in m for m in messages_of(resp)))
        self.assertTrue(resp.context['ticket_form'].errors)
        self.assertFalse(UserSupportTicket.objects.exists())

    def test_reply_appends_message_and_updates_ticket(self):
        ticket = self.create_ticket(subject='Thread')
        UserSupportTicket.objects.filter(pk=ticket.pk).update(
            updated_at='2020-01-01T00:00:00Z'
        )
        resp = self.client.post(reverse('user_support_portal'), {
            'reply_ticket': '1',
            'message': 'Any update on this?',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/user/support/?ticket_id={ticket.ticket_id}', resp.url)
        self.assertTrue(any('Reply sent successfully.' in m for m in messages_of(resp)))
        self.assertEqual(UserSupportMessage.objects.filter(ticket=ticket).count(), 1)
        ticket.refresh_from_db()
        self.assertGreater(ticket.updated_at, ticket.created_at)

    def test_reply_to_closed_ticket_is_rejected(self):
        ticket = self.create_ticket(subject='Closed', status='closed')
        resp = self.client.post(reverse('user_support_portal'), {
            'reply_ticket': '1',
            'message': 'Reopening?',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('This ticket is closed. You cannot reply.' in m for m in messages_of(resp)))
        self.assertEqual(UserSupportMessage.objects.filter(ticket=ticket).count(), 0)

    def test_reply_without_message_field_is_rejected(self):
        self.create_ticket(subject='Thread')
        resp = self.client.post(reverse('user_support_portal'), {
            'reply_ticket': '1',
            'message': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('Please fix the reply form errors below.' in m for m in messages_of(resp)))
        self.assertEqual(UserSupportMessage.objects.count(), 0)

    def test_messages_context_ordered_by_created_at(self):
        ticket = self.create_ticket(subject='Thread')
        first = UserSupportMessage.objects.create(
            ticket=ticket, sender=self.user, message='first'
        )
        second = UserSupportMessage.objects.create(
            ticket=ticket, sender=self.user, message='second'
        )
        UserSupportMessage.objects.filter(pk=first.pk).update(created_at='2026-01-01T00:00:00Z')
        UserSupportMessage.objects.filter(pk=second.pk).update(created_at='2026-02-01T00:00:00Z')
        resp = self.client.get(
            reverse('user_support_portal'), {'ticket_id': ticket.ticket_id}
        )
        texts = [m.message for m in resp.context['messages']]
        self.assertEqual(texts, ['first', 'second'])


class ContactFormTests(TestCase):
    def test_get_returns_bad_request_json(self):
        resp = self.client.get(reverse('contact-form'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {
            'status': 'error', 'message': 'Invalid request',
        })

    def test_valid_post_sends_mail_and_returns_success(self):
        with mock.patch('user_app.views.send_mail') as mail:
            resp = self.client.post(reverse('contact-form'), {
                'name': 'Pat', 'email': 'pat@example.com', 'message': 'Hello team',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
        mail.assert_called_once()
        args = mail.call_args[0]
        self.assertEqual(args[0], 'ZemQue Contact Form - Pat')
        self.assertIn('pat@example.com', args[1])
        self.assertIn('Hello team', args[1])
        self.assertEqual(args[3], [settings.DEFAULT_FROM_EMAIL])

    def test_missing_fields_still_attempted_and_success(self):
        with mock.patch('user_app.views.send_mail') as mail:
            resp = self.client.post(reverse('contact-form'), {})
        self.assertEqual(resp.json()['status'], 'success')
        self.assertIn('ZemQue Contact Form - None', mail.call_args[0][0])

    def test_mail_failure_returns_error_json(self):
        with mock.patch('user_app.views.send_mail', side_effect=RuntimeError('smtp down')):
            with self.assertLogs('user_app.views', level='ERROR'):
                resp = self.client.post(reverse('contact-form'), {
                    'name': 'Pat', 'email': 'pat@example.com', 'message': 'Hi',
                })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {
            'status': 'error',
            'message': 'Unable to send your message right now. Please try again later.',
        })


class SubmitReviewTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant('Review Kitchen')
        self.user = User.objects.create_user(username='reviewer', password='pw12345678')

    def test_login_required(self):
        resp = self.client.get(reverse('submit_review', args=[self.restaurant.id]))
        self.assertEqual(resp.status_code, 302)

    def test_get_renders_review_form(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('submit_review', args=[self.restaurant.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'submit_review.html')
        self.assertEqual(resp.context['restaurant'].id, self.restaurant.id)

    def test_unknown_restaurant_returns_404(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('submit_review', args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_valid_post_creates_review_and_redirects_to_menu(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('submit_review', args=[self.restaurant.id]),
            {'rating': '5', 'comment': 'Great food'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('user_view_menu', args=[self.restaurant.id]))
        review = self.restaurant.reviews.get()
        self.assertEqual(review.user, self.user)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Great food')

    def test_invalid_post_re_renders_with_errors(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('submit_review', args=[self.restaurant.id]),
            {'rating': '9', 'comment': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)
        self.assertFalse(self.restaurant.reviews.exists())

    def test_multiple_reviews_from_same_user_allowed(self):
        self.client.force_login(self.user)
        for rating in ('4', '3'):
            self.client.post(
                reverse('submit_review', args=[self.restaurant.id]),
                {'rating': rating, 'comment': 'again'},
            )
        self.assertEqual(self.restaurant.reviews.count(), 2)


class WriteOrderFeedbackTests(TestCase):
    def setUp(self):
        self.restaurant = make_restaurant('Feedback View Kitchen')
        self.item = make_menu_item(self.restaurant)
        self.user = User.objects.create_user(username='fbwriter', password='pw12345678')
        self.other = User.objects.create_user(username='fbstranger', password='pw12345678')
        self.order = make_order(self.user, self.restaurant)
        OrderMenuItem.objects.create(
            order=self.order, menu_item=self.item, quantity=1, price=self.item.price
        )
        self.client.force_login(self.user)

    def url(self):
        return reverse('write_feedback', args=[self.order.id])

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 302)

    def test_foreign_order_returns_404(self):
        self.client.force_login(self.other)
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 404)

    def test_get_renders_form_with_per_item_rating_fields(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'write_feedback.html')
        self.assertIn(f'item_rating_{self.item.id}', resp.context['form'].fields)
        self.assertEqual(len(resp.context['order_items']), 1)

    def test_post_creates_feedback_with_computed_overall_rating(self):
        resp = self.client.post(self.url(), {
            'item_quality': '5',
            'delivery_experience': '4',
            'restaurant_rating': '3',
            'rider_rating': '2',
            'additional_comments': 'Solid',
            f'item_rating_{self.item.id}': '5',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('order_detail', args=[self.order.id]))
        fb = CustomerFeedback.objects.get(order=self.order)
        self.assertEqual(fb.customer, self.user)
        self.assertEqual(fb.restaurant, self.restaurant)
        self.assertEqual(fb.rating, 3)
        self.assertEqual(fb.item_ratings, {str(self.item.id): 5})
        self.assertEqual(fb.additional_comments, 'Solid')

    def test_partial_subratings_average_only_what_was_given(self):
        self.client.post(self.url(), {
            'item_quality': '5',
            'delivery_experience': '',
            'restaurant_rating': '',
            'rider_rating': '',
        })
        fb = CustomerFeedback.objects.get(order=self.order)
        self.assertEqual(fb.rating, 5.0)

    def test_no_subratings_leaves_overall_rating_unset(self):
        self.client.post(self.url(), {
            'item_quality': '',
            'delivery_experience': '',
            'restaurant_rating': '',
            'rider_rating': '',
        })
        fb = CustomerFeedback.objects.get(order=self.order)
        self.assertIsNone(fb.rating)

    def test_feedback_is_one_per_order_and_redirects_when_duplicate(self):
        CustomerFeedback.objects.create(
            order=self.order, restaurant=self.restaurant, customer=self.user, rating=4
        )
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('order_detail', args=[self.order.id]))
        resp = self.client.post(self.url(), {'item_quality': '5'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CustomerFeedback.objects.count(), 1)

    def test_feedback_form_rejects_out_of_range_rating(self):
        resp = self.client.post(self.url(), {'item_quality': '7'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)
        self.assertFalse(CustomerFeedback.objects.exists())
