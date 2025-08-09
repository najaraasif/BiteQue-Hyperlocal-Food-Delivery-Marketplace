from django.utils import timezone
from django.db.models.signals import post_save, post_delete,pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
import requests

from merchant_app.models import Restaurant
from .models import OrderAssignment, Rider
from user_app.models import Order
from django.conf import settings
from mailersend import emails
from geopy.geocoders import Nominatim


# signals.py
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.template.loader import render_to_string
from .brevo_helper import send_brevo_email
from .models import Rider

@receiver(post_save, sender=Rider)
def send_approval_email(sender, instance, created, **kwargs):
    if instance.is_approved and not created:
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


"""@receiver(post_save, sender=OrderAssignment)
def update_order_status_and_reject_others(sender, instance, created, **kwargs):
    if instance.status == 'accepted': 
        order = instance.order
        if order.status != 'out_for_delivery':
            order.status = 'out_for_delivery'
            order.save()
            print(f"Signal: Order {order.id} status updated to 'out_for_delivery'.")

        other_assignments = OrderAssignment.objects.filter(
            order=instance.order,
            status='pending' 
        ).exclude(pk=instance.pk)
        if other_assignments.exists():
            updated_count = other_assignments.update(status='rejected')
            print(f"Signal: Rejected {updated_count} other pending assignments for order {instance.order.id}.")

    elif instance.status == 'delivered':
        order = instance.order
        if order.status != 'delivered':
            order.status = 'delivered'
            order.save()
            print(f"Signal: Order {order.id} status updated to 'delivered'.")"""

@receiver(post_save, sender=OrderAssignment)
def update_acceptance_stats(sender, instance, **kwargs):
    rider = instance.rider
    print(f"Signal: OrderAssignment status changed to {instance.status} for rider {rider.id}") 

    
    if instance.status in ['pending', 'accepted', 'rejected', 'delivered']: 
        rider.total_assignments = OrderAssignment.objects.filter(rider=rider).count()
        print(f"  Rider {rider.id} total_assignments updated to {rider.total_assignments}")

    if instance.status == 'accepted':
        rider


GOOGLE_API_KEY = '***REMOVED***'


def geocode_address_google(address):
    print(f"Geocoding address using Google Maps: {address}")
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        'address': address,
        'key': GOOGLE_API_KEY
    }
    response = requests.get(base_url, params=params)
    data = response.json()

    if data['status'] == 'OK' and data['results']:
        for result in data['results']:
            location_type = result['geometry'].get('location_type', '')
            if location_type == 'ROOFTOP':
                location = result['geometry']['location']
                lat = location['lat']
                lon = location['lng']
                print(f"[ROOFTOP] Google Geocode result: lat={lat}, lon={lon}")
                return lat, lon
        print("No ROOFTOP match found, falling back to first result.")

        # Fallback if no ROOFTOP match
        location = data['results'][0]['geometry']['location']
        lat = location['lat']
        lon = location['lng']
        print(f"[Fallback] Google Geocode result: lat={lat}, lon={lon}")
        return lat, lon
    else:
        print(f"Failed to geocode: {data}")
        return None, None


@receiver(pre_save, sender=Order)
def geocode_order_address(sender, instance, **kwargs):
    if (instance.delivery_address and 
        (instance.dest_lat is None or instance.dest_lon is None) and
        (not instance.pk or  
         instance.delivery_address != Order.objects.get(pk=instance.pk).delivery_address)):
        
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
    print(f"DEBUG SIGNAL: OrderAssignment {instance.id} saved. Status: {instance.status}. Order ID: {order.id}") # Debug

    if instance.status == 'accepted':
        print(f"DEBUG SIGNAL: OrderAssignment accepted. Current order status: {order.status}") # Debug
        if order.status != 'out_for_delivery':
            order.status = 'out_for_delivery'
            order.generate_delivery_pin() #
            order.save() 
            print(f"DEBUG SIGNAL: Order {order.id} status set to 'out_for_delivery'. PIN: {order.delivery_pin}")
        else:
            
            if not order.delivery_pin:
                order.generate_delivery_pin()
                order.save()
                print(f"DEBUG SIGNAL: Order {order.id} was already 'out_for_delivery', generated missing PIN: {order.delivery_pin}")


        
        other_assignments = OrderAssignment.objects.filter(
            order=order,
            status='pending'
        ).exclude(pk=instance.pk)
        if other_assignments.exists():
            updated_count = other_assignments.update(status='rejected')
            print(f"DEBUG SIGNAL: Rejected {updated_count} other pending assignments for order {order.id}.")

    elif instance.status == 'delivered':
        print(f"DEBUG SIGNAL: OrderAssignment delivered. Current order status: {order.status}")
        if order.status != 'delivered':
            order.status = 'delivered'
            order.clear_delivery_pin() 
            order.save() 
            print(f"DEBUG SIGNAL: Order {order.id} status set to 'delivered'. PIN cleared.")


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