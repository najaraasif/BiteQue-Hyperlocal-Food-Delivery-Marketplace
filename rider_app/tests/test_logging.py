"""Tests for the logging split between the earnings reset job and the rest
of the rider application.

The two must be distinguishable: a scheduler failure and a rider view error
must not end up in the same file, otherwise a view error looks like a broken
earnings reset (which is exactly how the 2025 incident was misdiagnosed).
"""
import logging
import uuid
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from rider_app.management.commands import reset_earnings as reset_module
from rider_app.views import logger as views_logger

RESET_LOGGER_NAME = 'rider_app.management.commands.reset_earnings'


def effective_log_files(logger_name):
    """Return the set of log files a record for ``logger_name`` is written to."""
    logger = logging.getLogger(logger_name)
    files = set()
    while logger is not None:
        for handler in logger.handlers:
            filename = getattr(handler, 'baseFilename', None)
            if filename:
                files.add(Path(filename).name)
        if not logger.propagate:
            break
        logger = logger.parent
    return files


class LoggingRoutingTests(SimpleTestCase):
    def test_reset_job_and_application_use_different_files(self):
        reset_files = effective_log_files(RESET_LOGGER_NAME)
        app_files = effective_log_files('rider_app.views')

        self.assertIn('earnings_reset.log', reset_files)
        self.assertIn('rider_app.log', app_files)
        self.assertEqual(reset_files & app_files, set())

    def test_reset_module_uses_the_configured_reset_logger(self):
        self.assertEqual(reset_module.logger.name, RESET_LOGGER_NAME)
        self.assertEqual(
            views_logger.name,
            'rider_app.views',
        )

    def test_reset_logger_does_not_propagate_into_the_application_log(self):
        self.assertFalse(
            settings.LOGGING['loggers'][RESET_LOGGER_NAME]['propagate']
        )
        self.assertFalse(settings.LOGGING['loggers']['rider_app']['propagate'])

    def test_application_error_is_only_written_to_the_application_log(self):
        marker = f'view-error-marker-{uuid.uuid4().hex}'

        logging.getLogger('rider_app.views').error(marker)

        reset_log = Path(settings.BASE_DIR / 'logs' / 'earnings_reset.log')
        app_log = Path(settings.BASE_DIR / 'logs' / 'rider_app.log')

        self.assertIn(marker, app_log.read_text(encoding='utf-8'))
        if reset_log.exists():
            self.assertNotIn(marker, reset_log.read_text(encoding='utf-8'))

    def test_reset_failure_is_only_written_to_the_reset_log(self):
        marker = f'reset-error-marker-{uuid.uuid4().hex}'

        logging.getLogger(RESET_LOGGER_NAME).error(marker)

        reset_log = Path(settings.BASE_DIR / 'logs' / 'earnings_reset.log')
        app_log = Path(settings.BASE_DIR / 'logs' / 'rider_app.log')

        self.assertIn(marker, reset_log.read_text(encoding='utf-8'))
        if app_log.exists():
            self.assertNotIn(marker, app_log.read_text(encoding='utf-8'))
