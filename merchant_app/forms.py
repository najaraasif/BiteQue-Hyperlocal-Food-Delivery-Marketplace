from django import forms
from .models import merchantRegistration, Restaurant
from merchant_app.models import  merchantRegistration, Restaurant, RestaurantMenu, BankAccount
from django.contrib.auth.models import User
from django import forms
from user_app.models import Order


class merchantRegistrationForm(forms.ModelForm):
    username = forms.CharField(max_length=100, label="Username")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    retypePassword = forms.CharField(widget=forms.PasswordInput, label="Retype Password")

    class Meta:
        model = merchantRegistration
        fields = ['username', 'name', 'number', 'email', 'password']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        retype_password = cleaned_data.get('retypePassword')

        if password and retype_password and password != retype_password:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data




class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        exclude = ['owner', 'is_approved']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-input'}),
            'address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-input'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-input'}),
            'gstin_number': forms.TextInput(attrs={'class': 'form-input'}),
            'fssai_number': forms.TextInput(attrs={'class': 'form-input'}),
        }


class RestaurantMenuForm(forms.ModelForm):
    class Meta:
        model = RestaurantMenu
        fields = ['name', 'size_category', 'description', 'image', 'price', 'available', 'prep_time']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'Enter dish name'
            }),
            'size_category': forms.TextInput(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'Enter size category'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'Describe the item',
                'rows': 3
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'e.g., 199.99'
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
            'available': forms.CheckboxInput(attrs={
                'class': 'mr-2 text-blue-500',
            }),
            'prep_time': forms.NumberInput(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'Minutes',
                'type': 'number',
                'min': '0',
            }),
        }


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['bank_name', 'account_holder_name', 'account_number', 'ifsc_code', 'is_primary','is_approved' ]
        exclude = [ 'is_approved']
        widgets = {
            'bank_name': forms.TextInput(attrs={'class': 'form-input'}),
            'account_holder_name': forms.TextInput(attrs={'class': 'form-input'}),
            'account_number': forms.TextInput(attrs={'class': 'form-input'}),
            'ifsc_code': forms.TextInput(attrs={'class': 'form-input'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),

        }


class UpdateOrderStatusForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['status']
        widgets = {
            'status': forms.Select(choices=Order.STATUS_CHOICES),
        }