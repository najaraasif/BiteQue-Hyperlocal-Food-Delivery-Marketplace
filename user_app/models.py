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
    order_address = models.TextField()
    menu_items = models.ManyToManyField('merchant_app.RestaurantMenu', related_name='orders')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    delivery_address = models.CharField(max_length=512)
    dest_lat = models.DecimalField(
        max_digits=9, decimal_places=7, blank=True, null=True,
        help_text="Geocoded latitude of delivery address"
    )
    dest_lon = models.DecimalField(
        max_digits=9, decimal_places=7, blank=True, null=True,
        help_text="Geocoded longitude of delivery address"
    )
    
    distance_earning = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission = models.DecimalField(max_digits=10, decimal_places=2,default=0)
    total_earning = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal('0.00'))
    delivery_pin = models.CharField(max_length=6, blank=True, null=True)
    delivery_pin_generated_at = models.DateTimeField(null=True, blank=True)

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready for Delivery'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    def save(self, *args, **kwargs):
        created = not self.pk  
        super().save(*args, **kwargs)
        if self.status == 'ready' and not created:  
            self.create_assignments()
            
    def calculate_total(self):
        return sum(item.price for item in self.menu_items.all())  # Sum up the price of all items
    
    def save(self, *args, **kwargs):
        # First save to create an ID
        super().save(*args, **kwargs)
        
        # Now that the object has an ID, handle many-to-many relationships
        if self.menu_items.exists():  # If menu items are selected
            total_price = self.calculate_total()  # Calculate the total
            self.total = total_price  # Set the total price

            # Save the total field
            super().save(update_fields=['total'])

    @property
    def status_index(self):
        status_order = ['pending','confirmed','ready','out_for_delivery','delivered']
        try:
            return status_order.index(self.status)+1
        except ValueError:
            return 0
        
    @property
    def status_color(self):
        status_colors = {'pending':'red',
                         'confirmed':'blue',
                         'ready':'yellow',
                         'out_for_delivery':'orange',
                         'delivered':'green'
                          }
        return status_colors.get(self.status,'grey')
    

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"
    

    def generate_delivery_pin(self, length=4):
        
        self.delivery_pin = "".join(secrets.choice(string.digits) for _ in range(length))
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
    

#Homepage --

#user registration model()
#profile dashboard model()
#order model ()
#login and logout model()
#setting model (profile pic, Name, addresses, phone number, email()
#Address model()
#Order status  model()
#check out model()
#cart model()

#Menus 
#Payment integration