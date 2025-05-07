import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def geocode_address(address):
    """
    Convert a physical address to latitude/longitude using Nominatim
    Returns: (latitude, longitude) or (None, None) if failed
    """
    try:
        # Nominatim requires a user agent
        headers = {'User-Agent': 'BiteQueApp/1.0 (contact@yourdomain.com)'}
        
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': address,
                'format': 'json',
                'limit': 1
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
                
        
        logger.warning(f"Geocoding failed for address: {address}")
        return None, None
        
    except Exception as e:
        logger.error(f"Geocoding error: {str(e)}")
        return None, None
    
    