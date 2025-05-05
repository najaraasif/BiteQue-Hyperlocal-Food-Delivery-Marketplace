from os import __all__
from django.contrib import admin
from .models import merchantRegistration, Restaurant, RestaurantMenu, BankAccount
from rider_app.models import Rider, OrderAssignment



class merchantRegistrationAdmin(admin.ModelAdmin):
    list_display = ['username', 'name', 'number', 'email', 'password', 'retypePassword']
    list_filter = ['username']

class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name','owner','email','contact_number','address','city','pan_number', 'gstin_number', 'fssai_number','is_approved']
    list_filter = ['name']

class RestaurantMenuAdmin(admin.ModelAdmin):
    list_display = ['name', 'image', 'price', 'available', 'size_category']
    list_filter = ['name']

class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['merchant','bank_name', 'account_holder_name', 'account_number','ifsc_code', 'is_primary']
    list_filter = ['account_holder_name']

admin.site.register(merchantRegistration, merchantRegistrationAdmin)
admin.site.register(Restaurant, RestaurantAdmin)
admin.site.register(RestaurantMenu, RestaurantMenuAdmin)
admin.site.register(BankAccount, BankAccountAdmin)

class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'restaurant', 'status', 'created_at']
    list_editable = ['status']  # Allow status changes in admin list
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Trigger assignments only if status is 'ready'
        if obj.status == 'ready':
            riders = Rider.objects.filter(is_available=True, is_approved=True)
            for rider in riders:
                OrderAssignment.objects.get_or_create(
                    rider=rider,
                    order=obj,
                    defaults={'status': 'PENDING'}
                )
