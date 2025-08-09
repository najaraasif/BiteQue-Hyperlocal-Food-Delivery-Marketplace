from django import forms
from .models import merchantRegistration, Restaurant
from merchant_app.models import  merchantRegistration, Restaurant, RestaurantMenu, BankAccount
from django.contrib.auth.models import User
from django import forms
from user_app.models import Order
import re

class MerchantRegistrationForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label="Username",
        help_text="Required. 4-150 characters. Letters, digits and @/./+/-/_ only."
    )
    name = forms.CharField(
        max_length=100,
        label="Full Name"
    )
    number = forms.CharField(
        max_length=15,
        label="Phone Number",
        help_text="Required. Only digits. Format: +91XXXXXXXXXX or 10-digit local."
    )
    email = forms.EmailField(
        max_length=100,
        label="Email"
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Password",
        help_text="At least 8 characters, with a digit, uppercase, lowercase, and special character."
    )
    retypePassword = forms.CharField(
        widget=forms.PasswordInput,
        label="Retype Password"
    )

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if not re.match(r'^[\w.@+-]+$', username):
            raise forms.ValidationError("Username contains invalid characters.")
        if len(username) < 4:
            raise forms.ValidationError("Username must be at least 4 characters long.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists.")
        return username

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not re.match(r'^[A-Za-z\s]+$', name):
            raise forms.ValidationError("Name should contain only letters and spaces.")
        return name

    def clean_number(self):
        number = self.cleaned_data.get("number")
        if not re.match(r'/^[6-9]\d{10}$', number):  
            raise forms.ValidationError("Enter a valid phone number.")
        # Optional: check for duplicates if number is stored in a related model
        # if MerchantModel.objects.filter(number=number).exists():
        #     raise forms.ValidationError("Phone number already registered.")
        return number

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'\d', password):
            raise forms.ValidationError("Password must contain at least one digit.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', password):
            raise forms.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise forms.ValidationError("Password must contain at least one special character.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        retype_password = cleaned_data.get("retypePassword")

        if password and retype_password and password != retype_password:
            self.add_error('retypePassword', "Passwords do not match.")

        return cleaned_data


class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        exclude = ['owner', 'is_approved','is_available']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
            'contact_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]', 'rows': 3
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
            'pan_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
            'gstin_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
            'fssai_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#FF0B55] focus:border-[#FF0B55]'
            }),
        }

    def clean_contact_number(self):
        number = self.cleaned_data['contact_number']
        if not re.match(r'/^[6-9]\d{10}$', number):
            raise forms.ValidationError("Enter a valid mobile number.")
        return number

    def clean_pan_number(self):
        pan = self.cleaned_data['pan_number']
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
            raise forms.ValidationError("Invalid PAN format. Example: ABCDE1234F")
        return pan

    def clean_gstin_number(self):
        gstin = self.cleaned_data['gstin_number']
        if not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$', gstin):
            raise forms.ValidationError("Invalid GSTIN format.")
        return gstin

    def clean_fssai_number(self):
        fssai = self.cleaned_data['fssai_number']
        if not re.match(r'^\d{14}$', fssai):
            raise forms.ValidationError("FSSAI must be a 14-digit number.")
        return fssai

class RestaurantMenuForm(forms.ModelForm):
    class Meta:
        model = RestaurantMenu
        fields = ['name','sizes_categories', 'category', 'description', 'image', 'price', 'available', 'prep_time', 'veg_or_nonveg']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'Enter dish name',
            }),
            'sizes_categories': forms.Select(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
            }),
            'category': forms.TextInput(attrs={
                'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
                'placeholder': 'Enter category eg; pizza',
            }),
            'veg_or_nonveg': forms.Select(attrs={
                    'class': 'w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500',
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

from .models import Review

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(choices=[(i, i) for i in range(1, 6)], attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
        }
    
from django import forms
from .models import Ticket, TicketMessage

class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['subject', 'category']
        widgets = {
            'subject': forms.TextInput(attrs={'placeholder': 'Enter ticket subject', 'class': 'border border-black rounded-md p-3 focus:outline-none focus:ring-2 focus:ring-red-400 form-control'}),
            'category': forms.Select(attrs={'class': 'border border-black rounded-md p-3 focus:outline-none focus:ring-2 focus:ring-red-400 form-select'}),
        }


class TicketMessageForm(forms.ModelForm):
    class Meta:
        model = TicketMessage
        fields = ['message','image']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write your message here...', 'class': 'border border-black rounded-md p-3 focus:outline-none focus:ring-2 focus:ring-red-400 form-control'}),
        }
        labels = {
            'message': 'Message',
        }
