from django.utils import timezone
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.mail import send_mail
from .models import OrderAssignment, Rider
from user_app.models import Order
from django.conf import settings

from .mailersend_helper import send_mailersend_email

@receiver(post_save, sender=Rider)
def send_approval_email(sender, instance, created, **kwargs):
    if instance.is_approved and not created:
        subject = "Your Rider Account Has Been Approved"
        text_content = f"""Hello {instance.user.username},
        
        Your BiteQue rider account has been approved!
        You can now login at Website>
        
        Thank you,
        BiteQue Team"""
        
        html_content = f"""
        <html>
            <body>
                <h1>Welcome to BiteQue, {instance.user.username}!</h1>
                <p>Your rider account has been approved.</p>
                <a href="shakir.com">Click here to login</a>
                <p>Thank you,<br>BiteQue Team</p>
            </body>
        </html>"""
        
        send_mailersend_email(
            instance.user.email,
            subject,
            text_content,
            html_content
        )

@receiver(post_save, sender=OrderAssignment)
def update_order_status(sender, instance, **kwargs):
    if instance.status == 'ACCEPTED':
        instance.order.status = 'out_for_delivery'
        instance.order.save()
    elif instance.status == 'DELIVERED':
        instance.order.status = 'delivered' 
        instance.order.save()




@receiver(post_save, sender=OrderAssignment)
def update_acceptance_stats(sender, instance, **kwargs):
    rider = instance.rider

    # Log the status and rider
    print(f"Signal: OrderAssignment status changed to {instance.status} for rider {rider.id}")

    # Increment total assignments for every new assignment or update
    if instance.status in ['PENDING', 'ACCEPTED', 'REJECTED', 'DELIVERED']:
        rider.total_assignments = OrderAssignment.objects.filter(rider=rider).count()
        print(f"  Rider {rider.id} total_assignments updated to {rider.total_assignments}")

    if instance.status == 'ACCEPTED':
        rider.accepted_assignments = OrderAssignment.objects.filter(rider=rider, status='ACCEPTED').count()
        print(f"  Rider {rider.id} accepted_assignments updated to {rider.accepted_assignments}")

    rider.save()
    print(f"  Rider {rider.id} saved.")