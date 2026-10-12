from pathlib import Path

from django.apps import apps
from django.template import TemplateSyntaxError, engines
from django.test import SimpleTestCase

PROJECT_APPS = ('user_app', 'rider_app', 'merchant_app', 'BITEQUE')


def project_templates():
    names = []
    for app_config in apps.get_app_configs():
        if app_config.name not in PROJECT_APPS:
            continue
        templates_dir = Path(app_config.path) / 'templates'
        if not templates_dir.is_dir():
            continue
        for path in sorted(templates_dir.rglob('*.html')):
            names.append(path.relative_to(templates_dir).as_posix())
    return names


class TemplateSweepTests(SimpleTestCase):
    def test_repository_template_inventory(self):
        names = project_templates()
        self.assertGreaterEqual(len(names), 80)
        for required in (
            'home.html', 'base.html', 'merchantDashboard.html',
            'rider_app/dashboard.html', 'order_detail.html',
            'partials/active_orders.html', 'emails/email_verification.html',
        ):
            with self.subTest(template=required):
                self.assertIn(required, names)

    def test_every_project_template_parses(self):
        engine = engines['django']
        failures = []
        for name in project_templates():
            try:
                engine.get_template(name)
            except TemplateSyntaxError as exc:
                failures.append(f'{name}: {exc}')
        self.assertEqual(failures, [])

    def test_extends_targets_resolve(self):
        engine = engines['django']
        failures = []
        known = set(project_templates())
        for name in project_templates():
            wrapper = engine.get_template(name)
            nodelist = wrapper.template.nodelist
            for node in nodelist:
                parent = getattr(node, 'parent_name', None)
                if parent is None:
                    continue
                parent_name = getattr(parent, 'value', parent)
                if not isinstance(parent_name, str):
                    continue
                if parent_name in ('base.html', 'admin/base_site.html'):
                    continue
                if parent_name not in known:
                    failures.append(f'{name} extends {parent_name}')
        self.assertEqual(failures, [])
