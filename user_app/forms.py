import os
from django import forms
from .models import Order, CustomerFeedback, userRegistration
import re
from django.contrib.auth.models import User
from django import forms
from .models import UserSupportTicket, UserSupportMessage

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
        fields = ['restaurant', 'customer_name', 'customer_contact', 'landmark','special_instructions', 'status','delivery_address', 'dest_lat','dest_lon']
        widgets = {
            'menu_items': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: Limit menu items to available=True and filter by restaurant if needed


class CustomerFeedbackForm(forms.Form):
    class Meta:
        model = CustomerFeedback
        fields = ['customer', 'rating', 'feedback_text', 'comments']
        widgets = {
            'feedback_text': forms.Textarea(attrs={'placeholder': 'Write your feedback here...'}),
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }
from django import forms
from .models import CustomerFeedback

class OrderFeedbackForm(forms.ModelForm):
    class Meta:
        model = CustomerFeedback
        fields = ['rating', 'comments']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-select'}),
            'comments': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4, 'placeholder': 'Write your feedback...'}),
        }


from django import forms
from .models import CustomerFeedback

class ComprehensiveFeedbackForm(forms.ModelForm):
    class Meta:
        model = CustomerFeedback
        fields = [
            'item_quality', 
            'delivery_experience',
            'restaurant_rating',
            'rider_rating',
            'additional_comments'
        ]
        widgets = {
            'item_quality': forms.RadioSelect(attrs={'class': 'star-rating'}),
            'delivery_experience': forms.RadioSelect(attrs={'class': 'star-rating'}),
            'restaurant_rating': forms.RadioSelect(attrs={'class': 'star-rating'}),
            'rider_rating': forms.RadioSelect(attrs={'class': 'star-rating'}),
            'additional_comments': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Any additional feedback...'
            }),
        }
    def __init__(self, *args, **kwargs):
        order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)

        if order:
            self.order = order  # store reference if needed later

            # Dynamically add rating fields for each item in the order
            for item in order.order_items.all():
                field_name = f'item_rating_{item.menu_item.id}'
                self.fields[field_name] = forms.ChoiceField(
                    choices=[(i, str(i)) for i in range(1, 6)],
                    label=f"Rating for {item.menu_item.name}",
                    widget=forms.RadioSelect(attrs={'class': 'star-rating'}),
                    required=False
                )


    def get_item_ratings(self):
        """
        Extract item ratings from cleaned_data in the format:
        {menu_item_id: rating}
        """
        item_ratings = {}
        for field_name, value in self.cleaned_data.items():
            if field_name.startswith('item_rating_') and value:
                try:
                    item_id = int(field_name.split('_')[-1])
                    item_ratings[item_id] = int(value)
                except (ValueError, IndexError):
                    continue
        return item_ratings



class UserTicketCreateForm(forms.ModelForm):
    class Meta:
        model = UserSupportTicket
        fields = ['subject', 'category']
        widgets = {
            'subject': forms.TextInput(attrs={'placeholder': 'Enter ticket subject', 'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }



class UserTicketMessageForm(forms.ModelForm):
    class Meta:
        model = UserSupportMessage
        fields = ['message','image']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Reply here...', 'class': 'form-control'}),
        }
        labels = {
            'message': 'Message',
        }



from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)
    
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'address', 'avatar']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            profile.save()
            user = profile.user
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            user.save()
        return profile
    

    from django.core.exceptions import ValidationError

def validate_image(file):
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
    ext = os.path.splitext(file.name)[1]
    if not ext.lower() in valid_extensions:
        raise forms.ValidationError('Unsupported file extension.')