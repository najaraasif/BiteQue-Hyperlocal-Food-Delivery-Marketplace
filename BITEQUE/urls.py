"""
URL configuration for BITEQUE project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import Http404
from django.urls import path, include
from user_app import urls
from rider_app import urls
from merchant_app import urls
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as serve_media

PUBLIC_MEDIA_PREFIXES = (
    'restaurantImages/',
    'menu_images/',
    'images/',
    'static/',
)

AUTH_MEDIA_PREFIXES = (
    'riders/profiles/',
    'avatars/',
)


def _owns_private_media(user, path):
    from django.db.models import Q
    from rider_app.models import Rider
    from merchant_app.models import MerchantPayment, TicketMessage
    from user_app.models import UserSupportMessage, UserProfile

    if Rider.objects.filter(user=user).filter(
        Q(profile_photo=path) | Q(aadhar_front=path)
        | Q(aadhar_back=path) | Q(license_copy=path)
    ).exists():
        return True
    if MerchantPayment.objects.filter(merchant=user, payment_screenshot=path).exists():
        return True
    if TicketMessage.objects.filter(sender=user, image=path).exists():
        return True
    if UserSupportMessage.objects.filter(sender=user, image=path).exists():
        return True
    if UserProfile.objects.filter(user=user, avatar=path).exists():
        return True
    return False


def protected_media(request, path):
    parts = path.replace('\\', '/').split('/')
    if path.startswith('/') or '..' in parts:
        raise Http404
    if settings.DEBUG:
        return serve_media(request, path, document_root=settings.MEDIA_ROOT)
    if any(path.startswith(p) for p in PUBLIC_MEDIA_PREFIXES):
        return serve_media(request, path, document_root=settings.MEDIA_ROOT)
    if not request.user.is_authenticated:
        raise Http404
    if request.user.is_staff:
        return serve_media(request, path, document_root=settings.MEDIA_ROOT)
    if any(path.startswith(p) for p in AUTH_MEDIA_PREFIXES):
        return serve_media(request, path, document_root=settings.MEDIA_ROOT)
    if _owns_private_media(request.user, path):
        return serve_media(request, path, document_root=settings.MEDIA_ROOT)
    raise Http404


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('user_app.urls')),
    path('', include('rider_app.urls')),
    path('', include('merchant_app.urls')),
    path('media/<path:path>', protected_media),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
