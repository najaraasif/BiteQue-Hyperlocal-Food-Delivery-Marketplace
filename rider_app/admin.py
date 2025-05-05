from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Rider, RiderEarning, OrderAssignment
from .forms import RiderAdminForm
from django.utils.html import format_html

@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    form = RiderAdminForm
    list_display = (
        'user',
        'phone',
        'is_approved',
        'is_available',
        'total_earnings_display',
        'completed_orders_display',
        'acceptance_rate_display',
        'registration_date'
    )
    list_editable = ('is_approved', 'is_available')
    list_filter = ('is_approved', 'is_available', 'gender')
    search_fields = (
        'user__username',
        'phone',
        'aadhar_number',
        'driving_license'
    )
    readonly_fields = (
        'profile_photo_preview',  # Method for preview
        'aadhar_front_preview',   # Method for preview
        'license_copy_preview',
        'total_earnings_display',
        'completed_orders_display',
        'acceptance_rate_display',
        'registration_date'
    )
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'user',
                'phone',
                'gender',
                'is_approved',
                'is_available'
            )
        }),
        ('Verification Documents', {
            'fields': (
                'aadhar_number',
                'driving_license',
                'profile_photo_preview',
                'aadhar_front_preview',
                'license_copy_preview'
                
            )
        }),
        ('Location Details', {
            'fields': (
                'address',
                'area',
                'pincode',
                'current_location'
            )
        }),
        ('Bank Information', {
            'fields': (
                'bank_account_name',
                'bank_account_number',
                'bank_name',
                'ifsc_code'
            )
        }),
        ('Performance Metrics', {
            'fields': (
                'total_earnings_display',
                'completed_orders_display',
                'acceptance_rate_display'
            )
        }),
    )
    
    actions = ['approve_riders', 'make_available', 'make_unavailable']
    
    def profile_photo_preview(self, obj):
        if obj.profile_photo:
            return format_html('<img src="{}" width="150" />', obj.profile_photo.url)
        return "-"
    profile_photo_preview.short_description = 'Profile Photo Preview'
    
    def aadhar_front_preview(self, obj):
        if obj.aadhar_front:
            return format_html('<img src="{}" width="150" />', obj.aadhar_front.url)
        return "-"
    aadhar_front_preview.short_description = 'Aadhar Front Preview'
    
    def license_copy_preview(self, obj):
        if obj.license_copy:
            return format_html('<img src="{}" width="150" />', obj.license_copy.url)
        return "-"
    license_copy_preview.short_description = 'License Copy Preview'
    
    def total_earnings_display(self, obj):
        return f"₹{obj.get_total_earnings():,.2f}"
    total_earnings_display.short_description = 'Total Earnings'
    
    def completed_orders_display(self, obj):
        return obj.get_total_orders_completed()
    completed_orders_display.short_description = 'Completed Orders'
    
    def acceptance_rate_display(self, obj):
        return obj.acceptance_rate_display
    acceptance_rate_display.short_description = 'Acceptance Rate'
    
    def registration_date(self, obj):
        return obj.created_at.strftime("%b %d, %Y")
    registration_date.short_description = 'Registration Date'
    
    @admin.action(description='Approve selected riders')
    def approve_riders(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} riders were approved")
    
    @admin.action(description='Mark as available')
    def make_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f"{updated} riders were marked available")
    
    @admin.action(description='Mark as unavailable')
    def make_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f"{updated} riders were marked unavailable")


@admin.register(RiderEarning)
class RiderEarningAdmin(admin.ModelAdmin):
    list_display = (
        'rider',
        'date',
        'total_earnings_display',
        'orders_completed'
    )
    list_filter = ('date', 'rider')
    search_fields = ('rider__user__username',)
    date_hierarchy = 'date'
    
    def total_earnings_display(self, obj):
        return f"₹{obj.total_earnings:,.2f}"
    total_earnings_display.short_description = 'Earnings'


@admin.register(OrderAssignment)
class OrderAssignmentAdmin(admin.ModelAdmin):
    list_display = ('order', 'rider', 'status', 'assigned_at')
    list_filter = ('status',)  # Show all statuses
    search_fields = (
        'order__id',
        'rider__user__username'
    )
    readonly_fields = (
        'assigned_at',
        'updated_at'
    )
    date_hierarchy = 'assigned_at'
    list_select_related = ('rider', 'order')