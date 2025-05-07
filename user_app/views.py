from django.shortcuts import redirect, render
from merchant_app.models import RestaurantMenu
from user_app.models import Order
from rider_app.utils import geocode_address

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

from rider_app.utils import geocode_address

def create_order(request):
    if request.method == 'POST':
        # Get your order data from the form/request
        order_data = {
            'delivery_address': request.POST.get('delivery_address'),
            # other order fields...
        }
        
        # Create the order
        order = Order.objects.create(
            restaurant=...,
            customer_name=request.POST.get('customer_name'),
            delivery_address=request.POST.get('delivery_address'),
        )
        
        # Geocode the address
        lat, lng = geocode_address(order_data['delivery_address'])
        if lat and lng:
            order.delivery_latitude = lat
            order.delivery_longitude = lng
            order.save()
        
        return redirect('order_success')
    return render(request, 'create_order.html')
