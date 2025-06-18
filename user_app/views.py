from datetime import timedelta
from decimal import Decimal
from pyexpat.errors import messages
from statistics import mean
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

from django.views.decorators.csrf import csrf_exempt

from decimal import Decimal,ROUND_HALF_UP
from django.conf import settings
import razorpay

from decimal import Decimal
from decimal import Decimal, InvalidOperation
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect
from django.contrib import messages
from .models import Order
from merchant_app.models import Review     
from django.db.models import Avg  
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.utils.text import slugify
from .forms import OrderFeedbackForm
from merchant_app.views import send_push_to_merchant

def home(request):
    categories = RestaurantMenu.objects.values_list('category', flat=True).distinct()
    approved_restaurants = Restaurant.objects.filter(is_approved=True)
    sizes = SizeCategory.objects.all()
    items = RestaurantMenu.objects.filter(restaurant__in=approved_restaurants)

    query = request.GET.get('q')  
    if query:
        items = items.filter(name__icontains=query)

    for restaurant in approved_restaurants:
        restaurant.avg_rating = restaurant.reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    
    context = {
        'categories': categories,
        'approved_restaurants': approved_restaurants,
        'items': items,  
        'size': sizes,

    }
    return render(request, 'home.html', context)

@login_required
def dashboard_home(request):
    categories = RestaurantMenu.objects.values_list('category', flat=True).distinct()
    approved_restaurants = Restaurant.objects.filter(is_approved=True)
    sizes = SizeCategory.objects.all()
    items = RestaurantMenu.objects.filter(restaurant__in=approved_restaurants)

    query = request.GET.get('q')  
    if query:
        items = items.filter(name__icontains=query)

    for restaurant in approved_restaurants:
        restaurant.avg_rating = restaurant.reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    
    context = {
        'categories': categories,
        'approved_restaurants': approved_restaurants,
        'items': items,  
        'size': sizes,

    }
    return render(request, 'dashboard_home.html', context)



from django.shortcuts import render
from django.utils.text import slugify
from django.db.models import Avg
from .models import CustomerFeedback

def category_items(request, category_slug):
    categories = RestaurantMenu.objects.values_list('category', flat=True).distinct()
    category_lookup = {slugify(cat): cat for cat in categories}
    category = category_lookup.get(category_slug)

    if not category:
        return render(request, '404.html', status=404)

    items = RestaurantMenu.objects.filter(category=category)

    price_order = request.GET.get('price')
    if price_order == 'asc':
        items = items.order_by('price')
    elif price_order == 'desc':
        items = items.order_by('-price')

    min_rating = request.GET.get('rating')
    if min_rating:
        try:
            min_rating = int(min_rating)
            rated_restaurants = (
                CustomerFeedback.objects
                .values('restaurant')
                .annotate(avg_rating=Avg('rating'))
                .filter(avg_rating__gte=min_rating)
                .values_list('restaurant', flat=True)
            )
            items = items.filter(restaurant__in=rated_restaurants)
        except ValueError:
            pass

    for item in items:
        feedbacks = CustomerFeedback.objects.filter(item_ratings__has_key=str(item.id))
        ratings = []
        for fb in feedbacks:
            val = fb.item_ratings.get(str(item.id))
            if val:
                try:
                    ratings.append(int(val))
                except:
                    continue
        item.average_rating = round(mean(ratings), 1) if ratings else None

    context = {
        'category_name': category,
        'items': items,
        'rating_options': [5, 4, 3, 2, 1],
    }

    return render(request, 'category_items.html', context)







from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.conf import settings
import razorpay
from .models import Order,OrderMenuItem  

def checkout(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('user_login')}?next={request.path}")

    cart = request.session.get('cart', {})
    if not cart:
        return redirect('home')

    cart_items = []
    item_subtotal = Decimal('0.00')
    total_platform_gst = Decimal('0.00')
    packaging_charges = Decimal('20.00')
    delivery_fee = Decimal('0.00')
    distance_km = Decimal('0.00')
    restaurant = None

    for item_id, item_data in cart.items():
        menu_item = get_object_or_404(RestaurantMenu, id=item_id)
        quantity = item_data.get('quantity', 1)
        subtotal = menu_item.price * quantity
        gst = (menu_item.price * Decimal('0.05')) * quantity
        item_subtotal += subtotal
        total_platform_gst += gst

        if not restaurant:
            restaurant = menu_item.restaurant

        cart_items.append({
            'id': menu_item.id,
            'name': menu_item.name,
            'quantity': quantity,
            'price': menu_item.price,
            'subtotal': round(subtotal, 2),
        })

    if request.method == 'POST' and request.POST.get('create_order') == '1':
        try:
            dest_lat = request.POST.get('dest_lat')
            dest_lon = request.POST.get('dest_lon')
            delivery_fee_str = request.POST.get('calculated_delivery_fee', '0')
            distance_km_str = request.POST.get('calculated_distance_km', '0')

            try:
                delivery_fee = Decimal(delivery_fee_str).quantize(Decimal('0.00'))
                distance_km = Decimal(distance_km_str).quantize(Decimal('0.00'))
            except InvalidOperation:
                delivery_fee = Decimal('0.00')
                distance_km = Decimal('0.00')

            combined_total = item_subtotal + total_platform_gst + packaging_charges
            final_total = (combined_total + delivery_fee).quantize(Decimal('0.00'))
            razorpay_amount = int(final_total * 100)  # in paisa

            # Create the order
            order = Order.objects.create(
                user=request.user,
                restaurant=restaurant,
                landmark=request.POST.get('landmark'),
                customer_name=request.POST.get('customer_name'),
                customer_contact=request.POST.get('contact_number'),
                delivery_address=request.POST.get('delivery_address'),
                special_instructions=request.POST.get('special_instructions'),
                total=item_subtotal,
                item_gst=total_platform_gst,
                packaging_charges=packaging_charges,
                final_total=final_total,
                distance_km=distance_km,
                distance_earning=delivery_fee,
                dest_lat=Decimal(dest_lat) if dest_lat else None,
                dest_lon=Decimal(dest_lon) if dest_lon else None,
                is_paid=False
            )

            # ✅ Add each item to the OrderMenuItem model with quantity and price
            for item_id, item_data in cart.items():
                menu_item = RestaurantMenu.objects.get(id=item_id)
                quantity = item_data.get('quantity', 1)
                OrderMenuItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    quantity=quantity,
                    price=menu_item.price
                )

            # Razorpay order create
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            razorpay_order = client.order.create({
                'amount': razorpay_amount,
                'currency': 'INR',
                'payment_capture': '1',
                'notes': {
                    'order_id': str(order.id),
                    'actual_amount': str(order.final_total)
                }
            })

            order.razorpay_order_id = razorpay_order['id']
            order.save(update_fields=['razorpay_order_id'])

            return JsonResponse({
                'success': True,
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'razorpay_order_id': razorpay_order['id'],
                'razorpay_amount': razorpay_amount,
                'amount': str(order.final_total),
                'order_id': order.id
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    # GET request view rendering
    context = {
        'cart_items': cart_items,
        'packaging_charges': packaging_charges,
        'platform_gst': round(total_platform_gst, 2),
        'total_price': (item_subtotal + total_platform_gst + packaging_charges).quantize(Decimal('0.00')),
        'delivery_fee': delivery_fee,
        'restaurant': restaurant,
        'OSRM_SERVER_URL': settings.OSRM_SERVER_URL,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
        'user': request.user,
    }

    return render(request, 'checkout.html', context)






@csrf_exempt
def payment_success(request):
    if request.method == 'POST':
        print("✅ POST Received:", request.POST.dict())  # Debug

        params_dict = {
            'razorpay_order_id': request.POST.get('razorpay_order_id'),
            'razorpay_payment_id': request.POST.get('razorpay_payment_id'),
            'razorpay_signature': request.POST.get('razorpay_signature')
        }

        try:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            client.utility.verify_payment_signature(params_dict)

            order = Order.objects.get(razorpay_order_id=params_dict['razorpay_order_id'])
            if order.is_paid:
                return redirect('order_confirmation', order_id=order.id)

            # Update order
            order.razorpay_payment_id = params_dict['razorpay_payment_id']
            order.razorpay_signature = params_dict['razorpay_signature']
            order.is_paid = True
            order.save(update_fields=['razorpay_payment_id', 'razorpay_signature', 'is_paid'])

            if 'cart' in request.session:
                del request.session['cart']

            return redirect('order_confirmation', order_id=order.id)

        except razorpay.errors.SignatureVerificationError:
            messages.error(request, "Invalid payment signature.")
        except Order.DoesNotExist:
            messages.error(request, "Order not found.")
        except Exception as e:
            messages.error(request, f"Payment failed: {str(e)}")

    return redirect('checkout')





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
        if restaurant.player_id:
            send_push_to_merchant(restaurant.player_id, order.id)

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


from collections import defaultdict
from decimal import Decimal
from django.utils.timezone import timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Order

from .models import CustomerFeedback  # import if not already
from django.core.exceptions import ObjectDoesNotExist

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('restaurant__owner').prefetch_related('order_items__menu_item'),
        id=order_id,
        user=request.user
    )

    # Calculate subtotal from OrderMenuItem entries
    unique_items = []
    item_subtotal = Decimal('0.00')
    for order_item in order.order_items.all():
        subtotal = order_item.price * order_item.quantity
        unique_items.append({
            'item': order_item.menu_item,
            'quantity': order_item.quantity,
            'subtotal': subtotal
        })
        item_subtotal += subtotal

    gst_tax = item_subtotal * Decimal('0.05')
    delivery_fee = order.distance_earning + Decimal('0.60')
    packaging_charges = Decimal('20.00')
    order_total = item_subtotal + gst_tax + delivery_fee + packaging_charges

    # ✅ Check if feedback already exists
    try:
        feedback = CustomerFeedback.objects.get(order=order)
    except CustomerFeedback.DoesNotExist:
        feedback = None

    context = {
        'order': order,
        'order_items': unique_items,
        'item_subtotal': round(item_subtotal, 2),
        'gst': round(gst_tax, 2),
        'delivery_fee': round(delivery_fee, 2),
        'pakaging_charges': packaging_charges,
        'order_total': round(order_total, 2),
        'eta': order.created_at + timedelta(minutes=45),
        'rider': order.assignment.rider if hasattr(order, 'assignment') else None,
        'feedback': feedback  # ✅ pass to template
    }

    return render(request, 'order_detail.html', context)




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



from django.shortcuts import redirect

def add_to_cart(request, item_id):
    cart = request.session.get('cart', {})

    if str(item_id) in cart:
        cart[str(item_id)]['quantity'] += 1
    else:
        cart[str(item_id)] = {'quantity': 1}

    request.session['cart'] = cart
    request.session.modified = True

    return redirect(request.META.get('HTTP_REFERER', '/'))


def view_cart(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = 0

    for item_id, item_data in cart.items():
        menu_item = get_object_or_404(RestaurantMenu, id=item_id)
        quantity = item_data.get('quantity', 1)
        subtotal = menu_item.price * quantity
        total_price += subtotal

        cart_items.append({
            'id': item_id,
            'item': menu_item,  # pass full object here
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


def change_quantity(request, item_id, action):
    cart = request.session.get('cart', {})
    item_id = str(item_id)

    if item_id in cart:
        if action == 'increase':
            cart[item_id]['quantity'] += 1
        elif action == 'decrease':
            if cart[item_id]['quantity'] > 1:
                cart[item_id]['quantity'] -= 1
            else:
                del cart[item_id]

        request.session['cart'] = cart
        request.session.modified = True

    return redirect('view_cart')





def user_logout(request):
    logout(request)
    return redirect('user_login')

def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    if not order.is_paid:
        messages.warning(request, "Payment not completed yet")
        return redirect('checkout')
        
    return render(request, 'order_confirmation.html', {'order': order})


@login_required(login_url='user_login')
def order_now(request, item_id):
    menu_item = get_object_or_404(RestaurantMenu, id=item_id)

    request.session['cart'] = {
        str(menu_item.id): {'quantity': 1}
    }
    request.session.modified = True

    return redirect('checkout')

def user_view_menu(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    menus = RestaurantMenu.objects.filter(restaurant_id=restaurant_id, available=True)
    categories = menus.values_list('category', flat=True).distinct()

    category = request.GET.get('category')
    query = request.GET.get('q')

    if category:
        menus = menus.filter(category=category)
    if query:
        menus = menus.filter(name__icontains=query)

    average_rating = restaurant.reviews.aggregate(avg=Avg('rating'))['avg'] or 0

    return render(request, 'view_menu.html', {
        'menus': menus,
        'categories': categories,
        'restaurant': restaurant,
        'average_rating': round(average_rating, 1)
    })

from merchant_app.models import Restaurant, Review
from merchant_app.forms import ReviewForm

@login_required
def submit_review(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.restaurant = restaurant
            review.user = request.user
            review.save()
            return redirect('user_view_menu', restaurant_id=restaurant.id)
    else:
        form = ReviewForm()

    return render(request, 'submit_review.html', {
        'form': form,
        'restaurant': restaurant
    })




from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from .models import Order, CustomerFeedback
from .forms import ComprehensiveFeedbackForm

@login_required
def write_order_feedback(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if CustomerFeedback.objects.filter(order=order).exists():
        return redirect('order_detail', order_id=order_id)

    if request.method == 'POST':
        form = ComprehensiveFeedbackForm(request.POST, order=order)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.order = order
            feedback.customer = request.user
            feedback.restaurant = order.restaurant

            ratings = [
                feedback.item_quality,
                feedback.delivery_experience,
                feedback.restaurant_rating,
                feedback.rider_rating
            ]
            valid_ratings = [r for r in ratings if r is not None]
            if valid_ratings:
                feedback.rating = round(sum(valid_ratings) / len(valid_ratings), 1)

            feedback.item_ratings = form.get_item_ratings()

            feedback.save()
            return redirect('order_detail', order_id=order.id)
    else:
        form = ComprehensiveFeedbackForm(order=order)

    context = {
        'form': form,
        'order': order,
        'order_items': order.order_items.all(),   
    }
    return render(request, 'write_feedback.html', context)



def calculate_item_ratings():
    """Calculate average ratings for all menu items"""
    from .models import CustomerFeedback
    from merchant_app.models import RestaurantMenu
    
    feedbacks = CustomerFeedback.objects.exclude(item_ratings={})
    
    item_ratings = defaultdict(list)
    
    for feedback in feedbacks:
        for item_id, rating in feedback.item_ratings.items():
            item_ratings[item_id].append(rating)
    
    item_averages = {}
    for item_id, ratings in item_ratings.items():
        item_averages[item_id] = sum(ratings) / len(ratings)
    
    for menu_item in RestaurantMenu.objects.all():
        avg = item_averages.get(str(menu_item.id))
        if avg:
            menu_item.average_rating = avg
            menu_item.save()

    
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import UserSupportTicket, UserSupportMessage
from .forms import UserTicketCreateForm, UserTicketMessageForm
from django.contrib import messages

@login_required
def user_support(request):
    tickets = UserSupportTicket.objects.filter(user=request.user).order_by('-updated_at')
    ticket_id = request.GET.get('ticket_id')
    selected_ticket = None

    if ticket_id:
        try:
            selected_ticket = UserSupportTicket.objects.get(ticket_id=ticket_id, user=request.user)
        except UserSupportTicket.DoesNotExist:
            selected_ticket = tickets.first()
    else:
        selected_ticket = tickets.first()

    # Prepare blank forms by default
    ticket_form = UserTicketCreateForm()
    message_form = UserTicketMessageForm()
    reply_form = UserTicketMessageForm()

    # Handle ticket creation
    if request.method == 'POST' and 'create_ticket' in request.POST:
        ticket_form = UserTicketCreateForm(request.POST)
        message_form = UserTicketMessageForm(request.POST, request.FILES)

        if ticket_form.is_valid() and message_form.is_valid():
            ticket = ticket_form.save(commit=False)
            ticket.user = request.user
            ticket.save()

            initial_message = message_form.save(commit=False)
            initial_message.ticket = ticket
            initial_message.sender = request.user
            initial_message.save()

            messages.success(request, f"✅ Ticket created successfully with ID #{ticket.ticket_id}")
            return redirect(f'/user/support/?ticket_id={ticket.ticket_id}')
        else:
            messages.error(request, "❌ Please fix the form errors below.")

    # Handle reply to existing ticket
    elif request.method == 'POST' and 'reply_ticket' in request.POST:
        if selected_ticket and selected_ticket.status == 'closed':
            messages.error(request, "⚠️ This ticket is closed. You cannot reply.")
        else:
            reply_form = UserTicketMessageForm(request.POST, request.FILES)
            if reply_form.is_valid():
                reply = reply_form.save(commit=False)
                reply.ticket = selected_ticket
                reply.sender = request.user
                reply.save()

                # Update ticket timestamp
                selected_ticket.save()

                messages.success(request, "✅ Reply sent successfully.")
                return redirect(f'/user/support/?ticket_id={selected_ticket.ticket_id}')
            else:
                messages.error(request, "❌ Please fix the reply form errors below.")

    # Get messages for selected ticket
    messages_qs = selected_ticket.messages.all() if selected_ticket else UserSupportMessage.objects.none()

    context = {
        'tickets': tickets,
        'selected_ticket': selected_ticket,
        'messages': messages_qs,
        'ticket_form': ticket_form,
        'reply_form': reply_form,
        'message_form': message_form,
        'no_tickets': not tickets.exists(),
    }

    return render(request, 'partials/user_support.html', context)


