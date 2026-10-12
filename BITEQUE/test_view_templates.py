import re
from pathlib import Path

from django.apps import apps
from django.template import TemplateDoesNotExist, engines
from django.test import SimpleTestCase

PROJECT_APPS = ('user_app', 'rider_app', 'merchant_app')

RENDER_REQUEST = re.compile(
    r"""render\(\s*request\s*,\s*['"]([^'"]+)['"]"""
)
RENDER_TO_STRING = re.compile(
    r"""render_to_string\(\s*['"]([^'"]+)['"]"""
)


def view_template_references():
    names = set()
    for app_name in PROJECT_APPS:
        app_module = apps.get_app_config(app_name).module
        views_path = Path(app_module.__file__).with_name('views.py')
        if not views_path.is_file():
            continue
        source = views_path.read_text(encoding='utf-8')
        names.update(RENDER_REQUEST.findall(source))
        names.update(RENDER_TO_STRING.findall(source))
    return sorted(names)


class ViewTemplateReferenceTests(SimpleTestCase):
    def test_reference_inventory_is_substantial(self):
        names = view_template_references()
        self.assertGreaterEqual(len(names), 40)

    def test_every_template_named_in_a_view_exists(self):
        engine = engines['django']
        missing = []
        for name in view_template_references():
            try:
                engine.get_template(name)
            except TemplateDoesNotExist:
                missing.append(name)
        self.assertEqual(missing, [])

    def test_each_app_contributes_view_templates(self):
        per_app = {}
        for app_name in PROJECT_APPS:
            app_module = apps.get_app_config(app_name).module
            views_path = Path(app_module.__file__).with_name('views.py')
            source = views_path.read_text(encoding='utf-8')
            per_app[app_name] = set(RENDER_REQUEST.findall(source))
        for app_name in PROJECT_APPS:
            with self.subTest(app=app_name):
                self.assertGreaterEqual(len(per_app[app_name]), 5)
