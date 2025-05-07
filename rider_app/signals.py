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




import logging


logger = logging.getLogger(__name__)

@receiver(post_save, sender=OrderAssignment)
def update_acceptance_stats(sender, instance, created, **kwargs):
    logger.info(f"Signal triggered for OrderAssignment {instance.id}, status: {instance.status}")
    
    if instance.status in ['ACCEPTED', 'REJECTED']:
        rider = instance.rider
        logger.info(f"Processing rider {rider.id}, current stats - accepted: {rider.accepted_assignments}, total: {rider.total_assignments}")
        
        if not created:
            try:
                old_status = OrderAssignment.objects.get(pk=instance.pk).status
                logger.info(f"Status changed from {old_status} to {instance.status}")
                
                if old_status == 'PENDING' and instance.status == 'ACCEPTED':
                    rider.accepted_assignments += 1
                    rider.total_assignments += 1
                    logger.info("Incremented both counters")
                elif old_status == 'PENDING' and instance.status == 'REJECTED':
                    rider.total_assignments += 1
                    logger.info("Incremented total assignments")
            except OrderAssignment.DoesNotExist:
                logger.error("Couldn't find previous assignment state")
        else:
            if instance.status == 'ACCEPTED':
                rider.accepted_assignments += 1
                rider.total_assignments += 1
                logger.info("New accepted assignment - incremented both")
            elif instance.status == 'REJECTED':
                rider.total_assignments += 1
                logger.info("New rejected assignment - incremented total")
        
        rider.acceptance_rate = rider.get_acceptance_rate()
        rider.save()
        logger.info(f"Updated stats - accepted: {rider.accepted_assignments}, total: {rider.total_assignments}, rate: {rider.acceptance_rate}%")