# management/commands/reset_earnings.py

import time
from threading import Thread
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, time as datetime_time
from decimal import Decimal
import logging
from django.db import connections

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Starts a background thread to reset earnings daily at midnight'

    def handle(self, *args, **options):
        connections.close_all()

        def reset_daily_earnings():
            while True:
                try:
                    from rider_app.models import Rider, RiderEarning

                    now = timezone.localtime(timezone.now())
                    midnight = timezone.make_aware(
                        timezone.datetime.combine(
                            now.date() + timedelta(days=1),
                            datetime_time(0, 0)
                        )
                    )
                    wait_seconds = (midnight - now).total_seconds()

                    logger.info(f"Waiting {wait_seconds:.1f} seconds until midnight...")
                    time.sleep(wait_seconds)

                    process_daily_reset()

                except Exception as e:
                    logger.error(f"Error in scheduler loop: {str(e)}")
                    time.sleep(60)  # retry in 1 minute

        def process_daily_reset():
            try:
                from rider_app.models import Rider, RiderEarning
                logger.info("Midnight - Resetting earnings...")

                yesterday = (timezone.localtime(timezone.now()) - timedelta(days=1)).date()
                riders_processed = 0
                total_transferred = Decimal('0.00')

                for rider in Rider.objects.all():
                    try:
                        if rider.today_earnings > 0:
                            logger.info("Processing rider %s: today's earnings = %s", rider.id, rider.today_earnings)

                            RiderEarning.objects.create(
                                rider=rider,
                                date=yesterday,
                                total_earnings=rider.today_earnings,
                                orders_completed=rider.get_total_orders_completed(),
                                distance_km=Decimal('0.00'),
                                distance_earning=Decimal('0.00'),
                                commission_earning=Decimal('0.00')
                            )

                            # Add today's earnings to current balance only once
                            rider.current_balance += rider.today_earnings

                            # Reset today's earnings to zero
                            rider.today_earnings = Decimal('0.00')

                            rider.save(update_fields=['current_balance', 'today_earnings'])

                            logger.info(
                                "Updated rider %s: current balance = %s, today's earnings reset to 0",
                                rider.id, rider.current_balance
                            )

                            riders_processed += 1
                        else:
                            logger.info(f"Rider {rider.id} skipped (₹0 earnings)")
                    except Exception as rider_exc:
                        logger.error(f"Error processing rider {rider.id}: {str(rider_exc)}")
                        continue  # Continue with next rider

                logger.info(
                    "Reset complete. Processed %s riders (transferred %s to balances).",
                    riders_processed, total_transferred
                )

            except Exception as e:
                logger.error(f"Error during reset: {str(e)}")

        # Start background thread
        thread = Thread(target=reset_daily_earnings, daemon=True)
        thread.start()

        logger.info("Started earnings reset scheduler")
        self.stdout.write(self.style.SUCCESS("Started earnings reset scheduler"))
