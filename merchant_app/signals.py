import logging

from mailersend import emails
from django.conf import settings
import requests

logger = logging.getLogger(__name__)

def send_merchant_verification_email(merchant):
    mailer = emails.NewEmail(settings.MAILERSEND_API_KEY)

    subject = 'Your Merchant Account is Approved'
    plain_text = f"Hello {merchant.name},\n\nYour merchant account has been approved. You can now log in.\n\nThank you!"

    html_content = f"""
    <html>
    <head>
      <style>
        body {{ font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 20px; }}
        .container {{ background-color: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: auto; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #007bff; }}
        p {{ font-size: 12px; line-height: 1.6; color: Red; }}
        .button {{
          display: inline-block;
          padding: 10px 20px;
          margin-top: 20px;
          font-size: 16px;
          background-color: #28a745;
          color: white;
          text-decoration: none;
          border-radius: 5px;
        }}
      </style>
    </head>
    <body>
      <div class="container">
        <h1>Welcome, {merchant.name}!</h1>
        <p>Your merchant account has been <strong>approved</strong>.</p>
        <p>You can now log in to add your restaurant, start managing your listings and booast sales.</p>
        <a href="http://127.0.0.1:8000/merchant/login/" class="button">Log in Now</a>
        <p style="margin-top: 40px;">Thank you for choosing <strong>BiteQue</strong>!</p>
      </div>
    </body>
    </html>
    """

    email_data = {
        'from': {
            'email': settings.DEFAULT_FROM_EMAIL,
            'name': 'BiteQue'
        },
        'to': [
            {
                'email': merchant.username.email
            }
        ],
        'subject': subject,
        'text': plain_text,
        'html': html_content
    }

    try:
        response = mailer.send(email_data)
        logger.info("Merchant verification e-mail sent: %s", response)
    except Exception as exc:
        logger.warning("Merchant verification e-mail to %s failed: %s", merchant.username.email, exc)


def send_merchant_restaurant_email(restaurant):
    mailer = emails.NewEmail(settings.MAILERSEND_API_KEY)

    subject = 'Your Merchant Account is Approved'
    plain_text = f"Hello {restaurant.owner},\n\nYour Restaurant has been approved on BiteQue. You can now log in.\n\nThank you!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <style>
          body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f4f6f8;
            padding: 40px 0;
            margin: 0;
          }}
          .email-container {{
            max-width: 650px;
            margin: auto;
            background-color: #ffffff;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1);
            color: #333333;
          }}
          h1 {{
            font-size: 26px;
            color: #2c3e50;
            margin-bottom: 10px;
          }}
          p {{
            font-size: 16px;
            line-height: 1.8;
            color: #555555;
          }}
          .highlight {{
            color: #28a745;
            font-weight: 600;
          }}
          .btn {{
            display: inline-block;
            padding: 12px 25px;
            background-color: #007bff;
            color: #ffffff;
            text-decoration: none;
            font-size: 16px;
            font-weight: 500;
            border-radius: 6px;
            margin-top: 25px;
            transition: background-color 0.3s ease;
          }}
          .btn:hover {{
            background-color: #0056b3;
          }}
          .footer {{
            text-align: center;
            font-size: 13px;
            color: #999999;
            margin-top: 40px;
          }}
        </style>
      </head>
      <body>
        <div class="email-container">
          <h1>Congratulations, {restaurant.owner}! 🎉</h1>
          <p>
            We're excited to let you know that your restaurant <span class="highlight">{restaurant.name}</span> has been <strong>approved</strong> on <strong>BiteQue</strong>.
          </p>
          <p>
            You now have access to your personalized merchant dashboard where you can manage listings, update menus, track orders, and more.
          </p>
          <a href="http://127.0.0.1:8000/merchant/login/" class="btn">Log in to Your Dashboard</a>
          <p class="footer">
            This is an automated email from BiteQue. If you have any questions, feel free to contact our support team.
          </p>
        </div>
      </body>
    </html>

    """

    email_data = {
        'from': {
            'email': settings.DEFAULT_FROM_EMAIL,
            'name': 'BiteQue'
        },
        'to': [
            {
                'email': restaurant.email
            }
        ],
        'subject': subject,
        'text': plain_text,
        'html': html_content
    }

    try:
        response = mailer.send(email_data)
        logger.info("Restaurant approval e-mail sent: %s", response)
    except Exception as exc:
        logger.warning("Restaurant approval e-mail to %s failed: %s", restaurant.email, exc)

def send_mailersend_reset_email(to_email, reset_link):
    url = "https://api.mailersend.com/v1/email"
    headers = {
        "Authorization": f"Bearer {settings.MAILERSEND_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "from": {
            "email": f"no-reply@{settings.MAILERSEND_DOMAIN}",
            "name": "Merchant App Support"
        },
        "to": [{"email": to_email}],
        "subject": "Reset your Merchant App password",
        "html": f"""
            <h3>Password Reset Request</h3>
            <p>Click the link below to reset your password:</p>
            <a href="{reset_link}">{reset_link}</a>
            <p>If you didn’t request this, you can ignore this email.</p>
        """
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("MailerSend password-reset e-mail to %s failed: %s", to_email, exc)
        return False