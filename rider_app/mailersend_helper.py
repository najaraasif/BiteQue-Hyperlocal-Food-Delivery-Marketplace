from mailersend import emails
from django.conf import settings
from django.http import HttpResponse
def send_mailersend_email(recipient_email, subject, text_content, html_content=None):
    mailer = emails.NewEmail(settings.MAILERSEND_API_KEY)
    
    mail_body = {}
    mail_from = {
        "email": settings.DEFAULT_FROM_EMAIL,
        "name": "BiteQue Rider Support"
    }
    recipients = [
        {
            "email": recipient_email,
            "name": recipient_email.split('@')[0]
        }
    ]
    
    mailer.set_mail_from(mail_from, mail_body)
    mailer.set_mail_to(recipients, mail_body)
    mailer.set_subject(subject, mail_body)
    mailer.set_plaintext_content(text_content, mail_body)
    
    if html_content:
        mailer.set_html_content(html_content, mail_body)
    
    response = mailer.send(mail_body)
    return HttpResponse("Ok", status=200)