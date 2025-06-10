from django import forms
from .models import Order, CustomerFeedback, userRegistration
import re
from django.contrib.auth.models import User

class userRegistrationForm(forms.Form):
        username = forms.CharField(
            max_length=15,
            label="Username",
            help_text="Required. 4-150 characters. Letters, digits and @/./+/-/_ only."
        )
        name = forms.CharField(
            max_length=50,
            label="Full Name"
        )
        email = forms.EmailField(
            max_length=50,
            label="Email"
        )
        password = forms.CharField(
            widget=forms.PasswordInput,
            label="Password",
            max_length=20,
            help_text="At least 8 characters, with a digit, uppercase, lowercase, and special character."
        )
        retypePassword = forms.CharField(
            widget=forms.PasswordInput,
            max_length=20,
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
            if not re.match(r'^(\+?\d{10,15})$', number):
                raise forms.ValidationError("Enter a valid phone number.")
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

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['restaurant', 'customer_name', 'customer_contact', 'landmark', 'menu_items','status','delivery_address', 'dest_lat','dest_lon']
        widgets = {
            'menu_items': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: Limit menu items to available=True and filter by restaurant if needed
        self.fields['menu_items'].queryset = self.fields['menu_items'].queryset.filter(available=True)


class CustomerFeedbackForm(forms.Form):
    class Meta:
        model = CustomerFeedback
        fields = ['customer', 'rating', 'feedback_text', 'comments']
        widgets = {
            'feedback_text': forms.Textarea(attrs={'placeholder': 'Write your feedback here...'}),
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }
