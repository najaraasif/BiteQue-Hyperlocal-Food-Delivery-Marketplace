from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Rider, User


class RiderRegistrationForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-[#FF0B55]',
            'placeholder': 'Enter your full name'
        })
    )
    phone = forms.CharField(max_length=15)
    gender = forms.ChoiceField(choices=Rider.GENDER_CHOICES)
    aadhar_number = forms.CharField(max_length=12)
    driving_license = forms.CharField(max_length=20)
    address = forms.CharField(widget=forms.Textarea)
    area = forms.CharField(max_length=100)
    pincode = forms.CharField(max_length=6)
    profile_photo = forms.ImageField()
    aadhar_front = forms.ImageField()
    aadhar_back = forms.ImageField()
    license_copy = forms.ImageField()

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def clean_aadhar_number(self):
        aadhar = self.cleaned_data['aadhar_number']
        if not aadhar.isdigit() or len(aadhar) != 12:
            raise forms.ValidationError("Invalid Aadhar number")
        return aadhar

    def clean_pincode(self):
        pincode = self.cleaned_data['pincode']
        if not pincode.isdigit() or len(pincode) != 6:
            raise forms.ValidationError("Invalid pincode")
        return pincode


class RiderAdminForm(forms.ModelForm):
    class Meta:
        model = Rider
        fields = '__all__'
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply class styling to the fields if they exist
        if 'username' in self.fields:
            self.fields['username'].widget.attrs.update({
                'class': 'form-input'
            })

        if 'email' in self.fields:
            self.fields['email'].widget.attrs.update({
                'placeholder': 'you@example.com'
            })
    
    def save(self, commit=True):
        user = super().save(commit=False)
        # Split full name into first and last names
        full_name = self.cleaned_data['full_name'].split()
        user.first_name = full_name[0] if full_name else ''
        user.last_name = ' '.join(full_name[1:]) if len(full_name) > 1 else ''
        
        if commit:
            user.save()
        return user    
        
    def clean_aadhar_number(self):
        aadhar = self.cleaned_data['aadhar_number']
        if not aadhar.isdigit() or len(aadhar) != 12:
            raise forms.ValidationError("Aadhar number must be 12 digits")
        return aadhar
        
    def clean_driving_license(self):
        license = self.cleaned_data['driving_license']
        if len(license) < 10:
            raise forms.ValidationError("Invalid driving license number")
        return license

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