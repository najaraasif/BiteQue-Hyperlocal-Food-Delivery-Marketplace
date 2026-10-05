import logging
import random
import secrets
import string
import threading
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from user_app.utils import send_sms, send_whatsapp

logger = logging.getLogger(__name__)


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    restaurant = models.ForeignKey('merchant_app.Restaurant', on_delete=models.CASCADE, related_name='orders')
    customer_name = models.CharField(max_length=100)
    customer_contact = models.CharField(max_length=15)
    landmark = models.TextField(max_length=100)
    menu_items = models.ManyToManyField('merchant_app.RestaurantMenu', through='OrderMenuItem', related_name='orders')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    delivery_address = models.CharField(max_length=512)
    special_instructions = models.CharField(max_length=150)
    dest_lat = models.DecimalField(max_digits=9, decimal_places=7, blank=True, null=True)
    dest_lon = models.DecimalField(max_digits=9, decimal_places=7, blank=True, null=True)
    distance_earning = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_earning = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_pin = models.CharField(max_length=6, blank=True, null=True)
    packaging_charges = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('10.00'))
    item_gst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_pin_generated_at = models.DateTimeField(null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=100, blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    final_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready for Delivery'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def calculate_total(self):
        items = list(self.order_items.all())
        if items:
            return sum(item.price * item.quantity for item in items)
        if hasattr(self, '_cart_quantities'):
            return sum(item.price * self._cart_quantities.get(str(item.id), 1) for item in self.menu_items.all())
        return Decimal('0.00')

    @property
    def overall_sum(self):
        return (self.total + self.item_gst + self.packaging_charges + self.distance_earning).quantize(Decimal('0.00'))

    def send_status_update(self):
        """Send WhatsApp/SMS notification for order status changes."""
        if not self.customer_contact:
            return

        # Normalize phone number to 10-digit +91 format
        phone_number = ''.join(filter(str.isdigit, self.customer_contact))[-10:]
        full_number = '91' + phone_number

        status_messages = {
            'confirmed': (
                f"✅ Order Confirmed!\n"
                f"Order #{self.id} from {self.restaurant.name} has been confirmed.\n"
                f"Estimated delivery time: 30-45 minutes."
            ),
            'ready': (
                f"🍔 Order Ready!\n"
                f"Your order #{self.id} is ready for delivery.\n"
                f"Rider will arrive shortly to pick it up."
            ),
            'out_for_delivery': (
                f"🚚 Order On The Way!\n"
                f"Your order #{self.id} is out for delivery.\n"
                f"Rider: {self.assignment.rider.user.first_name if hasattr(self, 'assignment') else 'Unknown'}\n"
                f"Contact: {self.assignment.rider.phone if hasattr(self, 'assignment') else 'N/A'}"
            ),
            'delivered': (
                f"🎉 Order Delivered!\n"
                f"Your order #{self.id} has been delivered.\n"
                f"Enjoy your meal! Please share your feedback."
            )
        }

        if self.status in status_messages:
            message = status_messages[self.status]

            def notify():
                try:
                    # Try WhatsApp first
                    if not send_whatsapp(full_number, message):
                        # Fallback to SMS via Fast2SMS
                        send_sms(phone_number, message)
                except Exception:
                    logger.exception("Failed to send status update for order %s", self.pk)

            threading.Thread(target=notify, daemon=True).start()

    def save(self, *args, **kwargs):
        # Recalculate total
        if hasattr(self, '_cart_quantities') and self.menu_items.exists():
            self.total = self.calculate_total()
        elif self.pk and self.menu_items.exists():
            self.total = self.calculate_total()

        # Update final total
        self.final_total = (
            self.total + self.item_gst + self.packaging_charges + self.distance_earning
        ).quantize(Decimal('0.00'))

        # Detect status change
        prev_status = None
        if self.pk:
            prev_status = Order.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        super().save(*args, **kwargs)

        # Trigger notification if status changed
        if prev_status != self.status:
            self.send_status_update()

    @property
    def status_index(self):
        status_order = ['pending', 'confirmed', 'ready', 'out_for_delivery', 'delivered']
        try:
            return status_order.index(self.status) + 1
        except ValueError:
            return 0

    @property
    def status_color(self):
        return {
            'pending': 'red',
            'confirmed': 'blue',
            'ready': 'yellow',
            'out_for_delivery': 'orange',
            'delivered': 'green',
        }.get(self.status, 'grey')

    def generate_delivery_pin(self, length=4):
        self.delivery_pin = ''.join(secrets.choice(string.digits) for _ in range(length))
        self.delivery_pin_generated_at = timezone.now()
        return self.delivery_pin

    def clear_delivery_pin(self):
        self.delivery_pin = None
        self.delivery_pin_generated_at = None

    def is_delivery_pin_valid(self, entered_pin):
        if not self.delivery_pin or not self.delivery_pin_generated_at:
            return False
        return self.delivery_pin == entered_pin

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"



        
class OrderMenuItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    menu_item = models.ForeignKey('merchant_app.RestaurantMenu', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('order', 'menu_item')
   









class CustomerFeedback(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    restaurant = models.ForeignKey('merchant_app.Restaurant', on_delete=models.CASCADE)
    customer = models.ForeignKey(User, on_delete=models.CASCADE)

    rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        null=True,
        blank=True,
        help_text="Main overall rating given by the customer."
    )

    item_quality = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        null=True,
        blank=True,
        help_text="Quality of the food items"
    )
    delivery_experience = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        null=True,
        blank=True,
        help_text="Experience with the delivery process"
    )
    restaurant_rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        null=True,
        blank=True,
        help_text="Rating for the restaurant overall"
    )
    rider_rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        null=True,
        blank=True,
        help_text="Rating for the delivery rider"
    )

    item_ratings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dictionary of menu_item_id: rating"
    )

    comments = models.TextField(blank=True, null=True, help_text="General comments")
    additional_comments = models.TextField(blank=True, null=True, help_text="Extra feedback")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.username} - Order #{self.order.id}"

    @property
    def overall_rating(self):
        ratings = [
            self.rating,
            self.item_quality,
            self.delivery_experience,
            self.restaurant_rating,
            self.rider_rating,
            *self.item_ratings.values()
        ]
        valid_ratings = [r for r in ratings if r is not None]
        return round(sum(valid_ratings) / len(valid_ratings), 2) if valid_ratings else None


    
class MerchantNotification(models.Model):
    merchant = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)



def generate_ticket_id():
    length = 7
    chars = string.digits  
    while True:
        new_id = ''.join(random.choices(chars, k=length))
        if not UserSupportTicket.objects.filter(ticket_id=new_id).exists():
            return new_id
        


class UserSupportTicket(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('closed', 'Closed'),
    ]

    CATEGORY_CHOICES = [
        ('technical', 'Technical Issue'),
        ('billing', 'Billing'),
        ('general', 'General Inquiry'),
        ('other', 'Other'),
    ]

    ticket_id = models.CharField(max_length=6, unique=True, editable=False, default=generate_ticket_id)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_tickets')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ticket_id} - {self.subject} ({self.get_status_display()})"


class UserSupportMessage(models.Model):
    ticket = models.ForeignKey(UserSupportTicket, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    image = models.ImageField(upload_to='user_support_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message by {self.sender} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"
#PROFILE MODEL
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    whatsapp_consent = models.BooleanField(
        default=False,
        help_text="I agree to receive order updates via WhatsApp"
    )
    
    def __str__(self):
        return f"{self.user.username}'s Profile"

    
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'userprofile' not in update_fields:
        # Field-limited saves (e.g. last_login updates) must not
        # touch the profile row.
        return
    profile, _ = UserProfile.objects.get_or_create(user=instance)
    profile.save()