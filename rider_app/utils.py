import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def geocode_address(address):

    try:
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
    
import math

"""def calculate_distance(lat1, lon1, lat2, lon2):
   
    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    radius_of_earth = 6371  
    return radius_of_earth * c """


def get_osrm_distance(origin_lat, origin_lon, dest_lat, dest_lon):
    OSRM_SERVER_URL = settings.OSRM_SERVER_URL  # Ensure this is configured
    url = f"{OSRM_SERVER_URL}/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}?overview=false"
    
    response = requests.get(url)
    data = response.json()
    
    if data.get('code') != 'Ok':
        raise ValueError("OSRM route calculation failed")
    
    distance_meters = data['routes'][0]['distance']
    distance_km = distance_meters / 1000  # Convert meters to kilometers
    return round(distance_km, 2)