from django.db import models
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib.auth.models import User
from user_app.models import Order
from decimal import Decimal



class merchantRegistration(models.Model):
    username = models.OneToOneField(User, max_length=50, unique=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    number = models.DecimalField(max_length=50,max_digits=15, decimal_places=1)
    is_approved = models.BooleanField(default=False)


    

class Restaurant(models.Model):
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    contact_number = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=50)
    image = models.ImageField(upload_to='restaurantImages/', null=True, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    gstin_number = models.CharField(max_length=20, blank=True)
    fssai_number = models.CharField(max_length=20, blank=True)
    is_approved = models.BooleanField(default=False)
    is_available = models.BooleanField(default=False)
    lat = models.DecimalField(max_digits=9, decimal_places=7, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=7, null=True, blank=True)
    player_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.city}"
    
class SizeCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
class RestaurantMenu(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menus')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=130)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='menu_images/', null=True, blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    available = models.BooleanField(default=True)
    prep_time = models.PositiveIntegerField()
    sizes_categories = models.ForeignKey(SizeCategory,on_delete=models.CASCADE, related_name='menu_items')  # 👈 new field
    VEG_NONVEG_CHOICES = [
        ('veg', 'Vegetarian'),
        ('nonveg', 'Non-Vegetarian'),
    ]
    veg_or_nonveg = models.CharField(
        max_length=10,
        choices=VEG_NONVEG_CHOICES,
        null=True,
        blank=True,
        verbose_name="Veg / Non-Veg"
    )

    def __str__(self):
        return self.name
    def __str__(self):
        return f"{self.name} - {self.restaurant.name}"



class BankAccount(models.Model):
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100)
    account_holder_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50, unique=True)
    ifsc_code = models.CharField(max_length=20)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)


    def save(self, *args, **kwargs):
        # If this is being marked as primary, unmark all others
        if self.is_primary:
            BankAccount.objects.filter(merchant=self.merchant, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"



class MerchantPayment(models.Model):
    merchant = models.ForeignKey(User, on_delete=models.CASCADE)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=50, default='Bank Transfer')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    account = models.CharField(max_length=100, blank=True, null=True)
    payment_screenshot = models.ImageField(upload_to='payment_screenshots/', blank=True, null=True)

    def __str__(self):
        return f"{self.restaurant.name} - ₹{self.amount_paid} on {self.payment_date.strftime('%Y-%m-%d')}"
    


class MerchantEarning(models.Model):
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='earnings')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='earnings')

    net_sales = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    weekly_sales = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount_pending = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Earnings for {self.restaurant.name} - {self.merchant.username}"

    class Meta:
        verbose_name = "Merchant Earning"
        verbose_name_plural = "Merchant Earnings"
        unique_together = ('merchant', 'restaurant')

class Review(models.Model):
    restaurant = models.ForeignKey('Restaurant', on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.user.username} for {self.restaurant.name}"
    
from django.db import models
from django.contrib.auth.models import User
import uuid
import string
import random
def generate_ticket_id():
    length = 7
    chars = string.digits  
    while True:
        new_id = ''.join(random.choices(chars, k=length))
        if not Ticket.objects.filter(ticket_id=new_id).exists():
            return new_id
        
class Ticket(models.Model):
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
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ticket_id} - {self.subject} ({self.get_status_display()})"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    image = models.ImageField(upload_to='support_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message by {self.sender} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"