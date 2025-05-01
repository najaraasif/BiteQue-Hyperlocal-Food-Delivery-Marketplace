from django import forms
from .models import merchantRegistration, addRestaurant
from .models import MerchantProfile, InventoryItem

class merchantRegistrationForm(forms.ModelForm):
    class Meta: 
        model = merchantRegistration
        fields = ['username','name','email','number', 'password', 'retypePassword']
        widgets = {
            'password': forms.PasswordInput(),
            'retypePassword': forms.PasswordInput(),
        }

class addRestaurantForm(forms.ModelForm):
    class Meta: 
        model = addRestaurant
        fields = ['name','owner_name','email','contact_number','restaurantAddress','city','pan_number', 'gstin_number', 'fssai_number']
        exclude = ['is_approved']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'owner_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'contact_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'city': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'restaurantAddress': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded', 'rows': 2}),
            'pan_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'gstin_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
            'fssai_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded'}),
        }

class MerchantStatusForm(forms.ModelForm):
    class Meta:
        model = MerchantProfile
        fields = ['is_online']

class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['merchant', 'name','quantity','price']
