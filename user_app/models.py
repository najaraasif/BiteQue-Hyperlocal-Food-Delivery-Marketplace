from datetime import timezone
from django.db import models
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.apps import apps
from django.db.models.signals import m2m_changed
from django.dispatch import receiver


class Order(models.Model):
    restaurant = models.ForeignKey('merchant_app.Restaurant', on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=100)
    customer_contact = models.CharField(max_length=15)
    order_address = models.TextField()
    menu_items = models.ManyToManyField('merchant_app.RestaurantMenu', related_name='orders')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('ready', 'Ready for Delivery'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    def save(self, *args, **kwargs):
        created = not self.pk  # Check if this is a new order
        super().save(*args, **kwargs)
        if self.status == 'ready' and not created:  # Skip on initial creation
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

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

    
class userLogin(models.Model):
    username = models.CharField(unique=True, default='shakir', max_length=50)
    password = models.CharField(unique=True, default='Shakir@2002', max_length=50)

    def __str__(self):
        return self.username
    


