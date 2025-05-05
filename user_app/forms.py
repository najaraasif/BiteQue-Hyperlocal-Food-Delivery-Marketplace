from .models import userLogin
from django.forms import forms
from models import Order
class userLoginForm(forms.Form):
    class Meta:
        model = userLogin
        feild = ['username','password']
        widgets = {
            'password': forms.PasswordInput(),
        }

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['restaurant', 'customer_name', 'customer_contact', 'order_address', 'menu_items']
        widgets = {
            'menu_items': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: Limit menu items to available=True and filter by restaurant if needed
        self.fields['menu_items'].queryset = self.fields['menu_items'].queryset.filter(available=True)