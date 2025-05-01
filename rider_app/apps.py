from django.apps import AppConfig


class RiderAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rider_app'

    def ready(self):
        import rider_app.signals