import requests
import math
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def geocode_address(address):
    """Geocode an address using OpenStreetMap Nominatim API."""
    try:
        headers = {'User-Agent': f'BiteQueApp/1.0 ({settings.SITE_URL})'}
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': address,
                'format': 'json',
                'limit': 1
            },
            headers=headers,
            timeout=10
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

def calculate_distance(lat1, lon1, lat2, lon2):
    """Fallback distance calculation using Haversine formula."""
    R = 6371  # Earth radius in kilometers
    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(R * c, 2)

def calculate_osrm_distance(lat1, lon1, lat2, lon2):
    """Calculate road distance using OSRM with Haversine fallback."""
    endpoint = f"{settings.OSRM_SERVER_URL}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    
    try:
        response = requests.get(endpoint, timeout=10)
        data = response.json()
        
        if data.get('code') == 'Ok' and data['routes']:
            distance_km = data['routes'][0]['distance'] / 1000  # Convert to km
            return round(distance_km, 2)
        else:
            logger.warning(f"OSRM failed response: {data}")
    except Exception as e:
        logger.error(f"OSRM distance calculation failed: {str(e)}")

    # Fallback to Haversine if OSRM fails
    return calculate_distance(lat1, lon1, lat2, lon2)
