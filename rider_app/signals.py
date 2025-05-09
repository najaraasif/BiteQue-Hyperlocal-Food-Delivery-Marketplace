from django.utils import timezone
from django.db.models.signals import post_save, post_delete,pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from .models import OrderAssignment, Rider
from user_app.models import Order
from django.conf import settings
from mailersend import emails
from geopy.geocoders import Nominatim
from .mailersend_helper import send_mailersend_email

@receiver(post_save, sender=Rider)
def send_approval_email(sender, instance, created, **kwargs):
    if instance.is_approved and not created:
        mailer = emails.NewEmail(settings.MAILERSEND_API_KEY)

        mail_body = {
            "personalization": [  
                {
                    "email": instance.user.email,
                    "data": {
                        "rider_username": instance.user.username, 
                    }
                }
            ]
        }

        mail_from = {
            "email": settings.DEFAULT_FROM_EMAIL,
            "name": "BiteQue Rider Support"
        }

        recipients = [
            {
                "email": instance.user.email,
                "name": instance.user.username
            }
        ]

        mailer.set_mail_from(mail_from, mail_body)
        mailer.set_mail_to(recipients, mail_body)
        mailer.set_subject("Welcome to BiteQue, {{ rider_username }}!", mail_body) # Use double curly brackets in subject too
        mailer.set_template("jpzkmgq80m2g059v", mail_body)

        mailer.send(mail_body)

@receiver(post_save, sender=OrderAssignment)
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
            print(f"Signal: Order {order.id} status updated to 'delivered'.")

@receiver(post_save, sender=OrderAssignment)
def update_acceptance_stats(sender, instance, **kwargs):
    rider = instance.rider
    print(f"Signal: OrderAssignment status changed to {instance.status} for rider {rider.id}") 

    
    if instance.status in ['pending', 'accepted', 'rejected', 'delivered']: 
        rider.total_assignments = OrderAssignment.objects.filter(rider=rider).count()
        print(f"  Rider {rider.id} total_assignments updated to {rider.total_assignments}")

    if instance.status == 'accepted':
        rider


geolocator = Nominatim(user_agent="biteque_app")

@receiver(pre_save, sender=Order)
def geocode_address(sender, instance, **kwargs):
    print(f"Geocoding address: {instance.delivery_address}")
    if instance.delivery_address and (instance.dest_lat is None or instance.dest_lon is None):
        location = geolocator.geocode(instance.delivery_address)
        print(f"Geocode result: {location}")
        if location:
            instance.dest_lat = location.latitude
            instance.dest_lon = location.longitude
            print(f"Set coordinates: {location.latitude}, {location.longitude}")