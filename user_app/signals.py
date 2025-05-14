from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from rider_app.models import Rider, OrderAssignment
from geopy.geocoders import Nominatim



@receiver(post_save, sender=Order)
def create_assignments(sender, instance, **kwargs):
    if instance.status == 'ready':
        riders = Rider.objects.filter(is_available=True, is_approved=True)
        for rider in riders:
            OrderAssignment.objects.get_or_create(
                rider=rider,
                order=instance,
                defaults={'status': 'pending'}
            )