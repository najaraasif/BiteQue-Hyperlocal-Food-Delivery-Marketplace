from django.db import models
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib.auth.models import User
from user_app.models import Order


class merchantRegistration(models.Model):
    username = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    number = models.DecimalField(max_length=50,max_digits=15, decimal_places=1)
    email = models.EmailField(max_length=100)
    password = models.CharField(max_length=50, unique=True)   
    retypePassword = models.CharField(max_length=50)


    def __str__(self):
        return self.username
    

class Restaurant(models.Model):
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    contact_number = models.CharField(max_length=15)
    area = models.CharField(max_length=100, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=50)
    pan_number = models.CharField(max_length=20, blank=True)
    gstin_number = models.CharField(max_length=20, blank=True)
    fssai_number = models.CharField(max_length=20, blank=True)
    is_approved = models.BooleanField(default=False)
    is_available = models.BooleanField(default=False)


    def __str__(self):
        return f"{self.name} - {self.city}"
    

class RestaurantMenu(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menus')
    name = models.CharField(max_length=100)
    size_category = models.CharField(max_length=130)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='menu_images/', null=True, blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    available = models.BooleanField(default=True)
    prep_time = models.PositiveIntegerField()

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