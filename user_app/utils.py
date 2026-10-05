# sms_utils.py
import requests
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15

def send_sms(phone, message):
    """
    Send SMS using Fast2SMS
    Phone format: 10 digits without country code
    """
    try:
        headers = {
            'Authorization': settings.FAST2SMS_API_KEY,
            'Content-Type': "application/x-www-form-urlencoded",
            'Cache-Control': "no-cache",
        }
        
        payload = {
            "sender_id": settings.WHATSAPP_SENDER_ID,
            "message": message,
            "language": "english",
            "route": "v3",
            "numbers": phone,
        }
        
        response = requests.post(
            settings.FAST2SMS_URL,
            data=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        
        if response.status_code == 200:
            logger.info(f"SMS sent to {phone}. Response: {response.json()}")
            return True
        else:
            logger.error(f"SMS failed to {phone}. Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Exception sending SMS: {str(e)}")
        return False

def send_whatsapp(phone, message):
    """
    Send WhatsApp message using Fast2SMS
    Phone format: 10 digits without country code
    """
    try:
        headers = {
            'Authorization': settings.FAST2SMS_API_KEY,
            'Content-Type': "application/json",
        }
        
        payload = {
            "route": "whatsapp",
            "sender_id": settings.WHATSAPP_SENDER_ID,
            "message": message,
            "language": "english",
            "numbers": phone,
        }
        
        response = requests.post(
            "https://www.fast2sms.com/dev/whatsapp",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        
        if response.status_code == 200:
            logger.info(f"WhatsApp sent to {phone}. Response: {response.json()}")
            return True
        else:
            logger.error(f"WhatsApp failed to {phone}. Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Exception sending WhatsApp: {str(e)}")
        return False