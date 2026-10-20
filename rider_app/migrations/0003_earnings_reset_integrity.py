"""Earnings ledger integrity: a reset-run ledger and one earning row per
rider per business day.

Why
---
* ``EarningsResetRun`` records which business dates have been closed. Its
  unique ``business_date`` makes a second close of the same day impossible at
  the database level, which is what makes the daily reset idempotent and
  safe to retry.
* ``RiderEarning`` gets a unique ``(rider, date)`` constraint. The delivery
  path already keeps a single row per rider per day; the daily reset used to
  add a second row for the same day, which made
  ``Rider.get_total_earnings()`` count every day twice.

The constraint is only added when the data allows it: the check below aborts
the migration with a clear message if duplicate rows already exist. It never
deletes or rewrites earning records.
"""
from django.db import migrations, models
from decimal import Decimal


def find_duplicate_daily_earnings(model):
    """Return the (rider, date) pairs that have more than one earning row."""
    return list(
        model.objects.values('rider_id', 'date')
        .annotate(rows=models.Count('id'))
        .filter(rows__gt=1)
        .order_by('rider_id', 'date')
    )


def assert_model_has_no_duplicate_daily_earnings(model):
    """Abort instead of silently dropping duplicated earning rows."""
    duplicates = find_duplicate_daily_earnings(model)
    if not duplicates:
        return
    details = ', '.join(
        f"rider={item['rider_id']} date={item['date']} rows={item['rows']}"
        for item in duplicates[:20]
    )
    raise RuntimeError(
        'rider_app_riderearning contains duplicate (rider, date) rows, so '
        'the unique daily earning constraint cannot be added. No data was '
        'changed. Reconcile the duplicates manually, then re-run the '
        f'migration. Duplicates: {details}'
    )


def assert_no_duplicate_daily_earnings(apps, schema_editor):
    RiderEarning = apps.get_model('rider_app', 'RiderEarning')
    assert_model_has_no_duplicate_daily_earnings(RiderEarning)


class Migration(migrations.Migration):

    dependencies = [
        ('rider_app', '0002_ensure_acceptance_columns'),
    ]

    operations = [
        migrations.CreateModel(
            name='EarningsResetRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_date', models.DateField(unique=True)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('riders_processed', models.PositiveIntegerField(default=0)),
                ('total_credited', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('source', models.CharField(choices=[('cron', 'Scheduled job'), ('manual', 'Manual run'), ('thread', 'In-process scheduler')], default='cron', max_length=20)),
                ('note', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Earnings reset run',
                'verbose_name_plural': 'Earnings reset runs',
                'ordering': ['-business_date'],
            },
        ),
        migrations.RunPython(
            assert_no_duplicate_daily_earnings,
            migrations.RunPython.noop,
            elidable=False,
        ),
        migrations.AddConstraint(
            model_name='riderearning',
            constraint=models.UniqueConstraint(fields=('rider', 'date'), name='unique_earning_per_rider_and_date'),
        ),
    ]
