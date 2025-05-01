from .models import userLogin
from django.forms import forms

class userLoginForm(forms.Form):
    class Meta:
        model = userLogin
        feild = ['username','password']
        widgets = {
            'password': forms.PasswordInput(),
        }