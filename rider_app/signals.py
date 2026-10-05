import logging
import sys

import requests
from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils import timezone

from merchant_app.models import Restaurant
from .brevo_helper import send_brevo_email
from .models import OrderAssignment, Rider
from user_app.models import Order

logger = logging.getLogger(__name__)

GEOCODE_TIMEOUT_SECONDS = 5


@receiver(pre_save, sender=Rider)
def snapshot_rider_approved(sender, instance, **kwargs):
    # Remember the stored approval flag so post_save can detect a real
    # False -> True transition instead of re-sending on every save.
    instance._was_approved = False
    if instance.pk:
        instance._was_approved = Rider.objects.filter(
            pk=instance.pk
        ).values_list('is_approved', flat=True).first() or False


@receiver(post_save, sender=Rider)
def send_approval_email(sender, instance, created, **kwargs):
    if created or not instance.is_approved:
        return
    # Send only when this save actually approved the rider; repeated
    # saves (availability toggles, stats, admin edits) must not re-send.
    if getattr(instance, '_was_approved', False):
        return

    subject = f"Welcome to BiteQue, {instance.user.username}!"
    html_content = render_to_string('rider_app/approval_email.html', {
        'rider_username': instance.user.username,
    })

    send_brevo_email(
        subject=subject,
        html_content=html_content,
        recipient_email=instance.user.email,
        recipient_name=instance.user.username
    )


@receiver(post_save, sender=OrderAssignment)
def update_acceptance_stats(sender, instance, **kwargs):
    rider = instance.rider
    total = OrderAssignment.objects.filter(rider=rider).count()
    if rider.total_assignments != total:
        rider.total_assignments = total
        rider.save(update_fields=['total_assignments'])


def geocode_address_google(address):
    if 'test' in sys.argv:
        return None, None
    google_key = settings.GOOGLE_MAPS_API_KEY
    if not google_key or 'your-google' in google_key:
        return None, None

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={'address': address, 'key': google_key},
            timeout=GEOCODE_TIMEOUT_SECONDS,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Google geocoding request failed: %s", exc)
        return None, None

    if data.get('status') == 'OK' and data.get('results'):
        for result in data['results']:
            location_type = result['geometry'].get('location_type', '')
            if location_type == 'ROOFTOP':
                location = result['geometry']['location']
                return location['lat'], location['lng']

        # Fallback if no ROOFTOP match
        location = data['results'][0]['geometry']['location']
        return location['lat'], location['lng']

    logger.info("Google geocoding returned no result (status=%s)", data.get('status'))
    return None, None


@receiver(pre_save, sender=Order)
def geocode_order_address(sender, instance, **kwargs):
    if not instance.delivery_address or (instance.dest_lat is not None and instance.dest_lon is not None):
        return
    if instance.pk:
        try:
            previous_address = Order.objects.filter(pk=instance.pk).values_list('delivery_address', flat=True).first()
        except Order.DoesNotExist:
            previous_address = None
        if previous_address == instance.delivery_address:
            return

    lat, lon = geocode_address_google(instance.delivery_address)
    if lat and lon:
        instance.dest_lat = lat
        instance.dest_lon = lon


# Restaurant signal
@receiver(pre_save, sender=Restaurant)
def geocode_restaurant_address(sender, instance, **kwargs):
    if instance.address and (instance.lat is None or instance.lon is None):
        lat, lon = geocode_address_google(instance.address)
        if lat and lon:
            instance.lat = lat
            instance.lon = lon


#DELIVERY PIN LOGIC
@receiver(post_save, sender=OrderAssignment)
def handle_order_assignment_changes(sender, instance, created, **kwargs):
    order = instance.order

    if instance.status == 'accepted':
        if order.status != 'out_for_delivery':
            order.status = 'out_for_delivery'
            order.generate_delivery_pin()
            order.save()
            logger.info("Order %s accepted; status set to out_for_delivery.", order.id)
        elif not order.delivery_pin:
            order.generate_delivery_pin()
            order.save()

        OrderAssignment.objects.filter(
            order=order,
            status='pending'
        ).exclude(pk=instance.pk).update(status='rejected')

    elif instance.status == 'delivered':
        if order.status != 'delivered':
            order.status = 'delivered'
            order.clear_delivery_pin()
            order.save()
            logger.info("Order %s marked delivered.", order.id)


@receiver(pre_save, sender=OrderAssignment)
def calculate_acceptance_score(sender, instance, **kwargs):
    if instance.status == 'accepted' and not instance.response_time:
        # Calculate response time
        instance.response_time = timezone.now() - instance.assigned_at
        total_seconds = instance.response_time.total_seconds()

        # Calculate score based on response time
        if total_seconds <= 60:  # 0-1 min
            score = 100
        elif total_seconds <= 120:  # 1-2 min
            score = 90
        elif total_seconds <= 180:  # 2-3 min
            score = 80
        elif total_seconds <= 240:  # 3-4 min
            score = 70
        elif total_seconds <= 300:  # 4-5 min
            score = 50
        else:  # 5+ min
            score = 0

        instance.acceptance_score = score
