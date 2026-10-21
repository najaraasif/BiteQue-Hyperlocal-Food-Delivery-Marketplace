"""Business-date semantics and the daily earnings reset.

The rider earnings reset moves the money a rider earned during a business day
from the running accumulator (``Rider.today_earnings``) into the running
balance (``Rider.current_balance``) and closes that business day in the
ledger.

Two things are shared between the delivery path and the reset, so they live
here:

* :func:`business_date` - the local business day a moment belongs to. The
  delivery path used ``timezone.now().date()`` (UTC) while the reset used
  local time, so a delivery between 00:00 and 05:30 IST was filed under the
  previous day and the two paths disagreed about which day a row belonged to.
* :func:`close_business_date` - the reset itself, with its locking,
  idempotency and transaction rules.

Money rules
-----------
* The accumulator is emptied exactly once per business date. Because the reset
  always zeroes it, the accumulator holds exactly the earnings produced since
  the previous close, so crediting it against a business date cannot double
  count.
* A business date can be closed only once. ``EarningsResetRun`` has a unique
  business date, so the database itself refuses a second close.
* One ledger row per rider per business date. The delivery path already keeps
  a single ``RiderEarning`` row per rider per day; the reset must not add a
  second row for the same day, otherwise every day's earnings are counted
  twice by ``Rider.get_total_earnings()``.
"""
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Arbitrary but stable key for the PostgreSQL advisory lock that serialises
# resets. Any 64 bit integer works; it must never change once deployed.
RESET_ADVISORY_LOCK_KEY = 741852963


def business_date(moment=None):
    """Return the local business day (settings.TIME_ZONE) a moment belongs to.

    The business day is the calendar day in the application's local time
    zone, not in UTC: a delivery completed at 00:30 IST belongs to the day
    the rider worked, not to the previous UTC day.
    """
    moment = timezone.now() if moment is None else moment
    return timezone.localtime(moment).date()


def current_business_date():
    """The business day that is currently open (today, local time)."""
    return business_date()


def closed_business_dates():
    """Business dates that have already been closed by a reset."""
    from rider_app.models import EarningsResetRun

    return set(
        EarningsResetRun.objects.values_list('business_date', flat=True)
    )


def earliest_recorded_business_date():
    """The earliest business date that carries any recorded activity.

    Either a daily earning row or a reset-run record. It is the anchor for
    the catch-up window: a business date that was never recorded cannot be
    reconstructed, but a recorded one must not be skipped silently.
    """
    from django.db.models import Min

    from rider_app.models import EarningsResetRun, RiderEarning

    candidates = [
        RiderEarning.objects.aggregate(first=Min('date'))['first'],
        EarningsResetRun.objects.aggregate(
            first=Min('business_date')
        )['first'],
    ]
    candidates = [day for day in candidates if day is not None]
    return min(candidates) if candidates else None


def configured_start_date():
    """The configured catch-up anchor, or ``None``.

    ``EARNINGS_RESET_START_DATE`` pins the earliest business date the
    deployment will ever close. It is what makes a missed night recoverable:
    without it the anchor moves forward with "yesterday" and the missed
    business date would be skipped forever.
    """
    raw = (getattr(settings, 'EARNINGS_RESET_START_DATE', None) or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        raise ImproperlyConfigured(
            'EARNINGS_RESET_START_DATE must be a date in YYYY-MM-DD format, '
            f'got {raw!r}'
        )


def catch_up_plan(today=None, max_days=None, start_date=None):
    """Plan which business dates still have to be closed.

    Returns a dict with:

    * ``due`` - the business dates to close, oldest first, never including
      the current (still open) business day;
    * ``window_start`` - the first business date that was considered;
    * ``overdue`` - how many unclosed business dates exist in total;
    * ``skipped`` - how many of them are *not* in this run because of the
      bound. A non-zero value is always reported, never dropped silently.
    """
    today = today or current_business_date()
    if max_days is None:
        max_days = getattr(settings, 'EARNINGS_RESET_MAX_DAYS', 31)
    closed = closed_business_dates()

    start = start_date or configured_start_date() or earliest_recorded_business_date()
    if start is None:
        # Nothing has ever been recorded: the only date that can be closed is
        # the day that just ended.
        start = today - timedelta(days=1)

    unclosed = []
    day = start
    while day < today:
        if day not in closed:
            unclosed.append(day)
        day += timedelta(days=1)

    due = unclosed[:max_days]
    return {
        'due': due,
        'window_start': start,
        'overdue': len(unclosed),
        'skipped': len(unclosed) - len(due),
        'max_days': max_days,
    }


def due_business_dates(today=None, max_days=None, start_date=None):
    """Business dates that still need to be closed, oldest first.

    Every business date between the catch-up anchor and yesterday that no
    reset has closed yet is due, so a missed night is caught up instead of
    being skipped. The list is bounded by ``max_days``; the overflow is
    reported by :func:`catch_up_plan` and never dropped silently.
    """
    return catch_up_plan(
        today=today, max_days=max_days, start_date=start_date
    )['due']


def next_business_date_to_close(today=None, max_days=None, start_date=None):
    """The single business date the next run should close first, or ``None``."""
    due = due_business_dates(
        today=today, max_days=max_days, start_date=start_date
    )
    return due[0] if due else None



@contextmanager
def reset_lock(db_connection=None):
    """Serialise resets with a transaction scoped PostgreSQL advisory lock.

    Yields a dict with two keys:

    * ``state`` is ``'locked'`` (this process holds the lock),
      ``'busy'`` (another process holds it) or ``'unavailable'`` (the backend
      has no advisory locks).
    * ``detail`` explains what was used, so the log never claims a guarantee
      the backend cannot give.

    ``pg_try_advisory_xact_lock`` is released automatically when the
    surrounding transaction ends, including on rollback, so a crashed reset
    never leaves a stale lock behind. It must therefore be taken inside the
    transaction that performs the work.
    """
    db_connection = db_connection or connection
    if db_connection.vendor != 'postgresql':
        yield {
            'state': 'unavailable',
            'detail': (
                f"advisory locks are not available on the "
                f"'{db_connection.vendor}' backend; this run is protected only "
                "by the unique business date constraint and the backend's own "
                "write serialisation, not by a database lock"
            ),
        }
        return
    with db_connection.cursor() as cursor:
        cursor.execute(
            'SELECT pg_try_advisory_xact_lock(%s)', [RESET_ADVISORY_LOCK_KEY]
        )
        acquired = bool(cursor.fetchone()[0])
    if acquired:
        yield {'state': 'locked', 'detail': 'postgres advisory lock acquired'}
    else:
        yield {
            'state': 'busy',
            'detail': 'another reset already holds the advisory lock',
        }


def _ensure_daily_ledger_row(rider, day, amount):
    """Make sure the day has exactly one ledger row for this rider.

    Returns ``(row, created)``. When the delivery path already recorded the
    day, that row is kept untouched - it already accounts for the earnings -
    and the reset must not add a second row for the same day.
    """
    from rider_app.models import RiderEarning

    existing = (
        RiderEarning.objects.select_for_update()
        .filter(rider=rider, date=day)
        .first()
    )
    if existing is not None:
        if existing.total_earnings != amount:
            logger.warning(
                "Rider %s already has a ledger row for %s with total %s but the "
                "accumulator holds %s; keeping the existing row",
                rider.id, day, existing.total_earnings, amount,
            )
        return existing, False

    row = RiderEarning.objects.create(
        rider=rider,
        date=day,
        total_earnings=amount,
        orders_completed=rider.get_total_orders_completed(),
        distance_km=Decimal('0.00'),
        distance_earning=Decimal('0.00'),
        commission_earning=Decimal('0.00'),
    )
    return row, True


def close_business_date(day, source='cron'):
    """Close one business date.

    The whole close runs in a single transaction: either every rider is
    credited and the day is recorded as closed, or nothing changes at all.
    A partially applied reset cannot leave balances and ledger rows out of
    sync, and the day stays open so the run can simply be repeated.

    Returns a dict describing what happened. ``status`` is one of:

    * ``closed`` - the day was closed by this call;
    * ``already_closed`` - the day had already been closed;
    * ``locked`` - another reset holds the lock, this run did nothing;
    * ``no_opening`` - the day is not in the past, nothing to close.
    """
    from rider_app.models import EarningsResetRun, Rider

    today = current_business_date()
    if day >= today:
        return {
            'status': 'no_opening',
            'business_date': day,
            'message': f'{day} is not a closed business day yet',
        }

    summary = {
        'status': 'closed',
        'business_date': day,
        'riders_processed': 0,
        'total_credited': Decimal('0.00'),
        'ledger_rows_created': 0,
        'source': source,
    }

    try:
        with transaction.atomic():
            with reset_lock() as lock:
                if lock['state'] == 'busy':
                    logger.warning(
                        "Skipping reset for business date %s: %s",
                        day, lock['detail'],
                    )
                    summary['status'] = 'locked'
                    summary['message'] = lock['detail']
                    return summary
                if lock['state'] == 'unavailable':
                    logger.warning(
                        "Reset for business date %s runs without a database "
                        "lock: %s",
                        day, lock['detail'],
                    )
                    summary['lock'] = 'unavailable'

                if EarningsResetRun.objects.filter(business_date=day).exists():
                    logger.info(
                        "Business date %s is already closed; nothing to do", day
                    )
                    summary['status'] = 'already_closed'
                    summary['message'] = 'business date already closed'
                    return summary

                logger.info(
                    "Reset started for business date %s (%s)", day, lock['detail']
                )

                credited = Decimal('0.00')
                processed = 0
                rows_created = 0
                for rider in Rider.objects.select_for_update().order_by('id'):
                    if rider.today_earnings <= 0:
                        continue
                    amount = rider.today_earnings
                    _row, created = _ensure_daily_ledger_row(rider, day, amount)
                    if created:
                        rows_created += 1
                    rider.current_balance += amount
                    rider.today_earnings = Decimal('0.00')
                    rider.save(
                        update_fields=['current_balance', 'today_earnings']
                    )
                    credited += amount
                    processed += 1

                run = EarningsResetRun.objects.create(
                    business_date=day,
                    riders_processed=processed,
                    total_credited=credited,
                    source=source,
                )
                run.completed_at = timezone.now()
                run.save(update_fields=['completed_at'])

                summary.update({
                    'riders_processed': processed,
                    'total_credited': credited,
                    'ledger_rows_created': rows_created,
                    'run_id': run.id,
                })
                logger.info(
                    "Reset complete for business date %s: %s riders processed, "
                    "%s credited, %s ledger rows created",
                    day, processed, credited, rows_created,
                )
                return summary
    except IntegrityError:
        # The unique business date may have been taken by a concurrent run.
        if EarningsResetRun.objects.filter(business_date=day).exists():
            logger.warning(
                "Business date %s was closed by another process; nothing to do",
                day,
            )
            summary['status'] = 'already_closed'
            summary['message'] = 'business date closed concurrently'
            return summary
        raise


def close_due_business_dates(today=None, max_days=None, start_date=None,
                             source='cron'):
    """Close every business date that is due, oldest first.

    The dates are processed in chronological order so the audit trail reads
    naturally and the accumulated earnings are credited against the oldest
    outstanding business date - the only attribution the single accumulator
    allows. The per-day detail stays correct because the delivery path writes
    one earning row per rider per business day.

    A run that finds the advisory lock held by another process stops at once
    and leaves the remaining dates open for the next run.
    """
    plan = catch_up_plan(
        today=today, max_days=max_days, start_date=start_date
    )
    results = []
    for day in plan['due']:
        summary = close_business_date(day, source=source)
        results.append(summary)
        if summary['status'] == 'locked':
            logger.warning(
                'Stopping the catch-up: another reset holds the lock; %s '
                'business date(s) stay open',
                len(plan['due']) - len(results),
            )
            break
    return {
        'status': 'closed' if results else 'nothing_due',
        'plan': plan,
        'results': results,
        'closed_dates': [
            item['business_date'] for item in results
            if item['status'] == 'closed'
        ],
        'total_credited': sum(
            (item.get('total_credited', Decimal('0.00')) for item in results),
            Decimal('0.00'),
        ),
    }
