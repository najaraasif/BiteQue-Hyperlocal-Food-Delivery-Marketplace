from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Rider, RiderEarning, OrderAssignment
from .forms import RiderAdminForm

class RiderAdmin(admin.ModelAdmin):
    form = RiderAdminForm
    list_display = ('user', 'phone', 'is_available', 'is_approved', 'created_at')
    list_filter = ('is_available', 'is_approved', 'created_at')
    search_fields = ('user__username', 'phone', 'aadhar_number', 'driving_license')
    readonly_fields = ('created_at',)
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
        ('Status', {
            'fields': ('is_available', 'is_approved', 'current_location')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    actions = ['approve_riders', 'disapprove_riders']

    def approve_riders(self, request, queryset):
        queryset.update(is_approved=True)
    approve_riders.short_description = "Approve selected riders"

    def disapprove_riders(self, request, queryset):
        queryset.update(is_approved=False)
    disapprove_riders.short_description = "Disapprove selected riders"

"""class RiderEarningAdmin(admin.ModelAdmin):
    list_display = ('rider', 'date', 'total_earnings', 'orders_completed')
    list_filter = ('date', 'rider')
    search_fields = ('rider__user__username',)
    date_hierarchy = 'date'"""

"""class OrderAssignmentAdmin(admin.ModelAdmin):
    list_display = ('order', 'rider', 'status', 'assigned_at', 'updated_at')
    list_filter = ('status', 'assigned_at')
    search_fields = ('order__id', 'rider__user__username')
    readonly_fields = ('assigned_at', 'updated_at')
    list_editable = ('status',)
    date_hierarchy = 'assigned_at'"""


#admin.site.register(RiderEarning, RiderEarningAdmin)
#admin.site.register(OrderAssignment, OrderAssignmentAdmin)

@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'is_approved', 'is_available')
    list_editable = ('is_approved',)
    actions = ['approve_riders']

    def approve_riders(self, request, queryset):
        queryset.update(is_approved=True)
    approve_riders.short_description = "Approve selected riders"