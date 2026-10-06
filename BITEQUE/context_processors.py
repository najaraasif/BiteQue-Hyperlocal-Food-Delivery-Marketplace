from django.conf import settings


def external_api_keys(request):
    return {
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'site_url': settings.SITE_URL,
    }
