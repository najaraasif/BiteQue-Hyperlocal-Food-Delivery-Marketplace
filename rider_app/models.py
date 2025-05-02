from django.db import models
from django.contrib.auth.models import User

class Rider(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    aadhar_number = models.CharField(max_length=12, unique=True)
    driving_license = models.CharField(max_length=20, unique=True)
    address = models.TextField()
    area = models.CharField(max_length=100)
    pincode = models.CharField(max_length=6)
    profile_photo = models.ImageField(upload_to='riders/profiles/')
    aadhar_front = models.ImageField(upload_to='riders/aadhar/')
    aadhar_back = models.ImageField(upload_to='riders/aadhar/', blank=True, null=True)
    license_copy = models.ImageField(upload_to='riders/license/')
    is_approved = models.BooleanField(default=False)
    is_available = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    current_location = models.CharField(max_length=255, blank=True, null=True)
    bank_account_name = models.CharField(max_length=100, blank=True, null=True)
    bank_account_number = models.CharField(max_length=18, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    ifsc_code = models.CharField(max_length=11, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} ({'Approved' if self.is_approved else 'Pending'})"
    def get_total_earnings(self):
        from django.db.models import Sum
        total = RiderEarning.objects.filter(rider=self).aggregate(Sum('total_earnings'))
        return total['total_earnings__sum'] or 0
    
    def get_total_orders_completed(self):
        from django.db.models import Sum
        total = RiderEarning.objects.filter(rider=self).aggregate(Sum('orders_completed'))
        return total['orders_completed__sum'] or 0
    
    def get_acceptance_rate(self):
        from django.db.models import Count, Q
        stats = OrderAssignment.objects.filter(rider=self).aggregate(
            total=Count('id'),
            accepted=Count('id', filter=Q(status='ACCEPTED'))
        )
        if stats['total'] == 0:
            return 0
        return round((stats['accepted'] / stats['total']) * 100, 1)

class RiderEarning(models.Model):
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE)
    date = models.DateField()
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2)
    orders_completed = models.PositiveIntegerField()

    def __str__(self):
        return f"Earnings on {self.date} - ₹{self.total_earnings}"


class OrderAssignment(models.Model):
    ORDER_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('DELIVERED', 'Delivered'),
    ]
    
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE)
    order = models.ForeignKey('user_app.Order', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='PENDING')
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.order.id} → {self.rider.user.username} [{self.status}]"
