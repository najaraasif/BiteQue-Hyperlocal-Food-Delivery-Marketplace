from django.contrib import admin
from .models import userLogin

class userLoginAdmin(admin.ModelAdmin):
    list_display = ['username', 'password']
    list_filter = ['username', 'password']

admin.site.register(userLogin, userLoginAdmin)