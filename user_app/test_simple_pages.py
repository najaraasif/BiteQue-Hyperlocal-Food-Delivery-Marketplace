from django.test import TestCase
from django.urls import reverse


class SimplePageTests(TestCase):
    def test_add_restaurant_page_renders(self):
        resp = self.client.get(reverse('add-restaurant'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'addRestaurant.html')

    def test_ride_with_us_page_renders(self):
        resp = self.client.get(reverse('ride-with-us'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'rideWithUs.html')

    def test_careers_page_renders(self):
        resp = self.client.get(reverse('careers'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'careers.html')

    def test_responsible_disclosure_page_renders(self):
        resp = self.client.get(reverse('responsible-disclosure'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'ResponsibleDisclosure.html')

    def test_about_page_renders(self):
        resp = self.client.get(reverse('about'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'about.html')

    def test_contact_page_renders(self):
        resp = self.client.get(reverse('contact'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'contact.html')

    def test_privacy_page_renders(self):
        resp = self.client.get(reverse('privacy'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'privacy.html')

    def test_terms_page_renders(self):
        resp = self.client.get(reverse('terms-and-conditions'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'Terms&Conditions.html')
