from django.apps import AppConfig
from django.conf import settings
import sys

class RiderAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rider_app'

    def ready(self):
        import rider_app.signals
        
        if 'test' in sys.argv or 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return
        
        import threading
        from .management.commands.reset_earnings import Command
        
        def delayed_start():
            import time
            time.sleep(2)  
            Command().handle()
            
        threading.Thread(target=delayed_start, daemon=True).start()