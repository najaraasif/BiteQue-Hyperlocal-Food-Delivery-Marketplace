from django.contrib import admin
from .models import Order, CustomerFeedback, userRegistration
from django.utils.safestring import mark_safe



class userRegistrationAdmin(admin.ModelAdmin):
    list_display = ['username', 'name','number','email','address','password']
    list_filter = ['name', 'number']
    

class CustomerFeedbackAdmin(admin.ModelAdmin):
    list_display = ['customer','rating','comments','created_at']
    list_filter = ['order','customer']


class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_name', 'customer_contact', 'restaurant', 'get_menu_items', 'total', 'status', 'created_at', 'landmark', 'delivery_address','dest_lat','dest_lon', 'is_paid']
    list_filter = ['status', 'created_at', 'restaurant']
    search_fields = ['customer_name', 'restaurant__name']


    def render_change_form(self, request, context, *args, **kwargs):
        context['adminform'].form.fields['delivery_address'].help_text = mark_safe(
            '<button type="button" onclick="getCurrentLocation()">Use My Current Location</button>'
        )
        return super().render_change_form(request, context, *args, **kwargs)

    class Media:
        js = ('js/geocode.js',)


    def get_menu_items(self, obj):
        return ", ".join([item.name for item in obj.menu_items.all()])
    get_menu_items.short_description = 'Menu Items'

    def save_model(self, request, obj, form, change):
        # Save the object first to ensure it has a primary key (id)
        super().save_model(request, obj, form, change)
        
        # Now save the many-to-many field (menu_items)
        form.save_m2m()

        # Calculate the total based on the selected menu items
        obj.total = obj.calculate_total()
        obj.save(update_fields=['total'])

admin.site.register(userRegistration, userRegistrationAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(CustomerFeedback, CustomerFeedbackAdmin)
