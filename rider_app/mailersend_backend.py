from django.core.mail.backends.smtp import EmailBackend
from django.conf import settings

class MailerSendBackend(EmailBackend):
    def __init__(self, *args, **kwargs):
        kwargs.update({
            'host': settings.EMAIL_HOST,
            'port': settings.EMAIL_PORT,
            'username': settings.EMAIL_HOST_USER,
            'password': settings.EMAIL_HOST_PASSWORD,
            'use_tls': settings.EMAIL_USE_TLS,
        })
        super().__init__(*args, **kwargs)