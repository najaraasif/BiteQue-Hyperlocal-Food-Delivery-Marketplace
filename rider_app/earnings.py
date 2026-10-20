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
from datetime import date, timedelta
from decimal import Decimal

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


def due_business_dates(today=None, max_days=7):
    """Business dates that still need to be closed, oldest first.

    A business date is due when it is in the past (relative to the local
    business day) and no reset has closed it yet. The search starts at the day
    after the last closed business date, so a reset that has been running
    normally closes one day per run instead of falling back to the oldest
    possible date. The list is capped at ``max_days`` entries so a long
    outage cannot turn a single run into a silent multi-day reset.
    """
    today = today or current_business_date()
    closed = closed_business_dates()
    if not closed:
        # Nothing has ever been closed: the day that just ended is due.
        return [today - timedelta(days=1)]

    candidates = []
    candidate = max(closed) + timedelta(days=1)
    while candidate < today and len(candidates) < max_days:
        if candidate not in closed:
            candidates.append(candidate)
        candidate += timedelta(days=1)
    return candidates


def next_business_date_to_close(today=None, max_days=7):
    """The single business date the next run should close, or ``None``."""
    due = due_business_dates(today=today, max_days=max_days)
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
