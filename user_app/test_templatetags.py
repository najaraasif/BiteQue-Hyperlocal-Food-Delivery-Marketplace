from django import forms
from django.template import Context, Template
from django.test import TestCase

from .templatetags.form_tags import add_class, register


class SampleForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField(widget=forms.TextInput(attrs={'class': 'base'}))


class AddClassFilterTests(TestCase):
    def test_filter_is_registered_under_its_name(self):
        self.assertIn('add_class', register.filters)

    def test_add_class_puts_the_class_on_a_bare_widget(self):
        form = SampleForm()
        html = add_class(form['name'], 'form-control')
        self.assertIn('class="form-control"', html)
        self.assertIn('name="name"', html)

    def test_add_class_replaces_an_existing_widget_class(self):
        form = SampleForm()
        html = add_class(form['email'], 'form-input')
        self.assertIn('class="form-input"', html)
        self.assertNotIn('base', html)

    def test_add_class_keeps_other_widget_attributes(self):
        form = SampleForm()
        html = add_class(form['name'], 'extra')
        self.assertIn('name="name"', html)
        self.assertIn('type="text"', html)

    def test_filter_renders_inside_a_template(self):
        form = SampleForm()
        rendered = Template(
            '{% load form_tags %}{{ field|add_class:"css-from-template" }}'
        ).render(Context({'field': form['name']}))
        self.assertIn('class="css-from-template"', rendered)
        self.assertIn('name="name"', rendered)

    def test_merchant_library_exposes_the_same_filter(self):
        from merchant_app.templatetags.form_tags import (
            add_class as merchant_add_class,
        )
        form = SampleForm()
        html = merchant_add_class(form['name'], 'merchant-css')
        self.assertIn('class="merchant-css"', html)
