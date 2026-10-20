"""Daily rider earnings reset.

Two ways to run it:

``python manage.py reset_earnings --once``
    Close the business date that is due, then exit. This is the mode a
    scheduled job (Render Cron Job) uses: one process, one run, one exit.
    Repeating it is safe - a business date can only be closed once.

``python manage.py reset_earnings``
    Start an in-process scheduler thread that closes the due business date
    every night. This is a development convenience. In production the web
    service must not run it, because every gunicorn worker would start its
    own scheduler; set ``EARNINGS_RESET_SCHEDULER_ENABLED=0`` (the default
    when ``DEBUG`` is off) and use the scheduled job instead.

The reset itself lives in :mod:`rider_app.earnings`, which owns the business
date rules, the database lock and the transaction.
"""
import logging
import time
from datetime import datetime, timedelta
from threading import Thread

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone

from rider_app.earnings import (
    close_business_date,
    current_business_date,
    due_business_dates,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reset rider daily earnings into the running balance'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Close the business date that is due and exit.',
        )
        parser.add_argument(
            '--date',
            dest='business_date',
            help='Close a specific business date (YYYY-MM-DD) and exit.',
        )
        parser.add_argument(
            '--max-days',
            type=int,
            default=7,
            help=(
                'Maximum number of overdue business days considered when '
                'catching up (default: 7).'
            ),
        )
        parser.add_argument(
            '--source',
            default='cron',
            choices=['cron', 'manual', 'thread'],
            help='Where this run came from (recorded in the reset ledger).',
        )

    def handle(self, *args, **options):
        # Django writes whatever handle() returns to stdout, so the summary is
        # kept on the command instance instead of being returned.
        if options.get('business_date'):
            self.result = self.run_specific_date(options)
        elif options.get('once'):
            self.result = self.run_once(options)
        else:
            self.result = self.run_scheduler(options)

    # -- one shot --------------------------------------------------------
    def run_specific_date(self, options):
        raw = options['business_date']
        try:
            day = datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(
                f'--date must be a business date in YYYY-MM-DD format, got {raw!r}'
            )
        if day >= current_business_date():
            raise CommandError(
                f'{day} is not a closed business day yet; the current business '
                f'day is {current_business_date()}'
            )

        summary = close_business_date(day, source=options.get('source', 'manual'))
        self.report(summary)
        return summary

    def run_once(self, options):
        today = current_business_date()
        due = due_business_dates(today=today, max_days=options['max_days'])
        if not due:
            message = f'No business date is due (today is {today})'
            logger.info(message)
            self.stdout.write(self.style.SUCCESS(message))
            return {'status': 'nothing_due', 'business_date': None}

        target = due[0]
        if len(due) > 1:
            # Never close several days in one run: the accumulator holds the
            # earnings of every overdue day, so it is credited against the
            # oldest due date and the remaining dates are closed by the
            # following runs (with an empty accumulator).
            logger.warning(
                'Business dates %s are overdue; closing the oldest one (%s) now. '
                'The earnings accumulated since the last close are credited '
                'against %s; the remaining dates are closed by later runs.',
                ', '.join(str(day) for day in due), target, target,
            )

        summary = close_business_date(target, source=options.get('source', 'cron'))
        self.report(summary)
        return summary

    # -- in process scheduler (development) ------------------------------
    def run_scheduler(self, options):
        connections.close_all()

        def reset_daily_earnings():
            while True:
                try:
                    now = timezone.localtime(timezone.now())
                    midnight = timezone.make_aware(
                        timezone.datetime.combine(
                            now.date() + timedelta(days=1),
                            datetime.min.time(),
                        )
                    )
                    wait_seconds = max((midnight - now).total_seconds(), 0.0)

                    logger.info(
                        'Waiting %.1f seconds until midnight...', wait_seconds
                    )
                    time.sleep(wait_seconds)

                    today = current_business_date()
                    due = due_business_dates(today=today, max_days=options['max_days'])
                    if not due:
                        logger.info('No business date is due at %s', today)
                    else:
                        summary = close_business_date(
                            due[0], source=options.get('source', 'thread')
                        )
                        self.report(summary)

                except Exception as exc:  # pragma: no cover - defensive
                    logger.error('Error in scheduler loop: %s', exc)
                    time.sleep(60)  # retry in 1 minute

        thread = Thread(target=reset_daily_earnings, daemon=True)
        thread.start()

        logger.info('Started earnings reset scheduler')
        self.stdout.write(self.style.SUCCESS('Started earnings reset scheduler'))
        return {'status': 'scheduler_started'}

    # -- reporting -------------------------------------------------------
    def report(self, summary):
        """Print the outcome.

        The command writes its summary to stdout, the service logger writes
        the detail to the log file and the console, so nothing is printed
        twice.
        """
        status = summary.get('status')
        if status == 'closed':
            message = (
                f"Closed business date {summary['business_date']}: "
                f"{summary['riders_processed']} riders, "
                f"{summary['total_credited']} credited, "
                f"{summary['ledger_rows_created']} ledger rows created"
            )
            self.stdout.write(self.style.SUCCESS(message))
        elif status == 'already_closed':
            message = f"Business date {summary['business_date']} was already closed"
            self.stdout.write(message)
        elif status == 'locked':
            # The service logger already recorded why the run was skipped.
            message = (
                f"Skipped business date {summary['business_date']}: "
                f"{summary.get('message', 'another reset is running')}"
            )
            logger.warning(message)
        elif status == 'no_opening':
            message = summary.get('message', 'business date is not due')
            self.stdout.write(message)
        else:
            message = str(summary.get('message', summary))
            self.stdout.write(message)
        return summary
