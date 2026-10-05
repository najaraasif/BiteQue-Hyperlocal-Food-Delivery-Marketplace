from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User

from merchant_app.models import BankAccount
from .models import Rider, RiderBankAccount
from django.db import transaction


class RiderRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
    
    full_name = forms.CharField(max_length=100, required=True)
    phone = forms.CharField(max_length=15, required=True)
    gender = forms.ChoiceField(choices=Rider.GENDER_CHOICES, required=True)
    aadhar_number = forms.CharField(max_length=12, required=True)
    driving_license = forms.CharField(max_length=20, required=True)
    address = forms.CharField(widget=forms.Textarea, required=True)
    area = forms.CharField(max_length=100, required=True)
    pincode = forms.CharField(max_length=6, required=True)
    profile_photo = forms.ImageField(required=True)
    aadhar_front = forms.ImageField(required=True)
    aadhar_back = forms.ImageField(required=True)
    license_copy = forms.ImageField(required=True)

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        if not phone.isdigit() or len(phone) < 10:
            raise forms.ValidationError("Phone number must be at least 10 digits.")
        return phone

    def clean_aadhar_number(self):
        aadhar = self.cleaned_data['aadhar_number']
        if not aadhar.isdigit() or len(aadhar) != 12:
            raise forms.ValidationError("Aadhar number must be exactly 12 digits.")
        if Rider.objects.filter(aadhar_number=aadhar).exists():
            raise forms.ValidationError("This Aadhar number is already registered.")
        return aadhar

    def clean_driving_license(self):
        license = self.cleaned_data['driving_license']
        if len(license) < 10:
            raise forms.ValidationError("Driving license number must be at least 10 characters.")
        if Rider.objects.filter(driving_license=license).exists():
            raise forms.ValidationError("This driving license number is already registered.")
        return license

    def clean_pincode(self):
        pincode = self.cleaned_data['pincode']
        if not pincode.isdigit() or len(pincode) != 6:
            raise forms.ValidationError("Pincode must be exactly 6 digits.")
        return pincode


class RiderAdminForm(forms.ModelForm):
    class Meta:
        model = Rider
        fields = '__all__'
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'username' in self.fields:
            self.fields['username'].widget.attrs.update({
                'class': 'form-input'
            })

        if 'email' in self.fields:
            self.fields['email'].widget.attrs.update({
                'placeholder': 'you@example.com'
            })

class RiderLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class' : 'w-full px-4 py-2 border rounded-lg',
        'placeholder' : 'Username'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-2 border rounded-lg',
        'placeholder': 'Password'
    }))

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not hasattr(user, 'rider'):
            raise forms.ValidationError("This account doesn't have a rider profile.")
        if not user.rider.is_approved:
            raise forms.ValidationError("Your rider account is pending approval.")
        
from django.contrib.auth.forms import PasswordResetForm

class RiderPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg',
            'placeholder': 'Enter your email address'
        }),
        max_length=254,
        required=True
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email=email, rider__isnull=False).exists():
            raise forms.ValidationError("This email is not registered as a rider.")
        return email

class BankDetailsForm(forms.ModelForm): 
    class Meta:
        model = RiderBankAccount
        fields = ['account_holder_name', 'account_number', 'bank_name', 'ifsc_code', 'is_primary']
        widgets = {
            'account_number': forms.TextInput(attrs={
                'placeholder': 'Enter 11-18 digit account number'
            }),
            'ifsc_code': forms.TextInput(attrs={
                'placeholder': 'e.g. SBIN0000123'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.rider = kwargs.pop('rider', None) 
        super().__init__(*args, **kwargs)

    def clean_account_number(self): 
        account_num = self.cleaned_data['account_number']
        if account_num and not account_num.isdigit():
            raise forms.ValidationError("Account number should contain only digits")
        if account_num and len(account_num) < 11: 
            raise forms.ValidationError("Account number too short")
        return account_num

    def clean_ifsc_code(self):
        ifsc = self.cleaned_data['ifsc_code']
        if ifsc and len(ifsc) != 11:
            raise forms.ValidationError("IFSC code must be 11 characters long")
        return ifsc

    def clean(self):
        cleaned_data = super().clean()
        is_primary = cleaned_data.get("is_primary")

        if self.rider and is_primary:
            
            if RiderBankAccount.objects.filter(rider=self.rider, is_primary=True).exclude(pk=self.instance.pk).exists():
                
                pass
        elif self.rider and not self.instance.pk and not RiderBankAccount.objects.filter(rider=self.rider).exists():
            cleaned_data['is_primary'] = True
        return cleaned_data
    

class DeliveryOTPForm(forms.Form):
    otp = forms.CharField(
        label='Delivery PIN',
        max_length=6,
        min_length=4,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg text-center',
            'placeholder': 'Enter 4 digit PIN',
            'type': 'number',
            'pattern': '\\d*',
            'inputmode': 'numeric'
        })
    )

    def clean_otp(self):
        otp = self.cleaned_data.get('otp')
        if not otp.isdigit():
            raise forms.ValidationError("PIN must only contain digits.")
        if not (len(otp) == 4 or len(otp) == 6):
            raise forms.ValidationError("PIN must be 4 or 6 digits long.")
        return otp