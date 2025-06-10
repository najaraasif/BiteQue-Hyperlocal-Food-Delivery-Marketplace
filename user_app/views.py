from datetime import timedelta
from decimal import Decimal
from pyexpat.errors import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from merchant_app.models import RestaurantMenu
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Order, CustomerFeedback, MerchantNotification, userRegistration
from .forms import userRegistrationForm
from rider_app.utils import calculate_osrm_distance, geocode_address
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login
from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory
from rider_app.utils import geocode_address
from django.contrib.auth import logout
from django.shortcuts import render
from django.urls import reverse



def home(request):
    categories = RestaurantMenu.objects.values_list('category', flat=True).distinct()
    approved_restaurants = Restaurant.objects.filter(is_approved=True)
    sizes = SizeCategory.objects.all()
    items = RestaurantMenu.objects.filter(restaurant__in=approved_restaurants)
    
    query = request.GET.get('q')  
    if query:
        items = items.filter(name__icontains=query)

    context = {
        'categories': categories,
        'approved_restaurants': approved_restaurants,
        'items': items,  
        'size': sizes,
    }
    return render(request, 'home.html', context)


from decimal import Decimal
from django.conf import settings



def checkout(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('user_login')}?next={request.path}")

    cart = request.session.get('cart', {})
    cart_items = []
    total_price = 0
    restaurant = None
    total_platform_gst = 0
    packaging_charges = 20

    for item_id, item_data in cart.items():
        menu_item = get_object_or_404(RestaurantMenu, id=item_id)
        quantity = item_data['quantity']
        subtotal = menu_item.price * quantity
        gst = menu_item.price * Decimal('0.05')
        total_platform_gst += gst

        total_price = subtotal 
        final_total = total_price + packaging_charges + total_platform_gst

        cart_items.append({
            'id': menu_item.id,
            'name': menu_item.name,
            'quantity': quantity,
            'subtotal': round(subtotal, 2),
            'price': menu_item.price,
            'total_price': final_total,

        })

        if not restaurant:
            restaurant = menu_item.restaurant

    if request.method == 'POST':
        dest_lat = request.POST.get('dest_lat') or None
        dest_lon = request.POST.get('dest_lon') or None

        try:
            order = Order.objects.create(
                user=request.user,
                restaurant=restaurant,
                landmark=request.POST.get('landmark'),
                customer_name=request.POST.get('customer_name'),
                customer_contact=request.POST.get('contact_number'),
                delivery_address=request.POST.get('delivery_address'),
                special_instructions=request.POST.get('special_instructions'),
                total=total_price,
                dest_lat=Decimal(dest_lat) if dest_lat else None,
                dest_lon=Decimal(dest_lon) if dest_lon else None
            )

            for item in cart_items:
                menu_item = RestaurantMenu.objects.get(id=item['id'])
                order.menu_items.add(menu_item)

            if dest_lat and dest_lon and restaurant.lat and restaurant.lon:
                try:
                    # Use OSRM with fallback to Haversine
                    distance_km = calculate_osrm_distance(
                        float(restaurant.lat),
                        float(restaurant.lon),
                        float(dest_lat),
                        float(dest_lon),
                    )
                    order.distance_km = Decimal(str(distance_km)).quantize(Decimal('0.00'))
                    order.distance_earning = order.distance_km * Decimal('10')
                    order.save(update_fields=['distance_km', 'distance_earning'])
                except Exception as e:
                    messages.error(request, f"Failed to calculate road distance: {str(e)}")

            request.session['cart'] = {}
            return redirect('order_confirmation', order_id=order.id)

        except Exception as e:
            messages.error(request, f"Error creating order: {str(e)}")
            return redirect('checkout')

    context = {
        'cart_items': cart_items,
        'packaging_charges': packaging_charges,
        'platform_gst': round(total_platform_gst, 2),
        'total_price': total_price,
        'restaurant': restaurant,
        'OSRM_SERVER_URL': settings.OSRM_SERVER_URL,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    }
    return render(request, 'checkout.html', context)



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

def UserRegistration_view(request):
    if request.method == 'POST':
        form = userRegistrationForm(request.POST)
        if form.is_valid():
            try:
                password = form.cleaned_data['password']
                retype_password = form.cleaned_data['retypePassword']
                if password != retype_password:
                    form.add_error('retypePassword', 'Passwords do not match.')
                else:
                    user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password']
                    )
                    userRegistration.objects.create(
                        username=user,  # ✅ Assign the User object here
                        name=form.cleaned_data['name'],
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password']

                )

                    return redirect('user_registration_success')
            except IntegrityError:
                form.add_error('username', 'Username already exists. Please choose a different one.')
    else:
        form = userRegistrationForm()

    return render(request, 'userRegistration.html', {'form': form})

def registration_success(request):
    return render(request, 'user_registration_success.html')

def user_view_menu(request, restaurant_id):
    menus = RestaurantMenu.objects.filter(restaurant_id=restaurant_id, available=True)
    return render(request, 'view_menu.html', {'menus': menus})


@login_required
def create_order(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect('user_login')
        restaurant_id = Restaurant.POST.get(restaurant_id)
        restaurant=Restaurant.objects.get(id=restaurant_id)

        order_data = {
            'delivery_address': request.POST.get('delivery_address'),
        }
        
        order = Order.objects.create(
            user=request.user,
            restaurant=restaurant,
            customer_name=request.POST.get('customer_name'),
            landmark=request.POST.get('landmark'),
            delivery_address=request.POST.get('delivery_address'),
            customer_contact = request.POST.get('customer_contact'),
            items =  request.POST.get('menu_items'),
            total =  request.POST.get('total'),

        )
        menu_items = request.POST.getlist('menu_items')
        order.menu_items.set(menu_items)
        
        lat, lng = geocode_address(order_data['delivery_address'])
        if lat and lng:
            order.delivery_latitude = lat
            order.delivery_longitude = lng
            order.save()
        
        return redirect('')


def userLogin(request):
    form = AuthenticationForm(request, data=request.POST or None)
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('dashboard_home')

    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect(next_url)  # Redirect to original page (e.g., /checkout)

    return render(request, 'login.html', {'form': form, 'next': next_url})


@login_required
def user_profile(request):
    return render(request, 'dashboard_home.html')

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order.objects.select_related(
        'restaurant__owner'
    ).prefetch_related(
        'menu_items'
    ), id=order_id, user=request.user)

    delivery_fee = order.distance_earning + Decimal('0.60')
    gst_tax = order.total * Decimal('0.05')
    pakaging_charges = 20
    order_total = float(order.total + delivery_fee + gst_tax + pakaging_charges)

    context = {
        'order': order,
        'gst': round(gst_tax, 2),
        'delivery_fee': delivery_fee,
        'pakaging_charges': pakaging_charges,
        'order_total': round(order_total, 2),
        'eta': order.created_at + timedelta(minutes=45),
        'rider': order.assignment.rider if hasattr(order, 'assignment') else None
    }
    return render(request, 'order_detail.html', context)

@login_required
def dashboard_home(request):
    #menus = RestaurantMenu.objects.filter(restaurant_id=restaurant_id, available=True)
    return render(request, 'dashboard_home.html')

def profile_section(request):
    return render(request, 'profile_section.html')


def user_active_orders(request):
    orders = Order.objects.filter(user=request.user).select_related('restaurant').prefetch_related('menu_items')
    active_statuses = ['pending', 'confirmed', 'ready', 'out_for_delivery']
    context = {
        'user': request.user,
        'orders': orders,  
        'active_orders' : orders.filter(status__in=active_statuses).order_by('-created_at'),

    }
    return render(request, 'partials/active_orders.html', context)

def order_user_history(request):
    orders = Order.objects.filter(user=request.user).select_related('restaurant').prefetch_related('menu_items')
    context = {
        'user': request.user,
        'orders': orders,  
        'past_orders': orders.filter(status='delivered'),
    }
    return render(request, 'partials/order_history.html', context)

def support(request):
    return render(request, 'partials/support.html')


def submit_feedback(request, order_id=None, restaurant_id=None):
    # Defer the import to avoid circular import
    from merchant_app.models import Restaurant
    from .models import Order  # Assuming you have an Order model

    # Handle the case where order_id or restaurant_id is provided
    if order_id:
        order = get_object_or_404(Order, id=order_id)
        restaurant = order.restaurant  # Assuming Order has a relationship with Restaurant
    elif restaurant_id:
        restaurant = get_object_or_404(Restaurant, id=restaurant_id)
        order = None
    else:
        return HttpResponse("Invalid Feedback Request", status=400)

    # Handle feedback submission
    if request.method == 'POST':
        from .forms import CustomerFeedbackForm  # Import form here as well
        form = CustomerFeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.customer = request.user
            feedback.restaurant = restaurant
            feedback.order = order
            feedback.save()

            MerchantNotification.objects.create(
                merchant=restaurant.owner,  
                message=f'New feedback from {request.user} for {restaurant.name}'
            )

            return redirect('feedback_thanks')  
    else:
        from .forms import CustomerFeedbackForm
        form = CustomerFeedbackForm(initial={'restaurant': restaurant, 'order': order})

    return render(request, 'submit.feedback.html', {'form': form, 'restaurant': restaurant, 'order': order})



def feedback_thanks(request):
    return render(request, 'feedback_thanks.html')



def add_to_cart(request, item_id):
    menu_item = get_object_or_404(RestaurantMenu, id=item_id)

    cart = request.session.get('cart', {})

    if str(item_id) in cart:
        cart[str(item_id)]['quantity'] += 1
    else:
        cart[str(item_id)] = {'quantity': 1}

    request.session['cart'] = cart
    request.session.modified = True

    return redirect('home')


def view_cart(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = 0

    for item_id, item_data in cart.items():
        menu_item = get_object_or_404(RestaurantMenu, id=item_id)
        quantity = item_data['quantity']
        subtotal = menu_item.price * quantity
        total_price += subtotal

        cart_items.append({
            'item': menu_item,
            'quantity': quantity,
            'subtotal': subtotal,
        })

    return render(request, 'your_cart.html', {
        'cart_items': cart_items,
        'total': total_price,
    })


def remove_from_cart(request, item_id):
    cart = request.session.get('cart', {})

    if str(item_id) in cart:
        del cart[str(item_id)]
        request.session['cart'] = cart
        request.session.modified = True

    return redirect('view_cart')


def user_logout(request):
    logout(request)
    return redirect('user_login')

def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'order_confirmation.html', {'order': order})



