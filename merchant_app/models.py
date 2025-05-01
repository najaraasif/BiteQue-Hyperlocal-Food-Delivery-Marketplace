from django.db import models
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib.auth.models import User



class merchantRegistration(models.Model):
    username = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    number = models.DecimalField(max_length=50,max_digits=15, decimal_places=1)
    email = models.EmailField(max_length=100)
    password = models.CharField(max_length=50, unique=True)   
    retypePassword = models.CharField(max_length=50)


    def __str__(self):
        return self.username
    

class addRestaurant(models.Model):
    name = models.CharField(max_length=100)
    owner_name = models.CharField(max_length=100)
    email = models.EmailField()
    contact_number = models.DecimalField(max_length=15,max_digits=16, decimal_places=1)
    restaurantAddress = models.TextField()
    city = models.CharField(max_length=50)
    pan_number = models.CharField(max_length=20, blank=True)
    gstin_number = models.DecimalField(max_length=20,max_digits=15, decimal_places=1, blank=True)
    fssai_number = models.DecimalField(max_length=20,max_digits=15, decimal_places=1, blank=True)
    is_approved = models.BooleanField()

    def __str__(self):
        return self.name    
    
    # DASHBOARD MODELS

class MerchantProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_online = models.BooleanField(default=False)
    business_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    address = models.TextField()

    def __str__(self):
        return self.business_name
    
class InventoryItem(models.Model):
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.quantity})"

class Order(models.Model):
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=100)
    items = models.TextField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=[('Pending', 'Pending'), ('Completed', 'Completed')])

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

class Payment(models.Model):
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=100)

    def __str__(self):
        return f"Payment: {self.amount} on {self.transaction_date}"
