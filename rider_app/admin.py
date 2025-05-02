from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Rider, RiderEarning, OrderAssignment
from .forms import RiderAdminForm

@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'is_approved', 'registration_date', 'is_available')
    list_editable = ('is_approved',)
    list_filter = ('is_approved',)
    search_fields = ('user__username', 'phone')
    date_hierarchy = 'created_at'
    
    def registration_date(self, obj):
        return obj.created_at
    registration_date.short_description = 'Registered On'