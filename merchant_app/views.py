from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.models import User

from rider_app.models import OrderAssignment, Rider
from .forms import merchantRegistrationForm, RestaurantForm, RestaurantMenuForm, BankAccountForm, UpdateOrderStatusForm
from .models import merchantRegistration, Restaurant, RestaurantMenu, BankAccount
from django.db import IntegrityError
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.apps import apps
from user_app.models import Order
import logging
logger = logging.getLogger(__name__)




def merchant_register_view(request):
    if request.method == 'POST':
        form = merchantRegistrationForm(request.POST)
        if form.is_valid():
            try:
                password = form.cleaned_data['password']
                retype_password = form.cleaned_data['retypePassword']
                if password != retype_password:
                    form.add_error('retypePassword', 'Passwords do not match.')
                else:
                    merchantRegistration.objects.create(
                        username=form.cleaned_data['username'],
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password'],
                        retypePassword=form.cleaned_data['retypePassword'],
                        number=form.cleaned_data['number'],
                        name=form.cleaned_data['name']
                    )
                    return redirect('merchant_register_success')
            except IntegrityError:
                form.add_error('username', 'Username already exists. Please choose a different one.')
    else:
        form = merchantRegistrationForm()

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
    return render(request, 'awaitingapproval.html')

@login_required
def merchant_dashboard(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    if not restaurant.is_approved:
        return redirect('awaiting-approval')
    
    # Toggle availability
    if request.method == 'POST' and 'toggle_availability' in request.POST:
        restaurant.is_available = not restaurant.is_available
        restaurant.save()

    # Show orders only if available
    orders = Order.objects.filter(restaurant=restaurant, status='pending') if restaurant.is_available else []

    return render(request, 'merchantDashboard.html', {
        'restaurant': restaurant,
        'orders': orders
    })


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Restaurant, Order  # Adjust the import as per your app structure

def get_merchant_restaurant(user):
    return Restaurant.objects.filter(owner=user).first()

@login_required
def merchant_orders(request):
    restaurant = get_merchant_restaurant(request.user)
    if not restaurant:
        return redirect('dashboard')  # fallback if merchant has no restaurant

    # Categorize orders
    new_orders = Order.objects.filter(restaurant=restaurant, status='pending')
    confirmed_orders = Order.objects.filter(restaurant=restaurant, status='active')
    order_history = Order.objects.filter(restaurant=restaurant, status__in=['completed', 'cancelled'])

    context = {
        'new_orders': new_orders,
        'confirmed_orders': confirmed_orders,
        'order_history': order_history
    }
    return render(request, 'merchantOrders.html', context)

@login_required
def confirm_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, restaurant__owner=request.user)
    if order.status == 'pending':
        order.status = 'active'
        order.save()
    return redirect('merchant_orders')


# merchant_app/views.py
import logging
logger = logging.getLogger(__name__)

def mark_order_ready(request, order_id):
    order = get_object_or_404(Order, id=order_id, restaurant__owner=request.user)
    if order.status == 'active':
        # Delete existing assignments to avoid duplicates
        OrderAssignment.objects.filter(order=order).delete()
        
        # Assign to ALL available & approved riders
        riders = Rider.objects.filter(is_available=True, is_approved=True)
        logger.info(f"Found {riders.count()} riders for order {order.id}")  # Debug line
        
        for rider in riders:
            OrderAssignment.objects.create(
                rider=rider,
                order=order,
                status='pending'
            )
            logger.info(f"Created assignment for rider {rider.id}")  # Debug line
        
        order.status = 'ready'
        order.save()
    return redirect('merchant_orders')

@login_required

def add_item(request):
    if request.method == 'POST':
        form = RestaurantMenuForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.restaurant = Restaurant.objects.get(owner=request.user)
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
            item.is_available = 'is_available' in request.POST
            form.save()
            return redirect('menu_dashboard')  # Redirect to the menu display page
    else:
        form = RestaurantMenuForm(instance=item)

    return render(request, 'edit_item.html', {'form': form, 'item': item})

@login_required
def menu_dashboard_view(request):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    items = RestaurantMenu.objects.filter(restaurant__owner=request.user)

    # Detect edit_id from GET or POST
    edit_id = request.POST.get('edit_id') or request.GET.get('edit')

    if edit_id:
        # Editing existing item
        item = get_object_or_404(RestaurantMenu, pk=edit_id, restaurant__owner=request.user)
        form = RestaurantMenuForm(request.POST or None, request.FILES or None, instance=item)
        is_editing = True
    else:
        # Adding new item
        item = None
        form = RestaurantMenuForm(request.POST or None, request.FILES or None)
        is_editing = False

    if request.method == 'POST':
        if form.is_valid():
            new_item = form.save(commit=False)
            new_item.restaurant = restaurant
            new_item.owner = request.user
            new_item.save()
            return redirect('menu_dashboard')  # Make sure this URL name is correct

    return render(request, 'menu_list.html', {
        'items': items,
        'form': form,
        'is_editing': is_editing,
        'item': item,
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

def delete_bank_account(request, account_id):
    account = get_object_or_404(BankAccount, id=account_id, merchant=request.user)

    if request.method == 'POST':
        account.delete()
        return redirect('bank_account_list')  # or wherever your list view is

    return render(request, 'confirm_bank_account_delete.html', {'account': account})
