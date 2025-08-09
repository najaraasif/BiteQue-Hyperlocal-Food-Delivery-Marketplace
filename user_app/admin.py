from django.contrib import admin
from .models import Order, CustomerFeedback, UserProfile
from django.utils.safestring import mark_safe



class userRegistrationAdmin(admin.ModelAdmin):
    list_display = ['username', 'name','number','email','address','password']
    list_filter = ['name', 'number']
    

class CustomerFeedbackAdmin(admin.ModelAdmin):
    list_display = ['customer','rating','comments','created_at']
    list_filter = ['order','customer']


from django.contrib import admin
from django.utils.safestring import mark_safe
from user_app.models import Order


class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer_name', 'customer_contact', 'restaurant',
        'get_menu_items', 'total', 'status', 'created_at',
        'landmark', 'delivery_address', 'dest_lat', 'dest_lon', 'is_paid'
    ]
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
        """
        Overridden to:
        - Detect status change
        - Recalculate total
        - Send WhatsApp notification if status changed
        """
        old_status = None
        if change and 'status' in form.changed_data:
            old_status = Order.objects.get(pk=obj.pk).status

        super().save_model(request, obj, form, change)
        form.save_m2m()

        # Recalculate total
        obj.total = obj.calculate_total()
        obj.save(update_fields=['total'])

        # Reload instance from DB
        obj.refresh_from_db()

        # If status changed, send WhatsApp update
        if change and old_status and obj.status != old_status:
            obj.send_status_update()



from django.contrib import admin
from .models import UserSupportTicket, UserSupportMessage

class TicketMessageInline(admin.TabularInline):
    model = UserSupportMessage
    extra = 1
    readonly_fields = ('created_at',)
    fields = ('sender', 'message', 'image', 'created_at')
    show_change_link = True


@admin.register(UserSupportTicket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'subject', 'user', 'category', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('ticket_id', 'subject', 'user__username', 'messages__message')
    inlines = [TicketMessageInline]
    readonly_fields = ('ticket_id', 'created_at', 'updated_at')
    list_per_page = 25
    ordering = ['-created_at']

    fieldsets = (
        (None, {
            'fields': ('ticket_id', 'user', 'category', 'status', 'subject')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(UserSupportMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'sender', 'short_message', 'created_at')
    list_filter = ('created_at', 'sender')
    search_fields = ('ticket__ticket_id', 'sender__username', 'message')
    readonly_fields = ('created_at',)

    def short_message(self, obj):
        return (obj.message[:75] + "...") if len(obj.message) > 75 else obj.message
    short_message.short_description = 'Message Preview'


admin.site.register(UserProfile)

admin.site.register(Order, OrderAdmin)
admin.site.register(CustomerFeedback, CustomerFeedbackAdmin)
