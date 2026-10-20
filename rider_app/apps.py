from django.apps import AppConfig
from django.conf import settings
import sys


class RiderAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rider_app'

    def ready(self):
        import rider_app.signals

        # Never spawn the earnings-reset thread for management commands
        # (tests, migrations, checks, collectstatic); gunicorn/runserver
        # workers do start it.
        if any(cmd in sys.argv for cmd in ('test', 'migrate', 'makemigrations', 'check', 'collectstatic', 'shell')):
            return

        # The in-process scheduler is a development convenience only. Every
        # gunicorn worker would start its own scheduler and they would race
        # each other, so in production the reset must run from a scheduled
        # job (Render Cron Job) with `manage.py reset_earnings --once`.
        if not settings.EARNINGS_RESET_SCHEDULER_ENABLED:
            return

        import threading
        from .management.commands.reset_earnings import Command

        def delayed_start():
            import time
            time.sleep(2)
            Command().handle()

        threading.Thread(target=delayed_start, daemon=True).start()
