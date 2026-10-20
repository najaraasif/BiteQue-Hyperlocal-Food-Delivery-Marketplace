import os
import sys
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import (
    URLPattern,
    URLResolver,
    NoReverseMatch,
    get_resolver,
    resolve,
    reverse,
)


def iter_url_entries(patterns, prefix='', namespace=''):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            sub = (
                getattr(pattern, 'namespace', None)
                or getattr(pattern, 'app_name', None)
                or ''
            )
            child_namespace = (
                f'{namespace}:{sub}' if namespace and sub else (namespace or sub)
            )
            yield from iter_url_entries(
                pattern.url_patterns,
                prefix + str(pattern.pattern),
                child_namespace,
            )
        elif isinstance(pattern, URLPattern):
            full_name = (
                f'{namespace}:{pattern.name}'
                if namespace and pattern.name
                else pattern.name
            )
            yield full_name, prefix + str(pattern.pattern), pattern


class ProjectAppsTests(SimpleTestCase):
    def test_project_apps_are_installed(self):
        for app in ('user_app', 'rider_app', 'merchant_app'):
            with self.subTest(app=app):
                self.assertIn(app, settings.INSTALLED_APPS)

    def test_supporting_apps_are_installed(self):
        for app in (
            'django.contrib.admin', 'django.contrib.humanize',
            'widget_tweaks',
        ):
            with self.subTest(app=app):
                self.assertIn(app, settings.INSTALLED_APPS)

    def test_root_urlconf(self):
        self.assertEqual(settings.ROOT_URLCONF, 'BITEQUE.urls')

    def test_wsgi_application_path(self):
        self.assertEqual(settings.WSGI_APPLICATION, 'BITEQUE.wsgi.application')

    def test_default_auto_field(self):
        self.assertEqual(
            settings.DEFAULT_AUTO_FIELD, 'django.db.models.BigAutoField'
        )


class TemplateConfigTests(SimpleTestCase):
    def setUp(self):
        self.config = settings.TEMPLATES[0]

    def test_django_backend_with_app_dirs(self):
        self.assertEqual(
            self.config['BACKEND'],
            'django.template.backends.django.DjangoTemplates',
        )
        self.assertTrue(self.config['APP_DIRS'])

    def test_project_templates_directory_is_configured(self):
        expected = os.path.join(settings.BASE_DIR, 'templates')
        self.assertIn(expected, self.config['DIRS'])

    def test_required_context_processors(self):
        processors = self.config['OPTIONS']['context_processors']
        for processor in (
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'BITEQUE.context_processors.external_api_keys',
        ):
            with self.subTest(processor=processor):
                self.assertIn(processor, processors)

    def test_external_api_keys_processor_payload(self):
        from BITEQUE.context_processors import external_api_keys
        context = external_api_keys(mock.Mock())
        self.assertEqual(
            context['google_maps_api_key'], settings.GOOGLE_MAPS_API_KEY
        )
        self.assertEqual(context['site_url'], settings.SITE_URL)


class PasswordHasherTests(SimpleTestCase):
    def test_tests_use_the_fast_hasher(self):
        self.assertEqual(
            settings.PASSWORD_HASHERS,
            ['django.contrib.auth.hashers.MD5PasswordHasher'],
        )

    def test_testing_flag_tracks_the_test_command(self):
        from BITEQUE import settings as project_settings
        expected = len(sys.argv) > 1 and sys.argv[1] == 'test'
        self.assertEqual(project_settings._TESTING, expected)

    def test_password_minimum_length(self):
        validators = settings.AUTH_PASSWORD_VALIDATORS
        minimums = [
            v['OPTIONS'].get('min_length')
            for v in validators
            if 'OPTIONS' in v
        ]
        self.assertEqual(minimums, [8])


class SecurityConfigTests(SimpleTestCase):
    def test_clickjacking_and_mime_hardening(self):
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, 'same-origin')

    def test_secure_cookies_follow_import_time_debug_flag(self):
        from BITEQUE import settings as project_settings
        self.assertEqual(
            settings.SESSION_COOKIE_SECURE, not project_settings.DEBUG
        )
        self.assertEqual(
            settings.CSRF_COOKIE_SECURE, not project_settings.DEBUG
        )

    def test_ssl_redirect_and_hsts_disabled_for_tests(self):
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_proxy_ssl_header_is_configured(self):
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER,
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_secret_key_is_present(self):
        self.assertTrue(settings.SECRET_KEY)

    def test_booting_with_debug_off_and_no_secret_is_rejected(self):
        import subprocess
        env = dict(os.environ, DEBUG='False', SECRET_KEY='')
        code = (
            "import os, django;"
            "os.environ['DJANGO_SETTINGS_MODULE']='BITEQUE.settings';"
            "django.setup()"
        )
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(settings.BASE_DIR),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY environment variable', result.stderr)

    def test_booting_with_debug_off_and_explicit_secret_succeeds(self):
        import subprocess
        env = dict(
            os.environ, DEBUG='False',
            SECRET_KEY='a-real-production-secret-value',
        )
        code = (
            "import os, django;"
            "os.environ['DJANGO_SETTINGS_MODULE']='BITEQUE.settings';"
            "django.setup();"
            "from django.conf import settings as s;"
            "print(s.SECRET_KEY)"
        )
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(settings.BASE_DIR),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('a-real-production-secret-value', result.stdout)


class MiddlewareConfigTests(SimpleTestCase):
    def test_middleware_order(self):
        middleware = settings.MIDDLEWARE
        self.assertEqual(
            middleware[0], 'django.middleware.security.SecurityMiddleware'
        )
        self.assertEqual(
            middleware[1], 'whitenoise.middleware.WhiteNoiseMiddleware'
        )
        session = middleware.index(
            'django.contrib.sessions.middleware.SessionMiddleware'
        )
        auth = middleware.index(
            'django.contrib.auth.middleware.AuthenticationMiddleware'
        )
        csrf = middleware.index(
            'django.middleware.csrf.CsrfViewMiddleware'
        )
        messages = middleware.index(
            'django.contrib.messages.middleware.MessageMiddleware'
        )
        self.assertLess(session, auth)
        self.assertLess(csrf, auth)
        self.assertLess(auth, messages)
        self.assertEqual(
            middleware[-1],
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        )

    def test_csrf_settings(self):
        self.assertFalse(settings.CSRF_USE_SESSIONS)
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)


class StorageConfigTests(SimpleTestCase):
    def test_static_and_media_urls(self):
        self.assertEqual(settings.STATIC_URL, '/static/')
        self.assertEqual(settings.MEDIA_URL, '/media/')

    def test_media_root_lives_under_base_dir(self):
        self.assertEqual(Path(settings.MEDIA_ROOT), settings.BASE_DIR / 'media')

    def test_static_root_defaults_under_base_dir(self):
        if 'STATIC_ROOT' not in os.environ:
            self.assertEqual(
                Path(settings.STATIC_ROOT), settings.BASE_DIR / 'static'
            )

    def test_static_files_served_by_whitenoise(self):
        self.assertEqual(
            settings.STORAGES['staticfiles']['BACKEND'],
            'whitenoise.storage.CompressedStaticFilesStorage',
        )
        self.assertEqual(
            settings.STORAGES['default']['BACKEND'],
            'django.core.files.storage.FileSystemStorage',
        )

    def test_upload_limits_are_five_megabytes(self):
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)
        self.assertEqual(settings.FILE_UPLOAD_PERMISSIONS, 0o644)


class EmailAndApiConfigTests(SimpleTestCase):
    def test_brevo_smtp_defaults(self):
        self.assertEqual(settings.EMAIL_PORT, 587)
        self.assertTrue(settings.EMAIL_USE_TLS)
        if 'EMAIL_HOST' not in os.environ:
            self.assertEqual(
                settings.EMAIL_HOST, 'smtp-relay.brevo.com'
            )

    def test_third_party_keys_have_placeholder_defaults(self):
        self.assertTrue(settings.BREVO_API_KEY)
        self.assertTrue(settings.MAILERSEND_API_KEY)
        self.assertTrue(settings.MAILERSEND_DOMAIN)
        self.assertTrue(settings.GOOGLE_MAPS_API_KEY)
        self.assertTrue(settings.RAZORPAY_KEY_ID)
        self.assertTrue(settings.RAZORPAY_KEY_SECRET)

    def test_fast2sms_constants(self):
        self.assertEqual(
            settings.FAST2SMS_URL, 'https://www.fast2sms.com/dev/bulkV2'
        )
        self.assertEqual(settings.WHATSAPP_SENDER_ID, 'FSTSMS')
        self.assertTrue(settings.FAST2SMS_API_KEY)

    def test_osrm_server_url(self):
        self.assertEqual(
            settings.OSRM_SERVER_URL, 'http://router.project-osrm.org'
        )

    def test_site_url_has_no_trailing_slash(self):
        self.assertTrue(settings.SITE_URL)
        self.assertFalse(settings.SITE_URL.endswith('/'))


class RuntimeConfigTests(SimpleTestCase):
    def test_timezone_configuration(self):
        self.assertEqual(settings.TIME_ZONE, 'Asia/Kolkata')
        self.assertTrue(settings.USE_TZ)
        self.assertTrue(settings.USE_I18N)

    def test_delivery_pin_window(self):
        if 'DELIVERY_PIN_TTL_MINUTES' not in os.environ:
            self.assertEqual(settings.DELIVERY_PIN_TTL_MINUTES, 30)

    def test_allowed_hosts_are_non_empty(self):
        self.assertTrue(settings.ALLOWED_HOSTS)
        self.assertNotIn('', settings.ALLOWED_HOSTS)

    def test_fallback_sqlite_database_without_database_url(self):
        if not os.environ.get('DATABASE_URL'):
            self.assertEqual(
                settings.DATABASES['default']['ENGINE'],
                'django.db.backends.sqlite3',
            )

    def test_earnings_reset_logger_targets_the_earnings_log(self):
        logger = settings.LOGGING['loggers'][
            'rider_app.management.commands.reset_earnings'
        ]
        self.assertIn('earnings_reset_file', logger['handlers'])
        handler = settings.LOGGING['handlers']['earnings_reset_file']
        self.assertEqual(
            Path(handler['filename']).name, 'earnings_reset.log'
        )
        self.assertTrue(Path(handler['filename']).parent.is_dir())

    def test_rider_app_logger_targets_its_own_log(self):
        logger = settings.LOGGING['loggers']['rider_app']
        self.assertIn('rider_app_file', logger['handlers'])
        handler = settings.LOGGING['handlers']['rider_app_file']
        self.assertEqual(
            Path(handler['filename']).name, 'rider_app.log'
        )
        self.assertTrue(Path(handler['filename']).parent.is_dir())

    def test_loggers_do_not_share_a_file(self):
        handlers = settings.LOGGING['handlers']
        self.assertNotEqual(
            handlers['earnings_reset_file']['filename'],
            handlers['rider_app_file']['filename'],
        )

    def test_reset_and_application_logs_reach_the_console(self):
        # Render only keeps the service log stream, so the important records
        # must also go to stdout.
        for logger_name in ('rider_app.earnings', 'rider_app'):
            with self.subTest(logger=logger_name):
                self.assertIn(
                    'console', settings.LOGGING['loggers'][logger_name]['handlers']
                )
        console = settings.LOGGING['handlers']['console']
        self.assertEqual(console['class'], 'logging.StreamHandler')

    def test_reset_command_does_not_double_print(self):
        # The command writes its summary to stdout, so its logger must not
        # also write to the console.
        logger = settings.LOGGING['loggers'][
            'rider_app.management.commands.reset_earnings'
        ]
        self.assertNotIn('console', logger['handlers'])
        self.assertIn('earnings_reset_file', logger['handlers'])


class UrlResolutionTests(SimpleTestCase):
    def collect(self):
        return list(
            iter_url_entries(get_resolver().url_patterns)
        )

    def test_route_table_is_substantial(self):
        entries = [entry for entry in self.collect() if entry[0]]
        self.assertGreaterEqual(len(entries), 80)

    def test_every_unparameterised_route_reverses(self):
        failures = []
        checked = 0
        for name, pattern, _url_pattern in self.collect():
            if not name or '<' in pattern:
                continue
            checked += 1
            try:
                reverse(name)
            except NoReverseMatch as exc:
                failures.append(f'{name}: {exc}')
        self.assertGreater(checked, 50)
        self.assertEqual(failures, [])

    def test_core_routes_resolve_to_expected_paths(self):
        expectations = {
            '/admin/': 'admin:index',
            '/': 'home',
            '/merchant-login/': 'merchant_login',
        }
        for path, expected_name in expectations.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.view_name, expected_name)

    def test_media_route_is_named_protected(self):
        match = resolve('/media/avatars/me.jpg')
        self.assertEqual(match.func.__name__, 'protected_media')

    def test_url_modules_import_cleanly(self):
        from user_app import urls as user_urls
        from rider_app import urls as rider_urls
        from merchant_app import urls as merchant_urls
        for module in (user_urls, rider_urls, merchant_urls):
            with self.subTest(module=module.__name__):
                self.assertTrue(hasattr(module, 'urlpatterns'))

    def test_duplicate_route_names_still_reversible(self):
        for name in ('awaiting-approval', 'merchant_logout'):
            with self.subTest(name=name):
                self.assertTrue(reverse(name))


class SystemCheckTests(TestCase):
    def test_django_system_checks_pass(self):
        call_command('check', verbosity=0)
