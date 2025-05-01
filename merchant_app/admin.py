from os import __all__
from django.contrib import admin
from .models import merchantRegistration, addRestaurant
from .models import MerchantProfile, InventoryItem, Order, Payment

class merchantRegistrationAdmin(admin.ModelAdmin):
    list_display = ['username', 'name', 'number', 'email', 'password', 'retypePassword']
    list_filter = ['username']

class addRestaurantAdmin(admin.ModelAdmin):
    list_display = ['name','owner_name','email','contact_number','restaurantAddress','city','pan_number', 'gstin_number', 'fssai_number','is_approved']
    list_filter = ['name']

class MerchantProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'business_name', 'phone', 'address', 'is_online']

class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'name', 'quantity', 'price', 'last_updated']

class OrderAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'customer_name', 'total_amount', 'date', 'status']

class PaymentAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'amount', 'transaction_date', 'transaction_id']






admin.site.register(merchantRegistration, merchantRegistrationAdmin)
admin.site.register(InventoryItem, InventoryItemAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(MerchantProfile, MerchantProfileAdmin)