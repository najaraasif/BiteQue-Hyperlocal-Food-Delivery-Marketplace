from django.contrib import admin
from .models import Order,userLogin
from rider_app.models import Rider, OrderAssignment


class userLoginAdmin(admin.ModelAdmin):
    list_display = ['username', 'password']
    list_filter = ['username', 'password']




class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'restaurant', 'status', 'created_at']
    list_editable = ['status']  # Allow status editing in admin list

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Create assignments when status is 'ready'
        if obj.status == 'ready':
            riders = Rider.objects.filter(is_available=True, is_approved=True)
            for rider in riders:
                OrderAssignment.objects.get_or_create(
                    rider=rider,
                    order=obj,
                    defaults={'status': 'PENDING'}
                )

admin.site.register(userLogin, userLoginAdmin)
admin.site.register(Order, OrderAdmin)

