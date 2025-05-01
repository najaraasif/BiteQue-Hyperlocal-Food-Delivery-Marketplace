from django.db import models

class Order(models.Model):
    customer_name = models.CharField(max_length=100)
    delivery_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='pending')

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"
    
class userLogin(models.Model):
    username = models.CharField(unique=True, default='shakir', max_length=50)
    password = models.CharField(unique=True, default='Shakir@2002', max_length=50)

    def __str__(self):
        return self.username
    