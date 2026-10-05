from datetime import timedelta
from decimal import ROUND_UP, Decimal
from statistics import mean
import logging
from django.http import HttpResponse
from django.shortcuts import render, redirect
from merchant_app.models import RestaurantMenu
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Order, CustomerFeedback, MerchantNotification
from .forms import userRegistrationForm
from rider_app.utils import calculate_osrm_distance
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login
from merchant_app.models import Restaurant, RestaurantMenu, SizeCategory
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
from django.utils.safestring import mark_safe
import json
from user_app.utils import send_sms, send_whatsapp

logger = logging.getLogger(__name__)


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

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Order, CustomerFeedback, UserSupportTicket, UserProfile

@login_required
def dashboard_home(request):
    user = request.user

    # ✅ Get User Profile
    user_profile = UserProfile.objects.filter(user=user).first()

    # ✅ Get All Orders for the User
    orders = Order.objects.filter(user=user).order_by('-created_at')

    # 📊 Stats Calculations
    total_orders = orders.count()
    ongoing_orders = orders.filter(status__in=["pending", "confirmed", "ready", "out_for_delivery"]).count()
    delivered_orders = orders.filter(status="delivered").count()

    # 🎫 Support Tickets
    support_tickets = UserSupportTicket.objects.filter(user=user, status="open")

    # 💬 Feedback
    user_feedback = CustomerFeedback.objects.filter(customer=user)


    # 📦 Prepare Context
    context = {
        'user_profile': UserProfile.objects.filter(user=user).first(),
        'orders': orders,
        'total_orders': total_orders or 0,
        'ongoing_orders': ongoing_orders or 0,
        'delivered_orders': delivered_orders or 0,
        'support_tickets': support_tickets,
        'user_feedback': user_feedback,
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

    veg_filter = request.GET.get('veg_filter')
    if veg_filter == 'veg':
        items = items.filter(veg_or_nonveg='veg')
    elif veg_filter == 'nonveg':
        items = items.filter(veg_or_nonveg='nonveg')

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
    packaging_charges = Decimal('10.00')
    delivery_fee = Decimal('0.00')
    distance_km = Decimal('0.00')
    restaurant = None

    for item_id, item_data in cart.items():
        menu_item = get_object_or_404(RestaurantMenu, id=item_id)
        quantity = item_data.get('quantity', 1)
        subtotal = menu_item.price * quantity
        gst = (menu_item.price * Decimal('0.03')) * quantity
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
            distance_km_str = request.POST.get('calculated_distance_km', '0')

            try:
                posted_distance = Decimal(distance_km_str).quantize(Decimal('0.00'))
            except InvalidOperation:
                posted_distance = Decimal('0.00')

            # Server-side delivery fee. The fee is always derived from the
            # distance using the same formula as the client (distance * 10),
            # so the posted "calculated_delivery_fee" is never trusted.
            # When the restaurant's coordinates are known the distance is
            # recomputed server-side via OSRM and the posted distance is
            # ignored entirely.
            distance_km = posted_distance
            if restaurant.lat is not None and restaurant.lon is not None and dest_lat and dest_lon:
                try:
                    server_distance = calculate_osrm_distance(
                        float(restaurant.lat), float(restaurant.lon),
                        float(dest_lat), float(dest_lon)
                    )
                    if server_distance is not None:
                        distance_km = Decimal(str(server_distance)).quantize(Decimal('0.00'))
                except Exception:
                    logger.warning(
                        "Server-side distance calculation failed for restaurant %s; using posted distance.",
                        restaurant.id, exc_info=True
                    )

            # Sanity bounds for the client-provided fallback.
            if distance_km < 0:
                distance_km = Decimal('0.00')
            if distance_km > 50:
                distance_km = Decimal('50.00')
            delivery_fee = (distance_km * Decimal('10')).quantize(Decimal('0.00'))

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

            # ✅ Add items to OrderMenuItem
            for item_id, item_data in cart.items():
                menu_item = RestaurantMenu.objects.get(id=item_id)
                quantity = item_data.get('quantity', 1)
                OrderMenuItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    quantity=quantity,
                    price=menu_item.price
                )

            # ✅ Razorpay order creation
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

            # Let the merchant dashboard know a new order arrived
            # (picked up by the polling check_notifications endpoint).
            MerchantNotification.objects.create(
                merchant=restaurant.owner,
                message=f'New order #{order.id} received',
            )

            return JsonResponse({
                'success': True,
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'razorpay_order_id': razorpay_order['id'],
                'razorpay_amount': razorpay_amount,
                'amount': str(order.final_total),
                'order_id': order.id
            })

        except Exception as e:
            logger.error("Order creation failed: %s", e, exc_info=True)
            return JsonResponse({'success': False, 'error': 'Unable to create order. Please try again.'})


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
            logger.error("Payment verification failed: %s", e, exc_info=True)
            messages.error(request, "Payment verification failed. Please contact support.")

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



from django.db import transaction, IntegrityError
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .models import UserProfile
from .forms import userRegistrationForm

def UserRegistration_view(request):
    if request.method == 'POST':
        form = userRegistrationForm(request.POST)
        if form.is_valid():
            try:
                username = form.cleaned_data['username']
                email = form.cleaned_data['email']
                name = form.cleaned_data['name']
                password = form.cleaned_data['password']
                phone_number = form.cleaned_data['number']
                whatsapp_consent = form.cleaned_data.get('whatsapp_consent', False)

                # Create the User
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=name.split()[0],
                    last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
                )

                # Update the auto-created UserProfile
                profile = user.userprofile
                profile.phone_number = phone_number
                profile.whatsapp_consent = whatsapp_consent
                profile.address = ''  # optional
                profile.save()

                # Authenticate and login
                authenticated_user = authenticate(username=username, password=password)
                if authenticated_user is not None:
                    login(request, authenticated_user)
                    return redirect('registration_success')

            except IntegrityError as e:
                logger.error("Registration integrity error: %s", e)
                if 'username' in str(e).lower():
                    form.add_error('username', 'Username already exists')
                elif 'email' in str(e).lower():
                    form.add_error('email', 'Email already exists')
                else:
                    form.add_error(None, 'Registration error. Please try again.')
            except Exception as e:
                logger.error("Registration failed: %s", e, exc_info=True)
                form.add_error(None, 'An error occurred during registration. Please try again.')
    else:
        form = userRegistrationForm()

    return render(request, 'userRegistration.html', {'form': form})








def registration_success(request):
    return render(request, 'user_registration_success.html')

def userLogin(request):
    form = AuthenticationForm(request, data=request.POST or None)
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('dashboard_home')

    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect(next_url)  # Redirect to original page (e.g., /checkout)

    return render(request, 'login.html', {'form': form, 'next': next_url})


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

    gst_tax = item_subtotal * Decimal('0.03')
    delivery_fee = order.distance_earning + Decimal('0.60')
    packaging_charges = Decimal('10.00')
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
        'rider': order.assignments.filter(status='accepted').select_related('rider__user').first().rider
                 if order.assignments.filter(status='accepted').exists() else None,
        'feedback': feedback  # ✅ pass to template
    }

    return render(request, 'order_detail.html', context)




@login_required
def profile_section(request):
    return render(request, 'profile_section.html')


@login_required
def user_active_orders(request):
    orders = Order.objects.filter(user=request.user).select_related('restaurant').prefetch_related('menu_items')
    active_statuses = ['pending', 'confirmed', 'ready', 'out_for_delivery']
    context = {
        'user': request.user,
        'orders': orders,  
        'active_orders' : orders.filter(status__in=active_statuses).order_by('-created_at'),

    }
    return render(request, 'partials/active_orders.html', context)

@login_required
def order_user_history(request):
    orders = Order.objects.filter(user=request.user).select_related('restaurant').prefetch_related('menu_items')
    context = {
        'user': request.user,
        'orders': orders,  
        'past_orders': orders.filter(status='delivered'),
    }
    return render(request, 'partials/order_history.html', context)


def add_to_cart(request, item_id):
    cart = request.session.get('cart', {})
    item = get_object_or_404(RestaurantMenu, id=item_id)
    item_restaurant_id = str(item.restaurant.id)

    if cart:
        first_item_id = next(iter(cart))
        first_item = get_object_or_404(RestaurantMenu, id=first_item_id)
        first_item_restaurant_id = str(first_item.restaurant.id)

        if item_restaurant_id != first_item_restaurant_id:
            request.session['show_single_restaurant_alert'] = True
            # Redirect back to where user came from instead of a fixed URL
            return redirect(request.META.get('HTTP_REFERER', '/'))

    if str(item_id) in cart:
        cart[str(item_id)]['quantity'] += 1
    else:
        cart[str(item_id)] = {'quantity': 1}

    request.session['cart'] = cart
    request.session.modified = True

    return redirect(request.META.get('HTTP_REFERER', '/'))


from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

@require_POST
def clear_alert_flag(request):
    if 'show_single_restaurant_alert' in request.session:
        del request.session['show_single_restaurant_alert']
        request.session.modified = True
    return JsonResponse({'status': 'ok'})


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

@login_required
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


from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UserProfile
from .forms import UserProfileForm

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import UserProfile
from .forms import UserProfileForm


@login_required
def profile_view(request):
    profile = request.user.userprofile
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save()
            
            # Update user's name fields
            user = request.user
            user.first_name = form.cleaned_data.get('first_name', '')
            user.last_name = form.cleaned_data.get('last_name', '')
            user.save()
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        # Initialize form with current data
        form = UserProfileForm(instance=profile, initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name
        })

    return render(request, 'profile_section.html', {'form': form})


@login_required
def update_avatar(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        try:
            profile = request.user.userprofile
            profile.avatar = request.FILES['avatar']
            profile.save()
            messages.success(request, 'Avatar updated successfully!')
        except Exception as e:
            messages.error(request, f'Error updating avatar: {str(e)}')
    return redirect('profile')

from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib import messages

class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'change_password.html'
    success_url = reverse_lazy('profile')
    
    def form_valid(self, form):
        messages.success(self.request, 'Your password was successfully updated!')
        return super().form_valid(form)
    

#contact us form

from django.core.mail import send_mail

def contact_form(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')

        try:
            send_mail(
                f"ZemQue Contact Form - {name}",
                f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}",
                None,
                [settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
            return JsonResponse({"status": "success", "message": "Your message has been sent successfully!"})
        except Exception as e:
            logger.error("Contact form e-mail failed: %s", e, exc_info=True)
            return JsonResponse({"status": "error", "message": "Unable to send your message right now. Please try again later."})

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)


#invoice

from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML
from .models import Order

@login_required
def download_invoice(request, order_id):

    order = get_object_or_404(Order, id=order_id, user=request.user)

    
    if order.status != 'delivered':
        return HttpResponseForbidden("Invoice is available only for delivered orders.")

    
    order_items = order.order_items.all()

   
    delivery_fee = order.distance_earning 
    delivery_fee_new = delivery_fee + Decimal('0.60')
    exact_gst = order.total * Decimal('0.03')


    

    packaging_charges = Decimal('10.00')

    order_total = (order.total + delivery_fee_new + exact_gst + packaging_charges).quantize(Decimal('0.00'))

    
    html_string = render_to_string('invoice.html', {
    'order': order,
    'order_items': order_items,
    'delivery_fee': delivery_fee_new,
    'gst': exact_gst,          
    'packaging_charges': packaging_charges,
    'order_total': order_total,
    'now': timezone.now(),
})


   
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf_file = html.write_pdf()

   
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=invoice_order_{order.id}.pdf'
    return response
