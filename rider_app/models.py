from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q
from datetime import timedelta
from django.utils import timezone

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
    area = models.CharField(max_length=100, blank=True, help_text="Delivery area/zone")
    pincode = models.CharField(max_length=6)
    profile_photo = models.ImageField(upload_to='riders/profiles/')
    aadhar_front = models.ImageField(upload_to='riders/aadhar/')
    license_copy = models.ImageField(upload_to='riders/license/')
    aadhar_back = models.ImageField(upload_to='riders/aadhar/', blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    is_available = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    current_location = models.CharField(max_length=255, blank=True, null=True)
    total_assignments = models.PositiveIntegerField(default=0)
    accepted_assignments = models.PositiveIntegerField(default=0)
    assigned_at = models.DateTimeField(default=timezone.now)
    today_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    
    

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Rider'
        verbose_name_plural = 'Riders'

    def __str__(self):
        return f"{self.user.username} ({'Approved' if self.is_approved else 'Pending'})"
    
    def get_total_earnings(self):
        total = self.riderearning_set.aggregate(
            total_earnings=Sum('total_earnings')
        )['total_earnings']
        return total or 0
    
    def get_total_orders_completed(self):
        return self.orderassignment_set.filter(
            status='delivered'
        ).count()
    
    def get_acceptance_rate(self):
        assignments = self.orderassignment_set.filter(
            status__in=['accepted', 'rejected']
        )
        
        if not assignments.exists():
            return 0.0
            
        total_score = sum(
            a.acceptance_score for a in assignments 
            if a.status == 'accepted'
        )
        total_possible = 100 * assignments.count()
        
        return round((total_score / total_possible) * 100, 1) if total_possible else 0.0
    #transaction
    def get_current_balance(self):
        total_earnings = self.get_total_earnings()
        total_payments = self.transaction_set.filter(
            transaction_type='payment', 
            processed=True
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        return (total_earnings - total_payments)

    def get_transaction_history(self):
        return self.transaction_set.all().order_by('-transaction_date')



class RiderEarning(models.Model):
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2)
    orders_completed = models.PositiveIntegerField()
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=0)  
    distance_earning = models.DecimalField(max_digits=10, decimal_places=2, default=0)  
    commission_earning = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Rider Earning'
        verbose_name_plural = 'Rider Earnings'

    def __str__(self):
        return f"Earnings on {self.date} - ₹{self.total_earnings}"


class OrderAssignment(models.Model):
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('delivered', 'Delivered'),
    ]
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE)
    order = models.ForeignKey(
        'user_app.Order', 
        on_delete=models.CASCADE,
        related_name='assignments'  
    ) 
    status = models.CharField(
        max_length=20,
        choices=ORDER_STATUS_CHOICES,
        default='pending'  
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    response_time = models.DurationField(null=True, blank=True)
    acceptance_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=0.0,
        help_text="Weighted score based on response time"
    )

    class Meta:
        ordering = ['-assigned_at']
        verbose_name = 'Order Assignment'
        verbose_name_plural = 'Order Assignments'
        constraints = [
            models.UniqueConstraint(
                fields=['order'],
                condition=models.Q(status='accepted'),
                name='unique_accepted_assignment_for_order' 
            )
        ]
    pass
    def __str__(self):
        return f"Order #{self.order.id} → {self.rider.user.username} [{self.status}]"
    

class RiderBankAccount(models.Model):
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name='bank_accounts')
    account_holder_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=18)
    bank_name = models.CharField(max_length=100)
    ifsc_code = models.CharField(max_length=11)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']
        verbose_name = 'Rider Bank Account'
        verbose_name_plural = 'Rider Bank Accounts'
        constraints = [
            models.UniqueConstraint(fields=['rider', 'is_primary'], condition=models.Q(is_primary=True), name='unique_primary_bank_account_per_rider')
        ]

    def __str__(self):
        return f"{self.rider.user.username} - {self.account_number} ({'Primary' if self.is_primary else 'Secondary'})"

    def save(self, *args, **kwargs):
        if self.is_primary:
            RiderBankAccount.objects.filter(rider=self.rider, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('payment', 'Payment to Rider'),
        ('pending', 'Pending Balance'),
    ]

    rider = models.ForeignKey(Rider, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=255)
    transaction_date = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-transaction_date']

    def __str__(self):
        return f"{self.get_transaction_type_display()} - ₹{self.amount}"