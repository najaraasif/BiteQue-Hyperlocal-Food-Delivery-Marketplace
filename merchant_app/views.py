from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from .forms import MerchantRegistrationForm, RestaurantForm, RestaurantMenuForm, BankAccountForm
from .models import merchantRegistration, Restaurant, RestaurantMenu, BankAccount, MerchantPayment, MerchantEarning
from django.db import IntegrityError
from django.contrib import messages
from user_app.models import Order, CustomerFeedback, MerchantNotification, OrderMenuItem
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from django.utils.timezone import now, timedelta
from datetime import datetime, timedelta
import json
import os
from django.http import JsonResponse
from .signals import send_mailersend_reset_email
from rider_app.models import OrderAssignment, Rider
import logging
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse
import csv


# for token lund genertation
from django.contrib.auth.tokens import default_token_generator
from django.utils import http
from django.utils.encoding import force_bytes

from django.urls import reverse
from django.conf import settings
import requests
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def save_player_id(request):
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            data = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON body'}, status=400)
        player_id = data.get('player_id')
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            restaurant.player_id = player_id
            restaurant.save()
            return JsonResponse({'status': 'success'})
        except Restaurant.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Restaurant not found'}, status=404)
    return JsonResponse({'status': 'unauthorized'}, status=401)

@login_required
def check_notifications(request):
    notif = MerchantNotification.objects.filter(merchant=request.user, is_read=False).first()
    if notif:
        notif.is_read = True
        notif.save()
        return JsonResponse({"notify": True, "message": notif.message})
    return JsonResponse({"notify": False})

def merchant_register_view(request):
    if request.method == 'POST':
        form = MerchantRegistrationForm(request.POST)
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

                    merchantRegistration.objects.create(
                        username=user,  # ✅ Assign the User object here
                        number=form.cleaned_data['number'],
                        name=form.cleaned_data['name']  
                )

                    return redirect('merchant_register_success')
            except IntegrityError:
                form.add_error('username', 'Username already exists. Please choose a different one.')
    else:
        form = MerchantRegistrationForm()

    return render(request, 'merchantRegister.html', {'form': form})




def merchant_register_success(request):
    return render(request, 'merchant_register_success.html')


def merchant_login(request):
    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect('post-login-redirect') 

    return render(request, 'merchantLogin.html', {'form': form})

def merchant_approval(request):
    return render(request, 'merchant_approval.html')

@login_required
def post_login_redirect(request):
    try:
        restaurant = Restaurant.objects.get(owner=request.user)  
        if restaurant.is_approved:
            return redirect('merchant_dashboard')
        else:
            return render(request, 'awaitingApproval.html')
    except Restaurant.DoesNotExist:
        return redirect('add_restaurant')


@login_required
def add_restaurant_view(request):
    merchant = get_object_or_404(merchantRegistration, username=request.user)

    # If merchant is NOT approved, show approval pending message
    if not merchant.is_approved:
        return redirect('merchant_approval')  # A simple page explaining the status

    # If merchant is approved, handle restaurant form submission
    if request.method == 'POST':
        form = RestaurantForm(request.POST)
        if form.is_valid():
            restaurant = form.save(commit=False)
            restaurant.owner = request.user
            restaurant.save()
            return redirect('restaurant_success')
    else:
        form = RestaurantForm()

    return render(request, 'addRestaurant.html', {'form': form})



@login_required
def restaurant_success(request):
    return render(request, 'restaurant_success.html')

@login_required
def awaiting_approval_view(request):
    return render(request, 'awaitingApproval.html')

@login_required
def merchant_dashboard(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)

    if not restaurant.is_approved:
        return redirect('awaiting-approval')

    # Toggle availability
    if request.method == 'POST' and 'toggle_availability' in request.POST:
        restaurant.is_available = not restaurant.is_available
        restaurant.save()
        return redirect('merchant_dashboard')

    today = timezone.localdate()
    now = timezone.now()

    # Active orders
    pending_orders = Order.objects.filter(restaurant=restaurant, status='pending').prefetch_related('order_items__menu_item').order_by('-created_at')
    confirmed_orders = Order.objects.filter(restaurant=restaurant, status='confirmed')

    # Completed orders today
    completed_today_qs = Order.objects.filter(
        restaurant=restaurant,
        status='delivered',
        created_at__date=today
    )

    order_history = completed_today_qs  # This is now a queryset, suitable for template display
    total_orders_today = completed_today_qs.count()
    total_revenue_today = completed_today_qs.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    net_revenue = total_revenue_today * Decimal('0.84')  # Restaurant earns 80%

    # Weekly performance
    one_week_ago = now - timedelta(days=7)
    weekly_orders = Order.objects.filter(
        restaurant=restaurant,
        status='delivered',
        created_at__gte=one_week_ago
    )
    weekly_revenue = weekly_orders.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    net_week_revenue = weekly_revenue * Decimal('0.84')

    # Safe calculation of performance rate
    performance_rate = ((net_revenue / net_week_revenue) * 100) if net_revenue > 0 else Decimal('0.00')

    from collections import defaultdict

    order_item_quantities = defaultdict(dict)

    order_items_qs = OrderMenuItem.objects.filter(
        order__in=pending_orders
    ).select_related('order', 'menu_item')

    for oi in order_items_qs:
        order_item_quantities[oi.order_id][oi.menu_item_id] = oi.quantity
    # Top 5 items by quantity sold
    top_items = OrderMenuItem.objects.filter(
        order__restaurant=restaurant
    ).values('menu_item__name').annotate(
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:5]

    # Prepare labels and data
    top_items_names = [item['menu_item__name'] for item in top_items]
    top_items_quantities = [item['total_quantity'] for item in top_items]

    return render(request, 'merchantDashboard.html', {
        'restaurant': restaurant,
        'Pending_orders': pending_orders,
        'Confirmed_orders': confirmed_orders,
        'total_confirmed_today': completed_today_qs,
        'Order_history': order_history,
        'total_orders_today': total_orders_today,
        'total_revenue_today': round(total_revenue_today, 2),
        'net_revenue': round(net_revenue, 2),
        'performance_rate': round(performance_rate, 1),
        'top_items_names': json.dumps(top_items_names),
        'top_items_quantities': json.dumps(top_items_quantities),
        'top_items': top_items,
        'order_item_quantities': order_item_quantities,
    })

def send_push_to_merchant(player_id, order_id):
    rest_api_key = os.environ.get('ONESIGNAL_REST_API_KEY', '')
    if not player_id or not rest_api_key:
        return False
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": rest_api_key,
    }
    payload = {
        "app_id": os.environ.get('ONESIGNAL_APP_ID', '73976d16-6896-41dd-a6e4-49e0d80edccc'),
        "include_player_ids": [player_id],
        "headings": {"en": "New Order Received"},
        "contents": {"en": f"You have a new order #{order_id}"},
        "url": f"https://yourdomain.com/merchant/orders/{order_id}/"
    }
    try:
        response = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            data=json.dumps(payload),
            timeout=10,
        )
        return response.ok
    except requests.RequestException as exc:
        logger.warning("OneSignal push failed for order %s: %s", order_id, exc)
        return False


@login_required
def merchant_order_view(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    order_date = request.GET.get('order_date')

    # Pending and Confirmed Orders remain unchanged
    pending_orders = Order.objects.filter(
        restaurant=restaurant,
        status='pending'
    ).order_by('-created_at')

    confirmed_orders = Order.objects.filter(
        restaurant=restaurant,
        status='confirmed'
    ).order_by('-created_at')

    # Filter order history
    order_history = Order.objects.filter(restaurant=restaurant).exclude(
        Q(status='pending') | Q(status='confirmed')
    )

    if order_date:
        try:
            date_obj = datetime.strptime(order_date, '%Y-%m-%d').date()
            order_history = order_history.filter(created_at__date=date_obj)
        except ValueError:
            pass  # Invalid date format

    order_history = order_history.order_by('-created_at')

    # Pagination
    paginator = Paginator(order_history, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'restaurant': restaurant,
        'pending_orders': pending_orders,
        'confirmed_orders': confirmed_orders,
        'order_history': page_obj,  # Paginated history
        'is_paginated': page_obj.has_other_pages(),
        'page_obj': page_obj,
        'order_date': order_date,
    }

    return render(request, 'merchantOrders.html', context)

@login_required
def download_filtered_orders(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    order_date = request.GET.get('order_date')

    if not order_date:
        return HttpResponse("Date parameter is missing.", status=400)

    try:
        date_obj = datetime.strptime(order_date, '%Y-%m-%d').date()
    except ValueError:
        return HttpResponse("Invalid date format.", status=400)

    orders = Order.objects.filter(
        restaurant=restaurant,
        created_at__date=date_obj
    ).exclude(status__in=['pending', 'confirmed']).order_by('-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="orders_{order_date}.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'Customer', 'Contact', 'Items', 'Total', 'Address', 'Status', 'Date'])

    for order in orders:
        item_names = ', '.join(item.name for item in order.menu_items.all())
        writer.writerow([
            order.id,
            order.customer_name,
            order.customer_contact,
            item_names,
            order.total,
            order.delivery_address,
            order.get_status_display(),
            order.created_at.strftime("%d %b, %Y %H:%M")
        ])

    return response
logger = logging.getLogger(__name__)

@login_required
def confirm_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, restaurant__owner=request.user)
    if order.status == 'pending':
        order.status = 'confirmed'
        order.save()
    else:
        messages.error(request, f"Order #{order.id} cannot be confirmed (current status: {order.status}).")
    return redirect('merchant_orders')

@login_required
def mark_order_ready(request, order_id):
    order = get_object_or_404(Order, id=order_id, restaurant__owner=request.user)

    if order.status == 'confirmed':
        order.status = 'ready'
        order.save()

    if order.status == 'ready':
        # Refresh the pending assignment list without touching a rider
        # who has already accepted this order.
        OrderAssignment.objects.filter(order=order).exclude(status='accepted').delete()

        riders = Rider.objects.filter(
            is_available=True, is_approved=True
        ).exclude(orderassignment__order=order)
        logger.info(f"Found {riders.count()} riders for order {order.id}")

        for rider in riders:
            OrderAssignment.objects.create(
                rider=rider,
                order=order,
                status='pending'
            )
            logger.info(f"Created assignment for rider {rider.id}")
    else:
        messages.error(request, f"Order #{order.id} cannot be marked ready (current status: {order.status}).")

    return redirect('merchant_orders')

@login_required
def add_item(request):
    if request.method == 'POST':
        form = RestaurantMenuForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.restaurant = get_object_or_404(Restaurant, owner=request.user)
            item.save()
            return redirect('menu_dashboard')  
    else:
        form = RestaurantMenuForm()
    return render(request, 'add_menu.html', {'form': form})


@login_required
def edit_item(request, item_id):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    item = get_object_or_404(RestaurantMenu, id=item_id, restaurant=restaurant)

    if request.method == 'POST':
        form = RestaurantMenuForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            return redirect('menu_dashboard')  # Redirect to the menu display page
    else:
        form = RestaurantMenuForm(instance=item)

    return render(request, 'edit_item.html', {'form': form, 'item': item})

@login_required
def menu_dashboard_view(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    items = RestaurantMenu.objects.filter(restaurant=restaurant)
    query = request.GET.get('q')  
    category_filter = request.GET.get('category')  

    if query:
        items = items.filter(name__icontains=query)
    if category_filter:
        items = items.filter(category=category_filter)

    edit_id = request.POST.get('edit_id') or request.GET.get('edit')

    if edit_id:
        item = get_object_or_404(RestaurantMenu, pk=edit_id, restaurant__owner=request.user)
        form = RestaurantMenuForm(request.POST or None, request.FILES or None, instance=item)
        is_editing = True
    else:
        item = None
        form = RestaurantMenuForm(request.POST or None, request.FILES or None)
        is_editing = False

    if request.method == 'POST':
        if form.is_valid():
            new_item = form.save(commit=False)
            new_item.restaurant = restaurant
            new_item.save()
            return redirect('menu_dashboard')  

    categories = RestaurantMenu.objects.values_list('category', flat=True).distinct()

    return render(request, 'menu_list.html', {
        'items': items,
        'form': form,
        'is_editing': is_editing,
        'item': item,
        'categories': categories,  
    })

@login_required
def bank_account_list(request):
    # Fetch all bank accounts for the current merchant
    accounts = BankAccount.objects.filter(merchant=request.user)

    # Separate approved and pending accounts for UI clarity (optional)
    approved_accounts = accounts.filter(is_approved=True)
    pending_accounts = accounts.filter(is_approved=False)

    context = {
        'accounts': accounts,
        'approved_accounts': approved_accounts,
        'pending_accounts': pending_accounts,
    }
    return render(request, 'bank_account_list.html', context)


@login_required
def add_bank_account(request):
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.merchant = request.user
            account.save()
        
            return redirect('bank_account_list')
        
    else:
        form = BankAccountForm()
    return render(request, 'add_bank_account.html', {'form': form})

@login_required
def edit_bank_account(request, account_id):
    account = get_object_or_404(BankAccount, id=account_id, merchant=request.user)
    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            return redirect('bank_account_list')
    else:
        form = BankAccountForm(instance=account)
    return render(request, 'edit_bank_account.html', {'form': form, 'account': account})

@login_required
def delete_bank_account(request, account_id):
    account = get_object_or_404(BankAccount, id=account_id, merchant=request.user)

    if request.method == 'POST':
        account.delete()
        return redirect('bank_account_list')  # or wherever your list view is

    return render(request, 'confirm_bank_account_delete.html', {'account': account})


@login_required
def merchant_payment_section_view(request):
    merchant = request.user
    restaurant = get_object_or_404(Restaurant, owner=merchant)

    # Get all completed orders for this merchant's restaurant
    orders = Order.objects.filter(restaurant=restaurant, status='delivered')

    # Net (all-time) revenue
    total_revenue = orders.aggregate(total=Sum('total'))['total'] or 0

    # Weekly revenue
    one_week_ago = timezone.now() - timedelta(days=7)
    weekly_orders = orders.filter(created_at__gte=one_week_ago)
    weekly_revenue = weekly_orders.aggregate(total=Sum('total'))['total'] or 0

    # Merchant share is 80%
    merchant_share = total_revenue * Decimal('0.84')
    weekly_merchant_share = weekly_revenue * Decimal('0.84')
    weekly_platform_share = weekly_revenue * Decimal('0.16')  # Fixed this logic, platform gets 20%

    # Paid amount so far
    payments = MerchantPayment.objects.filter(merchant=merchant).order_by('-payment_date')
    paid_amount = payments.aggregate(total=Sum('amount_paid'))['total'] or 0

    # Pending payout to merchant
    pending_amount = merchant_share - paid_amount

    # === Store to MerchantEarning (Non-editable record) ===
    MerchantEarning.objects.update_or_create(
        merchant=merchant,
        restaurant=restaurant,
        defaults={
            'net_sales': total_revenue,
            'weekly_sales': weekly_revenue,
            'amount_paid': paid_amount,
            'amount_pending': pending_amount,
        }
    )

    # === Context for display ===
    context = {
        'total_revenues': total_revenue,
        'weekly_revenue': weekly_revenue,
        'merchant_share': merchant_share,
        'weekly_merchant_share': weekly_merchant_share,
        'weekly_platform_share': weekly_platform_share,
        'paid_amount': paid_amount,
        'pending_amount': pending_amount,
        'subscription_fee': 1000,
        'payments': payments,
    }

    return render(request, 'merchantPaymentSection.html', context)


    # Reports section...


@login_required
def merchant_revenue_report(request):
    merchant = request.user
    restaurant = get_object_or_404(Restaurant, owner=merchant)
    today = datetime.today()
    start_30_days = today - timedelta(days=30)
    start_7_days = today - timedelta(days=7)

    orders = Order.objects.filter(restaurant=restaurant, status='delivered')

    total_revenue = orders.aggregate(total=Sum('total'))['total'] or 0 
    total_net_revenue = total_revenue * Decimal('0.84')  # Restaurant earns 84%

    today_revenue = orders.filter(status='delivered',created_at__date=today.date()).aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
    total_today_revenue = today_revenue * Decimal('0.84')  # Restaurant earns 84%

    week_revenue = orders.filter(created_at__gte=start_7_days).aggregate(Sum('total'))['total__sum'] or 0
    total_week_revenue = total_revenue * Decimal('0.84')  # Restaurant earns 84%

    month_revenue = orders.filter(created_at__gte=start_30_days).aggregate(Sum('total'))['total__sum'] or 0
    total_month_revenue = total_revenue * Decimal('0.84')  # Restaurant earns 84%


    trend_labels = []
    trend_data = []
    
    last_30_days = [today - timedelta(days=i) for i in range(29, -1, -1)]

    labels = [day.strftime('%b %d') for day in last_30_days]
    
    data = []
    for day in last_30_days:
        total = orders.filter(created_at__date=day).aggregate(total=Sum('total'))['total'] or 0
        data.append(float(total))

    for i in range(30):
        day = today - timedelta(days=i)
        trend_labels.insert(0, day.strftime('%b %d'))
        daily_total = orders.filter(created_at__date=day.date()).aggregate(Sum('total'))['total__sum'] or 0
        trend_data.insert(0, float(daily_total))

    context = {
        'total_revenue': total_net_revenue,
        'today_revenue': total_today_revenue,
        'week_revenue': total_week_revenue,
        'month_revenue': total_month_revenue,
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data),
    }
    

    return render(request, 'revenue_report.html', context)


@login_required
def order_reports(request):
    user = request.user
    today = timezone.localdate()
    last_7_days = today - timedelta(days=6)
    last_30_days = today - timedelta(days=29)

    merchant_restaurants = Restaurant.objects.filter(owner=user)

    orders = Order.objects.filter(restaurant__in=merchant_restaurants)

    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    thirty_day_orders_qs = orders.filter(created_at__date__range=(last_30_days, today))
    thirty_day_orders = thirty_day_orders_qs.count()
    thirty_day_revenue = thirty_day_orders_qs.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    seven_day_orders_qs = orders.filter(created_at__date__range=(last_7_days, today))
    seven_day_orders = seven_day_orders_qs.count()
    seven_day_revenue = seven_day_orders_qs.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    today_orders_qs = orders.filter(created_at__date=today, status='delivered')
    today_orders = today_orders_qs.count()
    today_revenue = today_orders_qs.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    chart_labels = []
    chart_data = []

    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        label = day.strftime('%d %b')
        count = orders.filter(created_at__date=day).count()
        chart_labels.append(label)
        chart_data.append(count)

    context = {
        'total_orders': total_orders,
        'total_revenue': round(total_revenue, 2),
        'thirty_day_orders': thirty_day_orders,
        'thirty_day_revenue': round(thirty_day_revenue, 2),
        'seven_day_orders': seven_day_orders,
        'seven_day_revenue': round(seven_day_revenue, 2),
        'today_orders': today_orders,
        'today_revenue': round(today_revenue, 2),
        'order_chart_labels': json.dumps(chart_labels),
        'order_chart_data': json.dumps(chart_data),
    }

    return render(request, 'order_reports.html', context)


@login_required
def customer_feedback(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)

    show_all = request.GET.get('all') == '1'

    if show_all:
        reviews = restaurant.reviews.select_related('user').order_by('-created_at')
    else:
        reviews = restaurant.reviews.select_related('user').order_by('-created_at')[:10]

    feedbacks = CustomerFeedback.objects.filter(
        restaurant=restaurant
    ).select_related('order', 'customer').order_by('-created_at')

    context = {
        'restaurant': restaurant,
        'reviews': reviews,
        'feedbacks': feedbacks,
        'show_all_reviews': show_all,
    }
    return render(request, 'customer_feedback.html', context)

def merchant_password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)  # Or your custom Merchant model
            token = default_token_generator.make_token(user)
            uid = http.urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = request.build_absolute_uri(
                reverse('merchant-password-reset-confirm', kwargs={'uidb64': uid, 'token': token})
            )

            send_mailersend_reset_email(user.email, reset_link)
        except User.DoesNotExist:
            pass
        # Same response whether or not the e-mail exists, to avoid
        # revealing which addresses are registered.
        messages.success(request, "If an account exists for this email, a reset link has been sent.")
        return redirect('password_reset_sent')

    return render(request, 'password_reset_form.html')

def password_reset_sent_view(request):
    return render(request, 'password_reset_sent.html')


def merchant_password_reset_confirm(request, uidb64, token):
    User = get_user_model()
    try:
        uid = http.urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('password')
            user.set_password(new_password)
            user.save()
            messages.success(request, "Password reset successful.")
            return redirect('merchant_login')
        return render(request, 'password_reset_confirm.html', {'validlink': True})
    else:
        return render(request, 'password_reset_confirm.html', {'validlink': False})

from .models import Ticket, TicketMessage
from .forms import TicketCreateForm, TicketMessageForm

@login_required
def merchant_support(request):
    tickets = Ticket.objects.filter(merchant=request.user).order_by('-updated_at')
    ticket_id = request.GET.get('ticket_id')

    # Select the ticket or default to first
    if ticket_id:
        try:
            selected_ticket = Ticket.objects.get(ticket_id=ticket_id, merchant=request.user)
        except Ticket.DoesNotExist:
            selected_ticket = tickets.first()
    else:
        selected_ticket = tickets.first()

    # Handle new ticket creation
    if request.method == 'POST' and 'create_ticket' in request.POST:
        ticket_form = TicketCreateForm(request.POST)
        message_form = TicketMessageForm(request.POST, request.FILES)  # ✅ Include request.FILES here
        if ticket_form.is_valid() and message_form.is_valid():
            ticket = ticket_form.save(commit=False)
            ticket.merchant = request.user
            ticket.save()
            initial_message = message_form.save(commit=False)
            initial_message.ticket = ticket
            initial_message.sender = request.user
            initial_message.save()
            messages.success(request, f"Ticket created successfully with ID {ticket.ticket_id}")
            return redirect('support_portal')
    else:
        ticket_form = TicketCreateForm()
        message_form = TicketMessageForm()

    # Handle reply submission with status check
    if request.method == 'POST' and 'reply_ticket' in request.POST:
        if selected_ticket.status == 'closed':
            messages.error(request, "Cannot reply to a closed ticket.")
            reply_form = TicketMessageForm()  # show empty form
        else:
            reply_form = TicketMessageForm(request.POST, request.FILES)  # ✅ Also fix here
            if reply_form.is_valid():
                reply = reply_form.save(commit=False)
                reply.ticket = selected_ticket
                reply.sender = request.user
                reply.save()
                selected_ticket.save()  # trigger updated_at update
                messages.success(request, "Reply sent successfully.")
                return redirect(f'/merchant/support/?ticket_id={selected_ticket.ticket_id}')
    else:
        reply_form = TicketMessageForm()

    messages_qs = selected_ticket.messages.all() if selected_ticket else []

    context = {
        'tickets': tickets,
        'selected_ticket': selected_ticket,
        'messages': messages_qs,
        'ticket_form': ticket_form,
        'reply_form': reply_form,
        'message_form': message_form,
    }

    return render(request, 'merchant_support.html', context)

from django.template.loader import get_template
from django.http import HttpResponse
from xhtml2pdf import pisa
import io

@login_required
def export_payments_pdf(request):
    merchant = request.user
    restaurant = get_object_or_404(Restaurant, owner=merchant)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    payments = MerchantPayment.objects.filter(merchant=merchant)

    if start_date:
        payments = payments.filter(payment_date__date__gte=start_date)
    if end_date:
        payments = payments.filter(payment_date__date__lte=end_date)

    template_path = 'merchantPaymentPDF.html'
    context = {'payments': payments, 'restaurant': restaurant}

    # Render the template
    template = get_template(template_path)
    html = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Payment_History_{restaurant.name}.pdf"'

    pisa_status = pisa.CreatePDF(io.BytesIO(html.encode('UTF-8')), dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors with PDF generation <pre>' + html + '</pre>')
    return response


from django.template.loader import render_to_string

@login_required
def export_orders_pdf(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    restaurant_ids = Restaurant.objects.filter(owner=request.user).values_list('id', flat=True)
    orders = Order.objects.filter(restaurant_id__in=restaurant_ids)

    if start_date and end_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            orders = orders.filter(created_at__date__range=[start_date, end_date])
        except ValueError:
            pass  # fallback to all orders if date parsing fails

    html = render_to_string('merchantOrderPDF.html', {'orders': orders})
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="orders_report.pdf"'
    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('Error generating PDF', status=500)
    return response
