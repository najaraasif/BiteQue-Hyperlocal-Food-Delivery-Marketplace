import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings

def send_brevo_email(subject, html_content, recipient_email, recipient_name):
    # Configure API key authorization
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = settings.BREVO_API_KEY
    
    # Create API instance
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )
    # Prepare email content
    sender = {"name": "ZemQue Support", "email": settings.DEFAULT_FROM_EMAIL}
    to = [{"email": recipient_email, "name": recipient_name}]
    
    try:
        # Create send email object
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender=sender,
            to=to,
            html_content=html_content,
            subject=subject
        )
        
        # Send email
        api_response = api_instance.send_transac_email(send_smtp_email)
        return api_response
        
    except ApiException as e:
        print(f"Exception when sending email: {e}\n")
        print(f"Response headers: {e.headers}\n")
        print(f"Response body: {e.body}\n")
        return None