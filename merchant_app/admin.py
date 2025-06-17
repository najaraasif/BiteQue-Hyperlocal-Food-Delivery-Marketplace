from os import __all__
from django.contrib import admin
from django.utils.html import format_html
from .models import merchantRegistration, Restaurant, RestaurantMenu, BankAccount, MerchantPayment, MerchantEarning, SizeCategory, Review
from .signals import send_merchant_verification_email, send_merchant_restaurant_email
from rider_app.models import OrderAssignment, Rider

class merchantRegistrationAdmin(admin.ModelAdmin):
    list_display = ['username', 'name', 'number', 'is_approved']
    list_filter = ['username']


    def save_model(self, request, obj, form, change):
        if change:
            old_obj = merchantRegistration.objects.get(pk=obj.pk)
            if not old_obj.is_approved and obj.is_approved:
                # Only send email if status changed from False to True
                send_merchant_verification_email(obj)

        super().save_model(request, obj, form, change)

class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'email', 'contact_number', 'address', 'city', 'pan_number', 'gstin_number', 'fssai_number', 'is_approved']
    list_filter = ['name']

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = Restaurant.objects.get(pk=obj.pk)
            if not old_obj.is_approved and obj.is_approved:
                # Send email only when approval status changes from False to True
                send_merchant_restaurant_email(obj)
        super().save_model(request, obj, form, change)


class RestaurantMenuAdmin(admin.ModelAdmin):
    list_display = ['name', 'image','get_size_categories', 'price', 'available', 'category']
    list_filter = ['restaurant', 'category']

    def get_size_categories(self, obj):
        return obj.sizes_categories.name



class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['merchant','bank_name', 'account_holder_name', 'account_number','ifsc_code', 'is_primary']
    list_filter = ['account_holder_name']


class MerchantPaymentAdmin(admin.ModelAdmin):
    list_display = ('merchant', 'restaurant', 'amount_paid', 'payment_date', 'payment_method', 'transaction_id', 'account','screenshot_preview')
    list_filter = ('payment_date', 'payment_method', 'transaction_id', 'account')
    search_fields = ('merchant__username', 'restaurant__name', 'transaction_id')
    readonly_fields = ('screenshot_preview',)

    def screenshot_preview(self, obj):
        if obj.payment_screenshot:
            return format_html('<img src="{}" width="100" height="100" />', obj.payment_screenshot.url)
        return "No Screenshot"

    screenshot_preview.short_description = "Payment Screenshot"

class MerchantEarningAdmin(admin.ModelAdmin):
    list_display = ('merchant', 'restaurant', 'net_sales', 'weekly_sales', 'amount_paid', 'amount_pending', 'last_updated')
    readonly_fields = ('merchant', 'restaurant', 'net_sales', 'weekly_sales', 'amount_paid', 'amount_pending', 'last_updated')

    def has_add_permission(self, request):
        return False  # Prevent adding from admin panel

    def has_change_permission(self, request, obj=None):
        return False  # Prevent editing

    def has_delete_permission(self, request, obj=None):
        return False  # Prevent deletion
    

from django.contrib import admin
from .models import Ticket, TicketMessage

class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 1
    readonly_fields = ('created_at',)
    fields = ('sender', 'message', 'image', 'created_at')
    show_change_link = True


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'subject', 'merchant', 'category', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('ticket_id', 'subject', 'merchant__username', 'messages__message')
    inlines = [TicketMessageInline]
    readonly_fields = ('ticket_id', 'created_at', 'updated_at')
    list_per_page = 25
    ordering = ['-created_at']

    fieldsets = (
        (None, {
            'fields': ('ticket_id', 'merchant', 'category', 'status', 'subject')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'sender', 'short_message', 'created_at')
    list_filter = ('created_at', 'sender')
    search_fields = ('ticket__ticket_id', 'sender__username', 'message')
    readonly_fields = ('created_at',)

    def short_message(self, obj):
        return (obj.message[:75] + "...") if len(obj.message) > 75 else obj.message
    short_message.short_description = 'Message Preview'

admin.site.register(SizeCategory)
admin.site.register(Review)
admin.site.register(merchantRegistration, merchantRegistrationAdmin)
admin.site.register(Restaurant, RestaurantAdmin)
admin.site.register(RestaurantMenu, RestaurantMenuAdmin)
admin.site.register(BankAccount, BankAccountAdmin)
admin.site.register(MerchantPayment, MerchantPaymentAdmin)
admin.site.register(MerchantEarning, MerchantEarningAdmin)

