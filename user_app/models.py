from datetime import timezone
import secrets
import string
from django.db import models
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.apps import apps
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from decimal import Decimal
from venv import logger
from rider_app.utils import geocode_address



class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    restaurant = models.ForeignKey('merchant_app.Restaurant', on_delete=models.CASCADE, related_name='orders')
    customer_name = models.CharField(max_length=100)
    customer_contact = models.CharField(max_length=15)
    landmark = models.TextField(max_length=100)
    menu_items = models.ManyToManyField(
        'merchant_app.RestaurantMenu',
        through='OrderMenuItem',
        related_name='orders'
    )
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
        if hasattr(self, '_cart_quantities'):
            return sum(item.price * self._cart_quantities.get(str(item.id), 1) 
                   for item in self.menu_items.all())
        # Fallback to simple sum
        return sum(item.price for item in self.menu_items.all())

    @property
    def overall_sum(self):
        return (self.total + self.item_gst + self.packaging_charges + self.distance_earning).quantize(Decimal('0.00'))

    def save(self, *args, **kwargs):
    # Recalculate total using cart quantities if available (e.g., during checkout)
        if hasattr(self, '_cart_quantities') and self.menu_items.exists():
            self.total = self.calculate_total()
        elif self.pk and self.menu_items.exists():
            self.total = self.calculate_total()

        # Calculate final total
        self.final_total = (
            self.total + self.item_gst + self.packaging_charges + self.distance_earning
        ).quantize(Decimal('0.00'))

        # Check if status has changed
        prev_status = None
        if self.pk:
            prev_status = Order.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        super().save(*args, **kwargs)

        # Auto-assign delivery task if status changed to 'ready'
        if self.status == 'ready' and prev_status != 'ready':
            self.create_assignments()


    def create_assignments(self):
        # Placeholder for assignment logic
        print(f"DEBUG: Assignment logic triggered for Order #{self.id}")

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
        print(f"DEBUG: Generated PIN {self.delivery_pin} for order {self.id}")
        return self.delivery_pin

    def clear_delivery_pin(self):
        self.delivery_pin = None
        self.delivery_pin_generated_at = None
        print(f"DEBUG: Cleared PIN for order {self.id}")

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
   

class userRegistration(models.Model):
    username = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=30, default=1)
    number = models.CharField(max_length=10, default=0)
    email = models.EmailField(max_length=20)
    address = models.TextField(max_length=50)
    password = models.TextField(max_length=8)
    retypePassword =models.TextField(max_length=8)

    def __str__(self):
        return f"Registration successful by - {self.name}"



class CustomerFeedback(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    restaurant = models.ForeignKey('merchant_app.Restaurant', on_delete=models.CASCADE)
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.username} - Order #{self.order.id} - {self.rating}★"

    
class MerchantNotification(models.Model):
    merchant = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)