from django.shortcuts import render
from merchant_app.models import RestaurantMenu
def home(request):
    return render(request, 'home.html')

def about(request):
    return render(request, 'about.html')

def contact(request):
    return render(request, 'contact.html')

def privacy(request):
    return render(request, 'privacy.html')

def terms(request):
    return render(request, 'Terms&Conditions.html')

def addRestaurant(request):
    return render(request, 'addRestaurant.html')

def rideWithUs(request):
    return render(request, 'rideWithUs.html')

def careers(request):
    return render(request, 'careers.html')

def ResponsibleDisclosure(request):
    return render(request, 'ResponsibleDisclosure.html')

def userLogin(request):
    return render(request, 'login.html')

def user_view_menu(request, restaurant_id):
    menus = RestaurantMenu.objects.filter(restaurant_id=restaurant_id, available=True)
    return render(request, 'user_app/view_menu.html', {'menus': menus})

