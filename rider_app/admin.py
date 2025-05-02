from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Rider, RiderEarning, OrderAssignment
from .forms import RiderAdminForm


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'is_approved', 'is_available', 'bank_account_name')
    list_editable = ('is_approved',)
    search_fields = ('user__username', 'phone', 'bank_account_number')

    fieldsets = (
        ('Personal Info', {
            'fields': ('user', 'phone', 'gender', 'profile_photo')
        }),
        ('Government IDs', {
            'fields': ('aadhar_number', 'aadhar_front', 'aadhar_back', 
                      'driving_license', 'license_copy')
        }),
        ('Address Details', {
            'fields': ('address', 'area', 'pincode')
        }),
        ('Bank Details', {
            'fields': ('bank_account_name', 'bank_account_number', 'bank_name', 'ifsc_code'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_available', 'is_approved', 'current_location')
        }),
        # Removed the Metadata fieldset since created_at is auto-generated
    )
    
    readonly_fields = ('created_at',)  # Show as read-only if needed
    
    actions = ['approve_riders']

    def approve_riders(self, request, queryset):
        queryset.update(is_approved=True)
    approve_riders.short_description = "Approve selected riders"