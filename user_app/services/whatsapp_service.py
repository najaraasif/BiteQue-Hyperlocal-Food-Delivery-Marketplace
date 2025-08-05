# user_app/services/whatsapp_service.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def send_whatsapp_message(template_name, recipient, parameters):
    url = f"https://graph.facebook.com/v18.0/{os.getenv('WHATSAPP_PHONE_ID')}/messages"
    headers = {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": param} for param in parameters
                ]
            }]
        }
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json()