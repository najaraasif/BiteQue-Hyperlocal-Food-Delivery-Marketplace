from django.test import TestCase

from rider_app.apps import RiderAppConfig


class SchedulerTests(TestCase):
    def test_scheduler_not_run_during_tests(self):
        config = RiderAppConfig.create('rider_app')
        # Must return early (no thread) because 'test' is on sys.argv.
        config.ready()
