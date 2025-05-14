from django.test import TestCase
from rider_app.apps import RiderAppConfig

class SchedulerTests(TestCase):
    def test_scheduler_not_run_during_tests(self):
        config = RiderAppConfig('rider_app', 'rider_app')
        config.ready() 